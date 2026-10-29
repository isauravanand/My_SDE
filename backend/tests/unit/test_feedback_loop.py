"""Unit tests for the Sandbox Compiler/Test Feedback Loop."""
from app.execution.feedback_loop import (
    _apply_diff_to_snapshot,
    _check_css_syntax,
    _check_python_syntax,
    verify_patch,
)

# ── _check_python_syntax ──────────────────────────────────────────────────────

def test_python_syntax_valid():
    content = "def hello():\n    return 'world'\n"
    errors = _check_python_syntax(content, "main.py")
    assert errors == []


def test_python_syntax_invalid():
    content = "def broken(\n    return 42\n"
    errors = _check_python_syntax(content, "main.py")
    assert len(errors) == 1
    assert "main.py" in errors[0]
    assert "syntax error" in errors[0].lower()


# ── _check_css_syntax ─────────────────────────────────────────────────────────

def test_css_brace_balance_ok():
    content = ".box { margin: 0; }\nbody { padding: 0; }\n"
    errors = _check_css_syntax(content, "style.css")
    assert errors == []


def test_css_brace_mismatch_detected():
    content = ".box { margin: 0;\nbody { padding: 0; }\n"  # missing closing brace
    errors = _check_css_syntax(content, "style.css")
    assert any("brace mismatch" in e for e in errors)


def test_css_empty_rule_detected():
    content = ".box {}\n.container { display: flex; }\n"
    errors = _check_css_syntax(content, "style.css")
    assert any("empty rule" in e for e in errors)


# ── _apply_diff_to_snapshot ───────────────────────────────────────────────────

def test_apply_diff_adds_lines():
    original = {"main.py": b"def hello():\n    pass\n"}
    diff = (
        "diff --git a/main.py b/main.py\n"
        "--- a/main.py\n"
        "+++ b/main.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def hello():\n"
        "-    pass\n"
        "+    return 'world'\n"
        "+# updated\n"
    )
    patched = _apply_diff_to_snapshot(original, diff)
    content = patched["main.py"].decode()
    assert "return 'world'" in content
    assert "# updated" in content


def test_apply_diff_empty_diff_unchanged():
    original = {"main.py": b"x = 1\n"}
    patched = _apply_diff_to_snapshot(original, "")
    assert patched["main.py"] == b"x = 1\n"


# ── verify_patch ──────────────────────────────────────────────────────────────

def test_verify_patch_valid_python():
    original = {"app.py": b"def run():\n    pass\n"}
    diff = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def run():\n"
        "-    pass\n"
        "+    return True\n"
    )
    result = verify_patch(diff, original)
    assert result.passed is True
    assert result.errors == []


def test_verify_patch_invalid_python_syntax():
    original = {"app.py": b"def run():\n    pass\n"}
    diff = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def run():\n"
        "-    pass\n"
        "+    return (\n"  # unclosed paren — syntax error
    )
    result = verify_patch(diff, original)
    assert result.passed is False
    assert len(result.errors) >= 1


def test_verify_patch_valid_css():
    original = {"style.css": b".box { margin: 0; }\n"}
    diff = (
        "diff --git a/style.css b/style.css\n"
        "--- a/style.css\n"
        "+++ b/style.css\n"
        "@@ -1,1 +1,2 @@\n"
        "-.box { margin: 0; }\n"
        "+.box { margin: 0; }\n"
        "+.nav { display: flex; }\n"
    )
    result = verify_patch(diff, original)
    assert result.passed is True


def test_verify_patch_css_brace_mismatch():
    original = {"style.css": b".box { margin: 0; }\n"}
    diff = (
        "diff --git a/style.css b/style.css\n"
        "--- a/style.css\n"
        "+++ b/style.css\n"
        "@@ -1,1 +1,2 @@\n"
        "-.box { margin: 0; }\n"
        "+.box { margin: 0;\n"  # missing closing brace
        "+.nav { display: flex; }\n"
    )
    result = verify_patch(diff, original)
    assert result.passed is False


def test_verify_patch_empty_diff_passes():
    result = verify_patch("", {})
    assert result.passed is True
    assert result.rounds_run == 0
