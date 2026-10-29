"""
Surgical Search-and-Replace engine for LLM-generated code edits.

Instead of fragile unified git diffs with line-number arithmetic, the LLM
outputs SEARCH/REPLACE block pairs. This engine:
  1. Parses FILE + SEARCH/REPLACE block groups from raw LLM output.
  2. Applies each block to the target file content (exact then fuzzy match).
  3. Converts the applied changes into a valid unified git diff for audit.
"""

from __future__ import annotations

import difflib
import logging
import re
import textwrap
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Sentinel markers ────────────────────────────────────────────────────────
_SEARCH_OPEN = "<<<<<<< SEARCH"
_DIVIDER = "======="
_REPLACE_CLOSE = ">>>>>>> REPLACE"

# FILE: <path> immediately before a block (optional — for multi-file output)
_FILE_HEADER_RE = re.compile(
    r"^(?:FILE|file|File)\s*:\s*(?P<path>\S+)\s*$", re.MULTILINE
)

# Full block regex: FILE (optional) + SEARCH + REPLACE
_BLOCK_RE = re.compile(
    r"(?:(?:FILE|file|File)\s*:\s*(?P<path>[^\n]+)\n)?"
    r"<{7}\s*SEARCH\s*\n"
    r"(?P<search>.*?)"
    r"={7}\s*\n"
    r"(?P<replace>.*?)"
    r">{7}\s*REPLACE\s*",
    re.DOTALL,
)


class SearchReplaceError(Exception):
    """Raised when a SEARCH block cannot be found in the target file."""
    pass


@dataclass
class SearchReplaceBlock:
    """Represents a single parsed SEARCH/REPLACE edit."""
    file_path: str
    search_text: str
    replace_text: str


@dataclass
class SearchReplaceResult:
    """Result of applying all blocks to a snapshot."""
    unified_diff: str
    files_changed: list[str] = field(default_factory=list)
    blocks_applied: int = 0
    blocks_skipped: int = 0


def parse_blocks(llm_output: str, default_file: str = "") -> list[SearchReplaceBlock]:
    """
    Extracts all SEARCH/REPLACE blocks from raw LLM output.

    Each block must contain:
      <<<<<<< SEARCH
      <original text>
      =======
      <replacement text>
      >>>>>>> REPLACE

    Optionally preceded by:
      FILE: path/to/file.ext

    Args:
        llm_output: Raw string from the LLM containing one or more edit blocks.
        default_file: Fallback file path if no FILE: header is present.

    Returns:
        List of SearchReplaceBlock instances in document order.
    """
    blocks: list[SearchReplaceBlock] = []
    last_file_path = default_file

    for m in _BLOCK_RE.finditer(llm_output):
        path = (m.group("path") or "").strip() or last_file_path
        if path:
            last_file_path = path
        search_text = m.group("search")
        replace_text = m.group("replace")
        blocks.append(
            SearchReplaceBlock(
                file_path=path.lstrip("./").strip(),
                search_text=search_text,
                replace_text=replace_text,
            )
        )

    return blocks


def _normalize_whitespace(text: str) -> str:
    """Strip leading/trailing blank lines and de-indent for fuzzy matching."""
    lines = text.splitlines()
    # Remove leading/trailing empty lines
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""
    # Detect common indentation
    dedented = textwrap.dedent("\n".join(lines))
    return dedented


def _find_and_replace(original: str, search: str, replace: str) -> str | None:
    """
    Attempts to find `search` in `original` and replace with `replace`.

    Strategy:
      1. Exact string match.
      2. Whitespace-normalized match (strip leading indent per line).
      3. Fuzzy line-sequence match via SequenceMatcher (>= 90% ratio).

    Returns the modified string, or None if no match is found.
    """
    # 1. Exact match
    if search in original:
        return original.replace(search, replace, 1)

    # 2. Normalize whitespace and try again
    norm_search = _normalize_whitespace(search)
    norm_original = _normalize_whitespace(original)
    if norm_search and norm_search in norm_original:
        # Re-anchor to original by finding the best line range
        orig_lines = original.splitlines(keepends=True)
        search_lines = norm_search.splitlines()
        for i in range(len(orig_lines)):
            window = "".join(
                line_item.strip() for line_item in orig_lines[i : i + len(search_lines)]
            )
            search_stripped = "".join(line_item.strip() for line_item in search_lines)
            if window == search_stripped:
                # Replace the window of lines
                new_lines = orig_lines[:i] + [replace] + orig_lines[i + len(search_lines) :]
                return "".join(new_lines)

    # 3. Fuzzy SequenceMatcher on stripped lines
    orig_lines = original.splitlines()
    search_lines = [line_item.strip() for line_item in search.splitlines() if line_item.strip()]
    if not search_lines:
        return None

    best_ratio = 0.0
    best_start = -1
    best_end = -1
    window_size = len(search_lines)

    for i in range(len(orig_lines) - window_size + 1):
        window = [line_item.strip() for line_item in orig_lines[i : i + window_size]]
        ratio = difflib.SequenceMatcher(None, search_lines, window).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start = i
            best_end = i + window_size

    if best_ratio >= 0.90 and best_start >= 0:
        new_lines = orig_lines[:best_start] + replace.splitlines() + orig_lines[best_end:]
        return "\n".join(new_lines)

    return None


