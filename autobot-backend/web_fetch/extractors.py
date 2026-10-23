# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
web_fetch.extractors — SPA detection and schema-driven extraction over fetched pages.

Issue #7400: Foundation package for unified web search/scrape/crawl.
Issue #7405: Schema-driven structured data extraction via LLM.
Issue #18826: HTML-to-text conversion moved out. Every HTML ingest path goes
through :func:`web_fetch.profile.extract_page`, which produces the canonical
``ExtractedDocument`` (:mod:`media.document.html_extraction`). The markdownify
conversion and its BS4 fallback that lived here are gone with their callers.

Never re-implements SSRF guards or Jina logic — those live in media/link/pipeline.py.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from media.document.html_extraction import CHROME_TAGS, INERT_TAGS

logger = get_logger(__name__)

# SPA detection markers — pages dominated by these patterns require JS rendering.
_SPA_MARKERS = (
    "loading...",
    "please enable javascript",
    "you need to enable javascript",
    "javascript is required",
    "this page requires javascript",
)

_MIN_CONTENT_CHARS = 500  # Minimum markdown length to consider a fetch successful.


def _strip_boilerplate(soup) -> None:
    """Remove non-content tags in-place: the inert ones plus page chrome."""
    for tag in soup(list(INERT_TAGS + CHROME_TAGS)):
        tag.decompose()


def is_spa_content(markdown: str, html: str = "") -> bool:
    """Return True when content signals a JS-rendered SPA shell.

    A page is considered a SPA shell when SPA marker strings are present
    in the content OR when the HTML body is empty / noscript-dominated.
    Mere shortness alone is not sufficient — very short but marker-free
    pages (e.g. tiny landing pages) are served as-is.
    """
    lower_md = markdown.lower()
    if any(marker in lower_md for marker in _SPA_MARKERS):
        return True

    if html:
        lower_html = html.lower()
        if any(marker in lower_html for marker in _SPA_MARKERS):
            return True
        if _is_noscript_dominated(html):
            return True

    return False


def _is_noscript_dominated(html: str) -> bool:
    """Return True when noscript tags contain significantly more text than body."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        noscript_text = " ".join(t.get_text() for t in soup.find_all("noscript"))
        _strip_boilerplate(soup)
        body = soup.find("body")
        body_text = body.get_text(strip=True) if body else ""
        if not body_text:
            return True
        return len(noscript_text) > len(body_text) * 0.5
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Issue #7405 — Schema-driven structured data extraction
# ---------------------------------------------------------------------------

_SCRIPT_BLOCK_RE = re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)


def _strip_script_blocks(markdown: str) -> str:
    """Remove <script>...</script> blocks from markdown (prompt-injection guard)."""
    return _SCRIPT_BLOCK_RE.sub("", markdown).strip()


async def extract_url(
    url: str,
    schema: Dict[str, Any],
    render: str = "auto",
) -> Dict[str, Any]:
    """Fetch *url*, strip script blocks, call LLM to extract structured data.

    Delegates the LLM call, JSON parsing, retry logic, and schema validation to
    ``llm_shared.structured_ops.extract`` (Issue #11520).

    Deliberate behavior change vs the pre-#11520 implementation: LLM output
    wrapped in markdown code fences is now tolerated (previously a hard parse
    failure), and invalid JSON triggers up to ``EXTRACT_MAX_RETRIES`` retries
    with the error fed back to the model.

    Args:
        url:    Absolute URL to fetch.
        schema: JSON Schema (draft 2020-12) dict describing the desired output.
        render: Render mode — "auto" | "fast" | "playwright".

    Returns:
        ``{"url": str, "data": dict, "schema_valid": True}``

    Raises:
        RuntimeError:  Fetch failed (caller maps to 502).
        ValueError:    LLM returned invalid JSON or data fails schema (caller maps to 422).
    """
    from llm_shared.structured_ops import ExtractionError, extract
    from web_fetch import FetchResult, RenderMode, WebFetcher

    render_mode = RenderMode(render)
    result: FetchResult = await WebFetcher.fetch(url, render=render_mode)
    if not result.success:
        raise RuntimeError(result.error_code or "fetch_failed")

    safe_markdown = _strip_script_blocks(result.markdown or "")

    # #10552: inspect web content through the content firewall before it reaches the LLM
    from security.content_firewall import ContentSource, get_content_firewall

    fw_verdict = await get_content_firewall().inspect(safe_markdown, source=ContentSource.WEB, context_label=url)
    if fw_verdict.blocked:
        raise RuntimeError(f"web_content_blocked_by_firewall: risk={fw_verdict.risk.value}")
    safe_markdown = fw_verdict.content

    try:
        data = await extract(safe_markdown, schema)
    except ExtractionError as exc:
        raise ValueError(str(exc)) from exc

    return {"url": result.url, "data": data, "schema_valid": True}
