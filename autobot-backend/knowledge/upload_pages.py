# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Page provenance for uploaded documents, computed from the text that is finally stored (#13894, #18407)."""

import dataclasses
from typing import TYPE_CHECKING, Callable, Tuple

if TYPE_CHECKING:
    from media.document.extraction import ExtractedDocument


def page_provenance_metadata(extracted: "ExtractedDocument | None") -> dict:
    """Page provenance for a stored fact, as metadata rather than marker text (#13894).

    Offsets are derived from the same pure ``render_plain`` call over the same
    pages that produced the stored content, so they index that exact string. A
    retrieved span resolves to a page via ``page_for_offset`` / ``pages_for_span``
    without the page number ever having entered the embedding.

    Returns an empty dict for unpaginated formats -- a DOCX has no pages, and
    inventing ``page: 1`` would be a fabricated citation.
    """
    if extracted is None or not extracted.pages:
        return {}

    from media.document.extraction import render_plain

    _text, spans = render_plain(extracted.pages)
    if not spans:
        return {}

    return {
        "page_count": extracted.page_count,
        "page_spans": [span.as_metadata() for span in spans],
        "pages_with_text": [span.number for span in spans],
    }


def clean_upload_text(
    content: str, extracted: "ExtractedDocument | None", clean: Callable[[str], str]
) -> Tuple[str, dict]:
    """Sanitise/redact *content* and return it with page provenance for the cleaned text.

    ``page_spans`` are offsets into the stored string, so they must be computed *after* cleaning:
    redaction and sanitising change lengths, and spans taken beforehand drift. A paginated PDF is
    therefore cleaned page by page and re-rendered, which fixes the final text and its spans together.
    """
    if extracted is None or extracted.format != "pdf" or not extracted.pages:
        return clean(content), page_provenance_metadata(extracted)

    from media.document.extraction import PageText, render_plain

    pages = [PageText(number=p.number, text=clean(p.text)) for p in extracted.pages]
    text, _spans = render_plain(pages)
    metadata = page_provenance_metadata(dataclasses.replace(extracted, pages=tuple(pages)))
    if metadata:
        metadata["page_count"] = extracted.page_count
    return text, metadata
