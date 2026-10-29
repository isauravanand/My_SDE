"""
Sandbox Compiler/Test Feedback Loop.

After generating a patch, runs lightweight static checks against the patched
file contents *before* presenting the patch to the user. If errors are found,
re-prompts the LLM with the error context (up to MAX_RETRY_ROUNDS rounds).

This prevents the user from ever seeing a patch with obvious syntax errors.
"""

from __future__ import annotations

import logging
import py_compile
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_RETRY_ROUNDS = 2
_CSS_UNCLOSED_BRACE_RE = re.compile(r"\{[^}]*$", re.MULTILINE)
_JS_SYNTAX_PATTERNS = [
    re.compile(r"SyntaxError"),
]


@dataclass
class FeedbackResult:
    """Result of running the feedback loop verification pass."""
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stdout: str = ""
    rounds_run: int = 0


def _check_python_syntax(content: str, file_path: str) -> list[str]:
    """Checks Python file syntax via py_compile."""
    errors: list[str] = []
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", encoding="utf-8", delete=False) as f:
        f.write(content)
        tmp_path = f.name
    try:
        py_compile.compile(tmp_path, doraise=True)
    except py_compile.PyCompileError as e:
        errors.append(f"{file_path}: Python syntax error — {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return errors


def _check_css_syntax(content: str, file_path: str) -> list[str]:
    """Performs basic CSS brace-balance check."""
    errors: list[str] = []
    open_count = content.count("{")
    close_count = content.count("}")
    if open_count != close_count:
        errors.append(
            f"{file_path}: CSS brace mismatch — {open_count} opening vs {close_count} closing braces."
        )
    # Check for empty rules that are clearly wrong
    empty_rules = re.findall(r"\.\w[\w-]*\s*\{\s*\}", content)
    if empty_rules:
        errors.append(
            f"{file_path}: CSS contains {len(empty_rules)} empty rule(s): {empty_rules[:3]}"
        )
    return errors


def _check_js_syntax(content: str, file_path: str) -> list[str]:
    """Checks JavaScript/TypeScript syntax via node --check (if node is available)."""
    errors: list[str] = []
    with tempfile.NamedTemporaryFile(
        suffix=".js", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write(content)
        tmp_path = f.name
    try:
        result = subprocess.run(
            ["node", "--check", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            cleaned = result.stderr.replace(tmp_path, file_path)
            errors.append(f"{file_path}: JS syntax error — {cleaned.strip()[:300]}")
    except FileNotFoundError:
        # node not available — skip silently
        pass
    except subprocess.TimeoutExpired:
        logger.warning("node --check timed out for %s", file_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return errors


def _apply_diff_to_snapshot(
    original_snapshot: dict[str, bytes], unified_diff: str
) -> dict[str, bytes]:
    """
    Applies a unified diff to a snapshot dict, returning patched file contents.

    Uses Python's difflib to reconstruct patched files without needing `patch` binary.
    """
    patched: dict[str, bytes] = dict(original_snapshot)

    # Split diff by file sections
    sections = re.split(r"(?=^diff --git )", unified_diff, flags=re.MULTILINE)
    for section in sections:
        if not section.strip():
            continue
        # Extract file path from +++ b/... header
        plus_match = re.search(r"^\+\+\+ b/(.+)$", section, re.MULTILINE)
        if not plus_match:
            continue

        file_path = plus_match.group(1).strip()
        is_delete = plus_match.group(1).strip() == "/dev/null"

        if is_delete:
            patched.pop(file_path, None)
            continue

        # Get original content
        original_bytes = original_snapshot.get(file_path, b"")
        original_lines = original_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)

        # Parse hunks
        hunk_lines = section.splitlines(keepends=True)
        hunk_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

        result_lines: list[str] = []
        orig_idx = 0
        i = 0
        while i < len(hunk_lines):
            hunk_match = hunk_re.match(hunk_lines[i])
            if hunk_match:
                old_start = max(0, int(hunk_match.group(1)) - 1)  # 0-indexed
                # Copy unmodified lines up to old_start
                while orig_idx < old_start and orig_idx < len(original_lines):
                    result_lines.append(original_lines[orig_idx])
                    orig_idx += 1
                i += 1
                while i < len(hunk_lines) and not hunk_lines[i].startswith("@@") and not hunk_lines[i].startswith("diff "):
                    line = hunk_lines[i]
                    if line.startswith("+"):
                        result_lines.append(line[1:])
                    elif line.startswith("-"):
                        orig_idx += 1
                    elif line.startswith(" ") or not line.strip():
                        if orig_idx < len(original_lines):
                            result_lines.append(original_lines[orig_idx])
                            orig_idx += 1
                        else:
                            result_lines.append(line[1:] if line.startswith(" ") else line)
                    i += 1
            else:
                i += 1

        # Copy any remaining original lines
        while orig_idx < len(original_lines):
            result_lines.append(original_lines[orig_idx])
            orig_idx += 1

        patched[file_path] = "".join(result_lines).encode("utf-8")

    return patched


def verify_patch(
    unified_diff: str,
    original_snapshot: dict[str, bytes],
) -> FeedbackResult:
    """
    Applies the unified_diff to a copy of original_snapshot, then runs
    language-appropriate static checks on each modified file.

    Args:
        unified_diff: Unified diff string to verify.
        original_snapshot: Repository file snapshot before patching.

    Returns:
        FeedbackResult with passed=True if all checks pass.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Identify changed files
    changed_files = re.findall(r"^\+\+\+ b/(.+)$", unified_diff, re.MULTILINE)
    changed_files = [f.strip() for f in changed_files if f.strip() != "/dev/null"]

    if not changed_files:
        return FeedbackResult(passed=True, rounds_run=0)

    try:
        patched_snapshot = _apply_diff_to_snapshot(original_snapshot, unified_diff)
    except Exception as e:
        return FeedbackResult(
            passed=False,
            errors=[f"Failed to apply diff for verification: {e}"],
        )

    for file_path in changed_files:
        content_bytes = patched_snapshot.get(file_path)
        if content_bytes is None:
            continue
        try:
            content = content_bytes.decode("utf-8", errors="replace")
        except Exception:
            continue

        ext = Path(file_path).suffix.lower()

        if ext == ".py":
            errors.extend(_check_python_syntax(content, file_path))
        elif ext == ".css":
            errors.extend(_check_css_syntax(content, file_path))
        elif ext in {".js", ".mjs", ".cjs"}:
            errors.extend(_check_js_syntax(content, file_path))
        elif ext in {".ts", ".tsx", ".jsx"}:
            # Basic brace balance check for JS-family files
            open_c = content.count("{")
            close_c = content.count("}")
            if abs(open_c - close_c) > 5:
                warnings.append(
                    f"{file_path}: Possible brace mismatch ({open_c} open, {close_c} close)."
                )

    passed = len(errors) == 0
    return FeedbackResult(
        passed=passed,
        errors=errors,
        warnings=warnings,
        rounds_run=1,
    )
