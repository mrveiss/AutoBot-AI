# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
web_fetch.extractors — HTML-to-Markdown conversion helpers and schema-driven extraction.

Issue #7400: Foundation package for unified web search/scrape/crawl.
Issue #7405: Schema-driven structured data extraction via LLM.

Delegates to existing markdownify/BS4 patterns.  Never re-implements SSRF
guards or Jina logic — those live in media/link/pipeline.py.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Tuple

from autobot_shared.logging_manager import get_logger

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
    """Remove non-content tags in-place."""
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()


def _extract_title(soup) -> str:
    """Extract page title from og:title or <title>."""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()[:300]
    tag = soup.find("title")
    return tag.get_text(strip=True)[:300] if tag else ""


def _html_to_markdown_via_markdownify(html: str) -> str:
    """Convert HTML to markdown using markdownify library."""
    try:
        import markdownify

        return markdownify.markdownify(html, heading_style="ATX", strip=["script", "style"])
    except Exception as exc:
        logger.debug("markdownify conversion failed: %s", exc)
        return ""


def _html_to_plain_text_via_bs4(html: str) -> str:
    """Fallback: extract readable text from HTML using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        _strip_boilerplate(soup)
        main = soup.find("article") or soup.find("main") or soup.find("body")
        if main is None:
            return ""
        text = main.get_text(separator="\n", strip=True)
        return re.sub(r"\n{3,}", "\n\n", text).strip()
    except Exception as exc:
        logger.debug("bs4 text extraction failed: %s", exc)
        return ""


def extract_markdown(html: str) -> Tuple[str, str]:
    """Convert raw HTML to (title, markdown) using markdownify then BS4 fallback.

    Returns:
        Tuple of (title, markdown_content).
    """
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        title = _extract_title(soup)
    except Exception:
        title = ""

    md = _html_to_markdown_via_markdownify(html)
    if not md or len(md.strip()) < 100:
        md = _html_to_plain_text_via_bs4(html)

    return title, md.strip()


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


def _build_extraction_prompt(markdown: str, schema: Dict[str, Any]) -> str:
    """Build the LLM prompt for schema-driven extraction.

    The schema dict is JSON-serialised — never interpolated as raw string —
    to prevent schema-injection attacks.
    """
    schema_json = json.dumps(schema, ensure_ascii=False)
    return (
        "Extract structured data from the following web page content.\n"
        "Return ONLY a valid JSON object that conforms to this JSON Schema:\n\n"
        f"```json\n{schema_json}\n```\n\n"
        "Page content:\n\n"
        f"{markdown}\n\n"
        "Respond with only the JSON object, no explanation or markdown fences."
    )


async def _call_llm_for_extraction(prompt: str) -> str:
    """Call the LLM gateway with structured-output mode and return raw content."""
    from llm_shared.types import LLMType
    from services.llm_service import get_llm_service

    svc = get_llm_service()
    response = await svc.chat(
        messages=[{"role": "user", "content": prompt}],
        llm_type=LLMType.EXTRACTION,
        structured_output=True,
    )
    if response.error:
        raise RuntimeError(f"LLM extraction failed: {response.error}")
    return response.content


def _validate_against_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> None:
    """Validate *data* against *schema* using Draft202012Validator.

    Raises jsonschema.ValidationError on failure.
    """
    import jsonschema

    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(data)


async def extract_url(
    url: str,
    schema: Dict[str, Any],
    render: str = "auto",
) -> Dict[str, Any]:
    """Fetch *url*, strip script blocks, call LLM to extract structured data.

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
    from web_fetch import FetchResult, RenderMode, WebFetcher

    render_mode = RenderMode(render)
    result: FetchResult = await WebFetcher.fetch(url, render=render_mode)
    if not result.success:
        raise RuntimeError(result.error_code or "fetch_failed")

    safe_markdown = _strip_script_blocks(result.markdown or "")

    # #10552: inspect web content through the content firewall before it reaches the LLM
    from security.content_firewall import ContentSource, get_content_firewall

    fw_verdict = await get_content_firewall().inspect(
        safe_markdown, source=ContentSource.WEB, context_label=url
    )
    if fw_verdict.blocked:
        raise RuntimeError(f"web_content_blocked_by_firewall: risk={fw_verdict.risk.value}")
    safe_markdown = fw_verdict.content

    prompt = _build_extraction_prompt(safe_markdown, schema)
    raw = await _call_llm_for_extraction(prompt)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned non-JSON output: {exc}") from exc

    try:
        _validate_against_schema(data, schema)
    except Exception as exc:
        raise ValueError(str(exc)) from exc

    return {"url": result.url, "data": data, "schema_valid": True}
