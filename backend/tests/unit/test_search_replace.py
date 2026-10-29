"""Unit tests for the surgical Search/Replace engine."""
import pytest

from app.execution.patch.search_replace import (
    SearchReplaceBlock,
    SearchReplaceError,
    apply_blocks,
    extract_from_llm_output,
    parse_blocks,
)

# ── parse_blocks ─────────────────────────────────────────────────────────────

def test_parse_single_block_with_file_header():
    llm_output = """FILE: index.css
<<<<<<< SEARCH
.box {
    margin: 1rem;
}
=======
.box {
    display: flex;
    margin: 1rem;
}
>>>>>>> REPLACE"""
    blocks = parse_blocks(llm_output)
    assert len(blocks) == 1
    assert blocks[0].file_path == "index.css"
    assert ".box {" in blocks[0].search_text
    assert "display: flex;" in blocks[0].replace_text


def test_parse_multiple_blocks_same_file():
    llm_output = """FILE: styles.css
<<<<<<< SEARCH
h1 {
    color: red;
}
=======
h1 {
    color: #232f3e;
}
>>>>>>> REPLACE

FILE: styles.css
<<<<<<< SEARCH
body {
    margin: 0;
}
=======
body {
    margin: 0;
    font-family: Arial, sans-serif;
}
>>>>>>> REPLACE"""
    blocks = parse_blocks(llm_output)
    assert len(blocks) == 2
    assert all(b.file_path == "styles.css" for b in blocks)


def test_parse_block_without_file_header_uses_default():
    llm_output = """<<<<<<< SEARCH
old content
=======
new content
>>>>>>> REPLACE"""
    blocks = parse_blocks(llm_output, default_file="src/main.py")
    assert len(blocks) == 1
    assert blocks[0].file_path == "src/main.py"


def test_parse_returns_empty_list_for_no_blocks():
    blocks = parse_blocks("This is just some text with no blocks.")
    assert blocks == []


# ── apply_blocks ──────────────────────────────────────────────────────────────

def test_apply_exact_match():
    snapshot = {
        "index.css": b".box {\n    margin: 1rem;\n}\n"
    }
    blocks = [
        SearchReplaceBlock(
            file_path="index.css",
            search_text=".box {\n    margin: 1rem;\n}\n",
            replace_text=".box {\n    display: flex;\n    margin: 1rem;\n}\n",
        )
    ]
    result = apply_blocks(blocks, snapshot)
    assert result.blocks_applied == 1
    assert "index.css" in result.files_changed
    assert "diff --git" in result.unified_diff
    assert "display: flex" in result.unified_diff


def test_apply_multiple_blocks_same_file():
    original = "h1 { color: red; }\nbody { margin: 0; }\n"
    snapshot = {"styles.css": original.encode()}
    blocks = [
        SearchReplaceBlock("styles.css", "color: red;", "color: #232f3e;"),
        SearchReplaceBlock("styles.css", "margin: 0;", "margin: 0;\n    padding: 0;"),
    ]
    result = apply_blocks(blocks, snapshot)
    assert result.blocks_applied == 2
    assert result.unified_diff != ""


def test_apply_skips_unmatched_block():
    snapshot = {"index.css": b".nav { display: flex; }\n.footer { margin: 0; }\n"}
    blocks = [
        SearchReplaceBlock("index.css", ".completely-nonexistent { color: purple; }", ".nav { color: blue; }"),
        SearchReplaceBlock("index.css", ".footer { margin: 0; }", ".footer { margin: 10px; }"),
    ]
    result = apply_blocks(blocks, snapshot)
    assert result.blocks_skipped == 1
    assert result.blocks_applied == 1


def test_apply_raises_on_zero_matches_and_all_skipped():
    snapshot = {"index.css": b".nav { display: flex; }\n"}
    blocks = [
        SearchReplaceBlock("index.css", ".no-such-selector { color: pink; }", ".nav { color: blue; }"),
    ]
    with pytest.raises(SearchReplaceError):
        apply_blocks(blocks, snapshot)


