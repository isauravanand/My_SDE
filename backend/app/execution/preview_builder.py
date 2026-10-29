"""
Live UI preview generator for execution runs.
Renders repository HTML and inlines patched CSS/JS for an isolated in-browser preview.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.execution.feedback_loop import _apply_diff_to_snapshot

logger = logging.getLogger(__name__)


def build_live_preview(
    original_snapshot: dict[str, bytes],
    raw_diff: str,
) -> dict[str, Any]:
    """
    Given the original snapshot and a proposed patch diff, builds a previewable
    HTML bundle with all modified CSS and JS inlined.
    """
    if not original_snapshot:
        return {
            "has_preview": False,
            "reason": "Repository snapshot is empty or not available.",
        }

    # 1. Apply diff to get patched snapshot
    try:
        patched_snapshot = _apply_diff_to_snapshot(original_snapshot, raw_diff) if raw_diff else original_snapshot
    except Exception as e:
        logger.warning("Failed to apply diff for live preview: %s", e)
        patched_snapshot = dict(original_snapshot)

    # 2. Find primary HTML entrypoint
    html_candidates = [
        "index.html",
        "public/index.html",
        "src/index.html",
        "app/index.html",
    ]
    entrypoint = None
    for candidate in html_candidates:
        if candidate in patched_snapshot:
            entrypoint = candidate
            break

    if not entrypoint:
        # Check any .html file
        for path in sorted(patched_snapshot.keys()):
            if path.endswith(".html"):
                entrypoint = path
                break

    if not entrypoint:
        return {
            "has_preview": False,
            "reason": "No HTML entrypoint found in repository (e.g. index.html). Live screen preview is available for web projects with HTML files.",
        }

    # 3. Helper to inline stylesheets into an HTML string
    def inline_assets(files: dict[str, bytes], html_file: str) -> str:
        raw_html = files.get(html_file, b"").decode("utf-8", errors="replace")

        # Replace <link ... href="..." ...> with inlined <style>
        def replace_link(match: re.Match[str]) -> str:
            full_tag = match.group(0)
            href_match = re.search(r"""href=['"]([^'"]+)['"]""", full_tag, re.IGNORECASE)
            if not href_match:
                return full_tag
            href = href_match.group(1).lstrip("./").strip()
            # Look up CSS in snapshot by relative path or filename
            css_bytes = files.get(href) or files.get(href.split("/")[-1])
            if css_bytes:
                css_str = css_bytes.decode("utf-8", errors="replace")
                return f"<style data-source='{href}'>\n{css_str}\n</style>"
            return full_tag

        inlined = re.sub(
            r"""<link\s+[^>]*?rel=['"]stylesheet['"][^>]*?>""",
            replace_link,
            raw_html,
            flags=re.IGNORECASE,
        )
        # Also catch <link href="..." rel="stylesheet">
        inlined = re.sub(
            r"""<link\s+[^>]*?href=['"][^'"]+\.css['"][^>]*?>""",
            replace_link,
            inlined,
            flags=re.IGNORECASE,
        )

        # Inject base href or viewport if missing
        if "<head>" in inlined and "viewport" not in inlined.lower():
            inlined = inlined.replace(
                "<head>",
                "<head>\n<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
                1,
            )

        return inlined

    html_after = inline_assets(patched_snapshot, entrypoint)
    html_before = inline_assets(original_snapshot, entrypoint)

    return {
        "has_preview": True,
        "entrypoint": entrypoint,
        "html_after": html_after,
        "html_before": html_before,
        "files_count": len(patched_snapshot),
    }