def _make_unified_diff(
    original: str, modified: str, file_path: str, context_lines: int = 3
) -> str:
    """Generates a unified diff string from original and modified content."""
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)
    # Ensure trailing newline
    if orig_lines and not orig_lines[-1].endswith("\n"):
        orig_lines[-1] += "\n"
    if mod_lines and not mod_lines[-1].endswith("\n"):
        mod_lines[-1] += "\n"

    diff = list(
        difflib.unified_diff(
            orig_lines,
            mod_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            n=context_lines,
        )
    )
    if not diff:
        return ""
    header = f"diff --git a/{file_path} b/{file_path}\n"
    return header + "".join(diff)


def apply_blocks(
    blocks: list[SearchReplaceBlock],
    snapshot: dict[str, bytes],
) -> SearchReplaceResult:
    """
    Applies a list of SearchReplaceBlock edits to a file snapshot.

    Args:
        blocks: Parsed edit blocks from `parse_blocks()`.
        snapshot: Dict mapping file_path -> file_bytes from the repository snapshot.

    Returns:
        SearchReplaceResult with the combined unified diff and statistics.

    Raises:
        SearchReplaceError: If a SEARCH block cannot be found in its target file
            and no fuzzy match is available.
    """
    # Group blocks by file so we process each file once in order
    file_blocks: dict[str, list[SearchReplaceBlock]] = {}
    for block in blocks:
        file_blocks.setdefault(block.file_path, []).append(block)

    all_diffs: list[str] = []
    files_changed: list[str] = []
    applied = 0
    skipped = 0

    for file_path, file_edit_blocks in file_blocks.items():
        # Load original content from snapshot
        original_bytes = snapshot.get(file_path) or snapshot.get(file_path.lstrip("./"))
        if original_bytes is None:
            # File doesn't exist yet — treat as new file creation
            original_content = ""
        else:
            original_content = original_bytes.decode("utf-8", errors="replace")

        current_content = original_content

        for block in file_edit_blocks:
            modified = _find_and_replace(current_content, block.search_text, block.replace_text)
            if modified is None:
                logger.warning(
                    "SEARCH block not found in '%s'. Skipping block. "
                    "Search preview: %r",
                    file_path,
                    block.search_text[:120],
                )
                skipped += 1
                continue
            current_content = modified
            applied += 1

        if current_content != original_content:
            diff_str = _make_unified_diff(original_content, current_content, file_path)
            if diff_str:
                all_diffs.append(diff_str)
                files_changed.append(file_path)
        elif applied == 0 and skipped > 0:
            raise SearchReplaceError(
                f"No SEARCH blocks matched in '{file_path}'. "
                "The model's SEARCH text did not match the repository file content."
            )

    combined_diff = "\n".join(all_diffs)
    return SearchReplaceResult(
        unified_diff=combined_diff,
        files_changed=files_changed,
        blocks_applied=applied,
        blocks_skipped=skipped,
    )


def extract_from_llm_output(
    llm_output: str,
    snapshot: dict[str, bytes],
    default_file: str = "",
) -> SearchReplaceResult:
    """
    Convenience wrapper: parse blocks from LLM output and apply to snapshot.

    Args:
        llm_output: Raw LLM response text.
        snapshot: Repository file snapshot dict (path -> bytes).
        default_file: If the LLM didn't specify FILE: headers, use this path.

    Returns:
        SearchReplaceResult with unified_diff ready for patch validation.
    """
    blocks = parse_blocks(llm_output, default_file=default_file)
    if not blocks:
        raise SearchReplaceError(
            "No SEARCH/REPLACE blocks found in LLM output. "
            "Expected format: <<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE"
        )
    return apply_blocks(blocks, snapshot)
