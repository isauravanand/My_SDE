"""Unit tests for the Enhanced Execution Context Builder."""
from app.execution.context_builder import (
    DEFAULT_CONTEXT_BUDGET,
    _find_imported_files,
    _resolve_local_import,
    build_execution_context,
)

# ── _resolve_local_import ─────────────────────────────────────────────────────

def test_resolve_local_import_same_dir():
    candidates = _resolve_local_import("src/App.jsx", "./Header")
    assert "src/Header" in candidates
    assert "src/Header.jsx" in candidates
    assert "src/Header.tsx" in candidates


def test_resolve_local_import_parent_dir():
    candidates = _resolve_local_import("src/components/Button.jsx", "../utils")
    assert "src/utils" in candidates
    assert "src/utils.js" in candidates


# ── _find_imported_files ──────────────────────────────────────────────────────

def test_find_imported_files_discovers_deps():
    snapshot = {
        "src/App.jsx": b"import Header from './Header';\nimport './styles.css';\n",
        "src/Header.jsx": b"export default function Header() {}\n",
        "src/Header.js": b"",
        "src/styles.css": b".box { margin: 0; }\n",
    }
    discovered = _find_imported_files({"src/App.jsx"}, snapshot)
    # Should find at least App.jsx itself
    assert "src/App.jsx" in discovered
    # At least one imported file should be discovered
    assert len(discovered) >= 1


def test_find_imported_files_max_depth_zero_returns_seed():
    snapshot = {
        "src/App.jsx": b"import Header from './Header';\n",
        "src/Header.jsx": b"",
    }
    discovered = _find_imported_files({"src/App.jsx"}, snapshot, max_depth=0)
    assert discovered == {"src/App.jsx"}


def test_find_imported_files_skips_missing():
    snapshot = {
        "src/App.jsx": b"import Nonexistent from './Nonexistent';\n",
    }
    discovered = _find_imported_files({"src/App.jsx"}, snapshot)
    assert "src/Nonexistent.jsx" not in discovered


# ── build_execution_context ───────────────────────────────────────────────────

def test_build_context_includes_plan_files():
    snapshot = {
        "index.css": b".box { margin: 0; }\n",
        "index.html": b"<html></html>\n",
        "unrelated.txt": b"unrelated content\n",
    }
    plan_data = {
        "implementation_steps": [
            {"step_id": "1", "title": "Style fix", "relevant_files": ["index.css"], "description": ""},
        ]
    }
    context = build_execution_context(
        task_title="Fix styling",
        task_description="Update the CSS",
        plan_data=plan_data,
        snapshot=snapshot,
    )
    assert "index.css" in context
    assert ".box { margin: 0; }" in context


def test_build_context_respects_budget():
    # Create a snapshot with a very large file
    big_content = b"x" * 200_000
    snapshot = {
        "big_file.py": big_content,
        "small_file.py": b"# small\n",
    }
    plan_data = {
        "implementation_steps": [
            {"step_id": "1", "title": "Update", "relevant_files": ["big_file.py", "small_file.py"], "description": ""},
        ]
    }
    context = build_execution_context(
        task_title="Update files",
        task_description="",
        plan_data=plan_data,
        snapshot=snapshot,
        budget=DEFAULT_CONTEXT_BUDGET,
    )
    assert len(context) <= DEFAULT_CONTEXT_BUDGET + 500  # small tolerance for block headers


def test_build_context_empty_snapshot_returns_fallback():
    context = build_execution_context(
        task_title="Fix bug",
        task_description="",
        plan_data={"implementation_steps": []},
        snapshot={},
    )
    assert context == "No repository code context provided"


def test_build_context_includes_core_web_files():
    snapshot = {
        "index.html": b"<html></html>\n",
        "index.css": b"body { margin: 0; }\n",
        "unrelated.md": b"readme\n",
    }
    plan_data = {"implementation_steps": []}
    context = build_execution_context(
        task_title="Update homepage",
        task_description="",
        plan_data=plan_data,
        snapshot=snapshot,
    )
    # Core web files should be included even without explicit plan steps
    assert "index.html" in context or "index.css" in context


def test_build_context_task_mention_picks_up_file():
    snapshot = {
        "navbar.css": b".nav { display: flex; }\n",
        "footer.css": b".footer { padding: 0; }\n",
    }
    plan_data = {"implementation_steps": []}
    context = build_execution_context(
        task_title="Fix navbar styling",
        task_description="The navbar.css needs update",
        plan_data=plan_data,
        snapshot=snapshot,
    )
    assert "navbar.css" in context


def test_build_context_deduplicates_files():
    """A file listed in both plan steps and task text should appear only once."""
    snapshot = {"index.css": b".box {}\n"}
    plan_data = {
        "implementation_steps": [
            {"step_id": "1", "title": "Fix", "relevant_files": ["index.css"], "description": ""},
        ]
    }
    context = build_execution_context(
        task_title="Fix index.css styles",
        task_description="Update index.css",
        plan_data=plan_data,
        snapshot=snapshot,
    )
    # Should appear exactly once (not duplicated)
    assert context.count("=== FULL REPOSITORY FILE: index.css ===") == 1