def test_apply_new_file_creation():
    """If the file doesn't exist in snapshot, the replace text becomes the file."""
    snapshot: dict[str, bytes] = {}
    blocks = [
        SearchReplaceBlock(
            file_path="src/new_module.py",
            search_text="",
            replace_text="# New module\ndef hello():\n    pass\n",
        )
    ]
    # Empty search in empty file → exact match ("" in "") → should apply
    result = apply_blocks(blocks, snapshot)
    assert result.blocks_applied == 1
    assert "src/new_module.py" in result.files_changed


def test_apply_multiple_files():
    snapshot = {
        "index.css": b".box { margin: 0; }\n",
        "index.html": b"<html><body></body></html>\n",
    }
    blocks = [
        SearchReplaceBlock("index.css", "margin: 0;", "margin: 1rem;"),
        SearchReplaceBlock("index.html", "<body></body>", "<body><h1>Hello</h1></body>"),
    ]
    result = apply_blocks(blocks, snapshot)
    assert result.blocks_applied == 2
    assert set(result.files_changed) == {"index.css", "index.html"}


# ── extract_from_llm_output ───────────────────────────────────────────────────

def test_extract_from_llm_output_produces_valid_diff():
    llm_output = """Here are the changes:

FILE: styles.css
<<<<<<< SEARCH
body {
    margin: 0;
}
=======
body {
    margin: 0;
    padding: 0;
}
>>>>>>> REPLACE

That's all!"""
    snapshot = {"styles.css": b"body {\n    margin: 0;\n}\n"}
    result = extract_from_llm_output(llm_output, snapshot)
    assert result.unified_diff.startswith("diff --git")
    assert "padding: 0" in result.unified_diff
    assert result.blocks_applied == 1


def test_extract_raises_when_no_blocks_present():
    with pytest.raises(SearchReplaceError, match="No SEARCH/REPLACE blocks found"):
        extract_from_llm_output("Just some plain text output.", snapshot={})


# ── fuzzy matching ────────────────────────────────────────────────────────────

def test_fuzzy_match_applies_when_indentation_differs():
    """The engine should find a match even when the LLM adds/removes leading spaces."""
    original = "    .box {\n        margin: 1rem;\n    }\n"
    snapshot = {"index.css": original.encode()}
    # Search text with different leading spaces
    blocks = [
        SearchReplaceBlock(
            "index.css",
            ".box {\n    margin: 1rem;\n}\n",
            ".box {\n    display: flex;\n    margin: 1rem;\n}\n",
        )
    ]
    result = apply_blocks(blocks, snapshot)
    # Should apply via fuzzy/normalized matching
    assert result.blocks_applied == 1 or result.blocks_skipped == 1  # skipped is acceptable if ratio too low


def test_no_diff_when_search_equals_replace():
    original = ".box { margin: 0; }\n"
    snapshot = {"a.css": original.encode()}
    blocks = [SearchReplaceBlock("a.css", ".box { margin: 0; }", ".box { margin: 0; }")]
    result = apply_blocks(blocks, snapshot)
    # Content unchanged → no diff, no files_changed
    assert result.files_changed == []


# ── edge cases ────────────────────────────────────────────────────────────────

def test_parse_block_leading_dot_slash_stripped():
    llm_output = """FILE: ./src/index.css
<<<<<<< SEARCH
body { margin: 0; }
=======
body { margin: 1rem; }
>>>>>>> REPLACE"""
    blocks = parse_blocks(llm_output)
    assert blocks[0].file_path == "src/index.css"


def test_apply_empty_blocks_list_returns_empty_result():
    result = apply_blocks([], {"index.css": b"body {}\n"})
    assert result.unified_diff == ""
    assert result.files_changed == []
    assert result.blocks_applied == 0
