"""
Enhanced execution context builder.

Builds a prioritized, token-budgeted code context string for the patch generator.
Ensures the LLM always sees the most relevant files first, within a character budget.
"""

from __future__ import annotations

import logging
import posixpath
import re

logger = logging.getLogger(__name__)

# Total character budget for code context passed to the LLM
DEFAULT_CONTEXT_BUDGET = 60_000

# Core web / config files always included if present (lowest priority, filled last)
CORE_WEB_FILES = {
    "index.html", "index.css", "style.css", "main.css", "styles.css",
    "App.css", "App.tsx", "App.jsx", "app.css",
}
CORE_CONFIG_FILES = {
    "package.json", "pyproject.toml", "tsconfig.json", "vite.config.ts",
    "vite.config.js", "tailwind.config.js", "webpack.config.js",
}

# Simple import/require regex to resolve transitive file dependencies
_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?\s+from\s+|require\s*\(\s*)['"](\.{1,2}/[^'"]+)['"]""",
    re.MULTILINE,
)


def _resolve_local_import(importer_path: str, import_path: str) -> list[str]:
    """
    Resolves a relative import path to candidate file paths.

    Args:
        importer_path: The file that contains the import statement (e.g. 'src/App.jsx').
        import_path: The import specifier (e.g. './components/Header').

    Returns:
        Candidate paths with common extensions tried (e.g. .js, .ts, .tsx, .jsx, .css).
    """
    parent = posixpath.dirname(importer_path)
    combined = posixpath.normpath(posixpath.join(parent, import_path))
    base = combined.lstrip("/")
    candidates: list[str] = [base]
    # Try with common extensions
    for ext in [".js", ".ts", ".tsx", ".jsx", ".css", ".scss", ".py"]:
        candidates.append(base + ext)
        candidates.append(base + "/index" + ext)
    return candidates


def _find_imported_files(
    seed_files: set[str],
    snapshot: dict[str, bytes],
    max_depth: int = 2,
) -> set[str]:
    """
    Discovers files imported by `seed_files` up to `max_depth` levels deep.

    Args:
        seed_files: Starting set of file paths to scan for import statements.
        snapshot: Repository file snapshot dict (path -> bytes).
        max_depth: How many levels of transitive imports to follow.

    Returns:
        Set of discovered file paths (includes seed_files).
    """
    discovered: set[str] = set(seed_files)
    frontier: set[str] = set(seed_files)

    for _ in range(max_depth):
        next_frontier: set[str] = set()
        for file_path in frontier:
            content_bytes = snapshot.get(file_path)
            if not content_bytes:
                continue
            try:
                content = content_bytes.decode("utf-8", errors="ignore")
            except Exception:
                continue
            for match in _IMPORT_RE.finditer(content):
                import_spec = match.group(1)
                for candidate in _resolve_local_import(file_path, import_spec):
                    if candidate in snapshot and candidate not in discovered:
                        next_frontier.add(candidate)
                        discovered.add(candidate)
        frontier = next_frontier
        if not frontier:
            break

    return discovered


def _format_file_block(file_path: str, content: str, max_chars: int) -> str:
    """Formats a single file as a context block, truncating if needed."""
    if len(content) > max_chars:
        content = content[:max_chars] + "\n... [truncated for context budget]"
    return f"=== FULL REPOSITORY FILE: {file_path} ===\n{content}\n=== END FILE: {file_path} ==="


def build_execution_context(
    task_title: str,
    task_description: str,
    plan_data: dict,
    snapshot: dict[str, bytes],
    budget: int = DEFAULT_CONTEXT_BUDGET,
) -> str:
    """
    Builds a prioritized, token-budgeted code context string.

    Priority order (highest to lowest):
      1. Files explicitly listed in plan step `relevant_files` (full content)
      2. Files mentioned in task title or description (full content)
      3. Files imported by #1 and #2 (auto-resolved via import scanning)
      4. Core web root files (index.html, index.css, App.css, etc.)
      5. Core config files (package.json, pyproject.toml, etc.)

    Args:
        task_title: The task's title string.
        task_description: The task's description string.
        plan_data: The plan's data dict (must have `implementation_steps`).
        snapshot: Repository file snapshot dict (path -> bytes).
        budget: Maximum total character budget for the context string.

    Returns:
        A formatted multi-file context string ready to embed in the LLM prompt.
    """
    if not snapshot:
        return "No repository code context provided"

    remaining_budget = budget
    blocks: list[str] = []
    included: set[str] = set()

    def add_file(file_path: str, priority_label: str) -> bool:
        nonlocal remaining_budget
        if file_path in included:
            return False
        content_bytes = snapshot.get(file_path)
        if not content_bytes:
            return False
        try:
            content = content_bytes.decode("utf-8", errors="replace")
        except Exception:
            return False
        block = _format_file_block(file_path, content, max_chars=remaining_budget - 200)
        if len(block) > remaining_budget:
            logger.debug("Context budget exhausted; skipping '%s' (%s)", file_path, priority_label)
            return False
        blocks.append(block)
        included.add(file_path)
        remaining_budget -= len(block)
        logger.debug("Added '%s' to context (%s, %d chars)", file_path, priority_label, len(block))
        return True

    # Priority 1: Plan step relevant_files
    plan_files: set[str] = set()
    for step in plan_data.get("implementation_steps", []):
        for rf in step.get("relevant_files", []):
            clean = rf.lstrip("./").strip()
            plan_files.add(clean)

    for fp in sorted(plan_files):
        add_file(fp, "plan_step")

    # Priority 2: Files mentioned in task text
    combined_text = f"{task_title} {task_description or ''}".lower()
    text_files: set[str] = set()
    for file_path in snapshot:
        base = file_path.split("/")[-1].lower()
        if base in combined_text or file_path.lower() in combined_text:
            text_files.add(file_path)

    for fp in sorted(text_files - plan_files):
        add_file(fp, "task_mention")

    # Priority 3: Transitive imports from P1+P2
    if remaining_budget > 5000:
        seed = plan_files | text_files
        imported = _find_imported_files(seed & set(snapshot.keys()), snapshot)
        for fp in sorted(imported - included):
            if remaining_budget < 2000:
                break
            add_file(fp, "imported_by_seed")

    # Priority 4: Core web files
    for fp in sorted(CORE_WEB_FILES):
        if remaining_budget < 2000:
            break
        add_file(fp, "core_web")

    # Priority 5: Core config files
    for fp in sorted(CORE_CONFIG_FILES):
        if remaining_budget < 1000:
            break
        add_file(fp, "core_config")

    if not blocks:
        return "No repository code context provided"

    return "\n\n".join(blocks)
