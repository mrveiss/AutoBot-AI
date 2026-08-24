# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical document text extraction (#13893).

Five independent PDF extractors existed before this module: the knowledge-base
upload endpoint, the media document pipeline, the Drive/OneDrive connectors, and
two fully orphaned helpers. Three were live, they disagreed on page markers, and
one still ran the unmaintained ``PyPDF2`` while the repo pins ``pypdf`` as a
security update. Every fix to the document path had to ship five times.

This module is the single implementation. Callers adapt its result to their own
error shape — an ``HTTPException`` for the API, a ``ProcessingResult`` for the
media pipeline, an empty string for the connectors — but nobody re-implements the
extraction itself.

Page text is kept **structured** rather than pre-joined. Callers that need a flat
string call :func:`render_pages`; callers that need per-page provenance read
``pages`` directly. That split is what lets page numbers reach retrieval as
metadata instead of as marker text baked into the embedding (#13894).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# The one page-marker convention. Three different ones existed across the forks
# (``## Page N``, ``--- Page N ---``, and none at all on the live upload path).
PAGE_MARKER_TEMPLATE = "## Page {number}"

_PDF_MAGIC = b"%PDF"
_ZIP_MAGIC = b"PK"
_DOCX_MARKER = b"word/"
_DOCX_SNIFF_BYTES = 2000


class DocumentExtractionError(Exception):
    """Raised when a document cannot be parsed.

    Callers map this to their own failure shape. It deliberately does not carry
    an HTTP status or a pipeline result — the core has no opinion about how a
    caller reports failure.
    """


class DocumentDependencyError(DocumentExtractionError):
    """Raised when the parsing library for a format is not installed.

    Kept distinct from a parse failure because the two need different responses:
    a corrupt file is the user's problem, a missing library is ours. The media
    pipeline reports this as ``unavailable`` rather than ``error`` so a
    deployment gap cannot be mistaken for a bad upload.
    """


@dataclass(frozen=True)
class PageText:
    """Text recovered from a single page, 1-indexed to match human page numbers."""

    number: int
    text: str


@dataclass(frozen=True)
class ExtractedDocument:
    """Structured result of a document extraction."""

    format: str
    text: str
    pages: Tuple[PageText, ...] = ()
    page_count: int | None = None
    tables: Tuple[Any, ...] = ()
    info: Mapping[str, str] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        """Number of characters of recovered text."""
        return len(self.text)

    @property
    def has_text(self) -> bool:
        """Whether any non-whitespace text was recovered.

        A PDF whose pages carry no text layer extracts to ``""`` rather than
        failing, so emptiness is a normal result that callers must check — it is
        the signal a scanned document needs OCR (#13884, #13896).
        """
        return bool(self.text.strip())


def render_pages(pages: Sequence[PageText], marker: str = PAGE_MARKER_TEMPLATE) -> str:
    """Join pages into one string, prefixing each with the canonical marker.

    Pages with no recovered text are skipped so a scanned page does not emit a
    bare marker with nothing under it.
    """
    parts = []
    for page in pages:
        if page.text.strip():
            parts.append(f"{marker.format(number=page.number)}\n{page.text}")
    return "\n\n".join(parts)


def detect_format(raw: bytes, mime_type: str = "") -> str:
    """Detect document format from magic bytes, falling back to MIME type."""
    mime = (mime_type or "").lower()
    if raw[:4] == _PDF_MAGIC:
        return "pdf"
    if raw[:2] == _ZIP_MAGIC and _DOCX_MARKER in raw[:_DOCX_SNIFF_BYTES]:
        return "docx"
    if "pdf" in mime:
        return "pdf"
    if "docx" in mime or "officedocument.wordprocessingml" in mime:
        return "docx"
    return "text"


def extract_pdf(raw: bytes) -> ExtractedDocument:
    """Extract the text layer from a PDF.

    A page whose text layer is absent contributes an empty :class:`PageText`
    rather than being dropped, so ``page_count`` stays truthful and a caller can
    tell *which* pages were unreadable.
    """
    reader = _pdf_reader(raw)
    pages = tuple(PageText(number=n, text=_pdf_page_text(page, n)) for n, page in enumerate(reader.pages, start=1))
    info = reader.metadata or {}
    return ExtractedDocument(
        format="pdf",
        text=render_pages(pages),
        pages=pages,
        page_count=len(pages),
        info=_pdf_info(info),
    )


def _pdf_reader(raw: bytes) -> Any:
    """Build a pypdf reader, translating library failures to our own error."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise DocumentDependencyError("PDF support requires the pypdf library") from exc

    try:
        return PdfReader(io.BytesIO(raw))
    except Exception as exc:
        raise DocumentExtractionError(f"Failed to parse PDF: {exc}") from exc


def _pdf_page_text(page: Any, number: int) -> str:
    """Extract one page, degrading to empty text rather than failing the document."""
    try:
        return page.extract_text() or ""
    except Exception as exc:
        logger.warning("Failed to extract text from PDF page %s: %s", number, exc)
        return ""


def _pdf_info(info: Mapping[str, Any]) -> Dict[str, str]:
    """Normalize pypdf's slash-prefixed metadata keys."""
    return {
        "title": str(info.get("/Title", "") or ""),
        "author": str(info.get("/Author", "") or ""),
        "subject": str(info.get("/Subject", "") or ""),
        "creator": str(info.get("/Creator", "") or ""),
    }


def extract_docx(raw: bytes) -> ExtractedDocument:
    """Extract paragraphs, tables and core properties from a DOCX."""
    try:
        from docx import Document as DocxDocument
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise DocumentDependencyError("DOCX support requires the python-docx library") from exc

    try:
        doc = DocxDocument(io.BytesIO(raw))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        tables = tuple(_docx_table(table) for table in doc.tables)
    except Exception as exc:
        raise DocumentExtractionError(f"Failed to parse DOCX: {exc}") from exc

    return ExtractedDocument(
        format="docx",
        text="\n".join(paragraphs),
        tables=tables,
        info=_docx_info(doc),
    )


def _docx_table(table: Any) -> List[List[str]]:
    """Render one DOCX table as rows of cell strings."""
    return [[cell.text.strip() for cell in row.cells] for row in table.rows]


def _docx_info(doc: Any) -> Dict[str, str]:
    """Read DOCX core properties, tolerating documents that carry none."""
    try:
        props = doc.core_properties
        return {
            "title": props.title or "",
            "author": props.author or "",
            "subject": props.subject or "",
            "keywords": props.keywords or "",
        }
    except Exception:
        return {}


def extract_plain_text(raw: bytes) -> ExtractedDocument:
    """Decode a plain-text document as UTF-8, falling back to latin-1."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")
    return ExtractedDocument(format="text", text=text)


def extract_document(raw: bytes, mime_type: str = "") -> ExtractedDocument:
    """Detect the format and extract, dispatching to the format-specific reader."""
    detected = detect_format(raw, mime_type)
    if detected == "pdf":
        return extract_pdf(raw)
    if detected == "docx":
        return extract_docx(raw)
    return extract_plain_text(raw)


def strip_page_markers(text: str, marker: str = PAGE_MARKER_TEMPLATE) -> str:
    """Remove canonical page markers from rendered text.

    Consumers that want prose without structural markers — an embedding input,
    for instance — use this rather than re-extracting with a different renderer.
    """
    pattern = re.escape(marker).replace(r"\{number\}", r"\d+")
    return re.sub(rf"^{pattern}\n?", "", text, flags=re.MULTILINE)
