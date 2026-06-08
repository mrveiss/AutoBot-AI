# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
web_fetch.ingest — Optional KB ingest wrapper for scraped web content.

Issue #7401: Scrape-consolidation layer.

When a caller passes ``ingest=True`` to ``POST /knowledge/scrape``, this
module indexes the fetched markdown into ChromaDB via DocIndexerService.
The wrapper is deliberately thin: it delegates all chunking, embedding, and
collision-detection to DocIndexerService._index_file_chunks so we never
duplicate that logic.
"""

from __future__ import annotations

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def ingest_markdown(
    url: str,
    markdown: str,
    title: str = "",
) -> bool:
    """Index ``markdown`` text into ChromaDB under the given ``url`` key.

    Args:
        url:      Source URL — used as the ``rel_path`` identifier in the chunk
                  metadata so search results can link back to the origin.
        markdown: Markdown content to chunk and embed.
        title:    Optional page title for metadata enrichment.

    Returns:
        True when at least one chunk was successfully stored, False otherwise.

    The function is intentionally fire-and-continue: any ChromaDB errors are
    logged at WARNING level and ``False`` is returned — the scrape response
    still succeeds so the caller gets the markdown even when ingest fails.
    """
    if not markdown or not markdown.strip():
        logger.warning("ingest_markdown: empty content for %s, skipping", url)
        return False

    try:
        from services.knowledge.doc_indexer import get_doc_indexer_service

        indexer = get_doc_indexer_service()
        if not indexer._initialized:
            await indexer.initialize()

        # Build a synthetic rel_path that identifies the scraped URL as a source.
        # The path is URL-derived so it sorts sensibly in search metadata.
        rel_path = _url_to_rel_path(url)

        content = _prepend_title(markdown, title)
        indexed, total = await indexer._index_file_chunks(
            file_str=url,
            content=content,
            rel_path=rel_path,
            tier=3,
        )
        logger.info(
            "ingest_markdown: indexed %d/%d chunks for %s",
            indexed,
            total,
            url,
        )
        return indexed > 0

    except Exception as exc:
        logger.warning("ingest_markdown failed for %s: %s", url, exc)
        return False


def _url_to_rel_path(url: str) -> str:
    """Convert a URL into a stable relative-path identifier for chunk metadata.

    Example: ``https://docs.example.com/guide`` → ``web/docs.example.com/guide``
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.netloc or "unknown"
    path = (parsed.path or "").strip("/") or "index"
    return f"web/{host}/{path}"


def _prepend_title(markdown: str, title: str) -> str:
    """Prepend an H1 title to markdown when one is provided and not already present."""
    if not title:
        return markdown
    if markdown.startswith("# "):
        return markdown
    return f"# {title}\n\n{markdown}"
