from app.rag.chunking import CodeChunker


def test_chunk_small_file_single_chunk():
    chunker = CodeChunker(target_lines=60)
    code = "def hello():\n    return 'world'\n"
    chunks = chunker.chunk_file("hello.py", code, "python")

    assert len(chunks) == 1
    ch = chunks[0]
    assert ch.start_line == 1
    assert ch.end_line == 2
    assert "def hello():" in ch.chunk_content
    assert len(ch.content_hash) == 64
    assert ch.symbol_type == "function"
    assert ch.symbol_name == "hello"


def test_chunk_python_functions_and_classes():
    chunker = CodeChunker(target_lines=10, max_lines=20)
    code = """# Module header
import os
import sys

class UserService:
    def __init__(self, db):
        self.db = db

    def get_user(self, user_id):
        return self.db.find(user_id)

def send_welcome_email(user_email):
    # Send email
    print(f"Sending email to {user_email}")
    return True
"""
    chunks = chunker.chunk_file("services.py", code, "python")

    assert len(chunks) >= 2
    # Ensure line numbers are 1-based and valid
    for ch in chunks:
        assert ch.start_line >= 1
        assert ch.end_line >= ch.start_line
        assert len(ch.content_hash) == 64

    # Check extracted symbols
    symbols = [ch.symbol_name for ch in chunks if ch.symbol_name]
    assert "UserService" in symbols or "send_welcome_email" in symbols


def test_chunk_javascript_functions():
    chunker = CodeChunker(target_lines=10, max_lines=20)
    code = """export async function fetchUser(id) {
    const res = await fetch(`/api/users/${id}`);
    return res.json();
}

export const calculateTotal = (items) => {
    return items.reduce((sum, item) => sum + item.price, 0);
};
"""
    chunks = chunker.chunk_file("api.js", code, "javascript")
    assert len(chunks) >= 1
    symbols = [ch.symbol_name for ch in chunks if ch.symbol_name]
    assert any(s in ("fetchUser", "calculateTotal") for s in symbols)


def test_sliding_window_fallback():
    chunker = CodeChunker(target_lines=15, max_lines=20, overlap_lines=5)
    # Long flat text without symbols
    lines = [f"line {i} with some arbitrary code content here" for i in range(1, 51)]
    code = "\n".join(lines)

    chunks = chunker.chunk_file("script.sh", code, "shell")
    assert len(chunks) >= 3

    # Check contiguous overlapping ranges
    for i in range(len(chunks) - 1):
        assert chunks[i].start_line < chunks[i + 1].start_line
        assert chunks[i].end_line > chunks[i + 1].start_line  # Overlap present
