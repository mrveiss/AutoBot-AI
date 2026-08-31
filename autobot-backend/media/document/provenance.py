# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Page-offset lookups and table rendering built on the canonical extractor.

Split out of ``media/document/extraction.py`` (#14970) once folding tables into
ingest text pushed that module over ``MAX_LINES``. ``PageSpan`` and
``render_plain`` stayed in ``extraction.py`` — ``knowledge/api.py`` imports
``render_plain`` directly, and moving it would have meant touching that file's
functions, several of which are already over the function-length ceiling from
unrelated debt. Everything here is a pure consumer of ``extraction.py``'s
``PageSpan``/``ExtractedDocument``, never the reverse, so the split carries no
circular import.

``render_tables``/``render_text_and_tables`` (#14970) are the one table
renderer every table-bearing ingest consumer shares, instead of each inventing
its own join the way PDF (dropped tables outright) and DOCX (forked its own
pipe-join) used to. ``page_for_offset``/``pages_for_span``/``chunk_page_map``
resolve a ``render_plain`` offset or a chunk back to the page(s) it came from.
"""

from __future__ import annotations

import re
from typing import List, Sequence, Tuple

from autobot_shared.env_utils import blank_to_none
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from media.document.extraction import PAGE_MARKER_TEMPLATE, ExtractedDocument, PageSpan

logger = get_logger(__name__)

# The one table-section marker (#14970). ``document_parser.py``'s DOCX path
# already used this exact heading; every other table-bearing consumer adopts it
# rather than inventing its own.
TABLE_SECTION_MARKER = "--- Tables ---"


def strip_page_markers(text: str, marker: str = PAGE_MARKER_TEMPLATE) -> str:
    """Remove canonical page markers from rendered text.

    Consumers that want prose without structural markers — an embedding input,
    for instance — use this rather than re-extracting with a different renderer.
    """
    pattern = re.escape(marker).replace(r"\{number\}", r"\d+")
    return re.sub(rf"^{pattern}\n?", "", text, flags=re.MULTILINE)


def page_for_offset(spans: Sequence[PageSpan], offset: int) -> int | None:
    """Return the page number containing *offset*, or ``None`` if outside them all.

    An offset landing in the separator between two pages belongs to neither; the
    caller decides what that means rather than being handed a silent guess.
    """
    for span in spans:
        if span.start <= offset < span.end:
            return span.number
    return None


def pages_for_span(spans: Sequence[PageSpan], start: int, end: int) -> Tuple[int, ...]:
    """Return every page number a ``[start, end)`` range touches.

    A chunk that straddles a page break genuinely comes from two pages. Reporting
    only the first would silently mis-cite half its content, so this returns the
    range and lets the caller record it.
    """
    if end <= start:
        return ()
    return tuple(span.number for span in spans if span.start < end and start < span.end)


def chunk_page_map(spans: Sequence[PageSpan], chunks: Sequence[str], text: str) -> Tuple[Tuple[int, ...], ...]:
    """Map each chunk of *text* to the page numbers it came from.

    Chunkers return strings, not offsets, so the offsets are recovered by
    scanning forward through *text*. Searching forward from the previous chunk's
    end — rather than with :meth:`str.find` from zero — keeps repeated boilerplate
    (headers, footers, recurring table scaffolding) from collapsing every
    occurrence onto the first page it appeared on.
    """
    result: List[Tuple[int, ...]] = []
    cursor = 0
    for chunk in chunks:
        if not chunk:
            result.append(())
            continue
        start = text.find(chunk, cursor)
        if start < 0:
            # The chunker transformed the text (trimmed, normalized whitespace),
            # so offsets cannot be recovered for this chunk. Report nothing
            # rather than a wrong page.
            result.append(())
            continue
        end = start + len(chunk)
        result.append(pages_for_span(spans, start, end))
        cursor = end
    return tuple(result)


DEFAULT_MAX_TABLE_CHARS = 20_000


def max_table_chars() -> int:
    """Resolve the rendered-table-text size bound from config (#14970).

    Cell-by-cell rendering of a table-dense document (invoices, financial
    statements) can produce far more text than the page count suggests. This
    bounds the *rendered* text the same way ``max_table_pages`` (in
    ``extraction.py``) bounds the *extraction* work, so one document cannot
    dominate chunk volume.
    """
    raw = blank_to_none(config.misc.document_max_table_chars)
    if raw is None:
        return DEFAULT_MAX_TABLE_CHARS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "AUTOBOT_DOCUMENT_MAX_TABLE_CHARS=%r is not an integer; using %d",
            raw,
            DEFAULT_MAX_TABLE_CHARS,
        )
        return DEFAULT_MAX_TABLE_CHARS
    if value <= 0:
        logger.warning(
            "AUTOBOT_DOCUMENT_MAX_TABLE_CHARS=%d is not positive; using %d",
            value,
            DEFAULT_MAX_TABLE_CHARS,
        )
        return DEFAULT_MAX_TABLE_CHARS
    return value


def render_tables(tables: Sequence[Sequence[Sequence[str]]]) -> str:
    """Render extracted tables as pipe-joined rows, identical for every format.

    ``_pdf_tables``/``_normalize_table`` and ``_docx_table`` (both in
    ``extraction.py``) already agree on shape (a tuple of tables, each a list
    of rows, each row a list of cell strings) — this is the one place that
    turns that shape into text, so a consumer no longer invents its own join
    (#14970). Rows with no non-blank cell are dropped; the whole result is
    bounded by :func:`max_table_chars`.
    """
    if not tables:
        return ""
    rendered_tables = []
    for table in tables:
        rows = [" | ".join(row) for row in table if any(cell.strip() for cell in row)]
        if rows:
            rendered_tables.append("\n".join(rows))
    rendered = "\n\n".join(rendered_tables)
    limit = max_table_chars()
    if len(rendered) > limit:
        logger.warning("Rendered table text truncated from %d to %d characters (#14970)", len(rendered), limit)
        rendered = rendered[:limit]
    return rendered


def render_text_and_tables(document: ExtractedDocument) -> str:
    """Fold a document's tables into its flattened text, once.

    PDF dropped tables outright and DOCX forked its own join — this is the one
    place both go through, so identical tables produce identical text down
    every ingest path (#14970). The page-marker text stays untouched: this
    only appends a table section, never wraps ``ExtractedDocument.text``.
    """
    table_text = render_tables(document.tables)
    if not table_text:
        return document.text
    if document.text.strip():
        return f"{document.text}\n\n{TABLE_SECTION_MARKER}\n{table_text}"
    return f"{TABLE_SECTION_MARKER}\n{table_text}"
