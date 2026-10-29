"""Unit tests for the Live Screen Preview builder."""
from app.execution.preview_builder import build_live_preview


def test_build_live_preview_empty_snapshot():
    res = build_live_preview({}, "")
    assert res["has_preview"] is False
    assert "empty" in res["reason"]


def test_build_live_preview_no_html_entrypoint():
    snapshot = {"main.py": b"print('hello')", "utils.py": b"# utils"}
    res = build_live_preview(snapshot, "")
    assert res["has_preview"] is False
    assert "No HTML entrypoint" in res["reason"]


def test_build_live_preview_inlines_css():
    snapshot = {
        "index.html": b"<!DOCTYPE html><html><head><link rel='stylesheet' href='index.css'></head><body><h1>Amazon</h1></body></html>",
        "index.css": b"h1 { color: #111; }",
    }
    patch_diff = """\
diff --git a/index.css b/index.css
--- a/index.css
+++ b/index.css
@@ -1 +1,2 @@
-h1 { color: #111; }
+h1 { color: #febd69; font-size: 24px; }
"""
    res = build_live_preview(snapshot, patch_diff)
    assert res["has_preview"] is True
    assert res["entrypoint"] == "index.html"
    # Patched CSS should be inlined in html_after
    assert "#febd69" in res["html_after"]
    assert "<style data-source='index.css'>" in res["html_after"]
    # Original CSS should be in html_before
    assert "#111" in res["html_before"]
