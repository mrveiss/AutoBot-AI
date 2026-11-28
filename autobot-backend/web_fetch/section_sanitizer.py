# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Sanitize an extracted page's section contract, then render its text from it (#18826).

The sections are the cross-source contract the chunker consumes, so sanitizing only
the rendered ``text`` would leave the structure raw. Every text field passes through
:func:`knowledge.query_sanitizer.sanitize_document` exactly once: each section
``heading`` and ``heading_path`` entry, each block's ``text``, list-item texts, table
``header`` and cell texts, and link texts -- never a link's ``target``, which the
extractor already restricted to an absolute http(s)/mailto URL. ``text`` is then
:func:`render_sections` of the sanitized sections, so the two always agree.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Tuple

from knowledge.query_sanitizer import sanitize_document
from media.document.extraction import ExtractedDocument
from media.document.sections import Block, Section, render_sections

#: Metrics/log label of the sanitizer hits this seam records (link ingest's label before #18826).
SANITIZER_SOURCE = "web_html"


def sanitize_field(text: str) -> str:
    """One field through the canonical sanitizer; an empty field is not a call."""
    return sanitize_document(text, source=SANITIZER_SOURCE).sanitized_text if text else text


def _clean_all(texts: Tuple[str, ...]) -> Tuple[str, ...]:
    return tuple(sanitize_field(text) for text in texts)


def _block(block: Block) -> Block:
    return replace(
        block,
        text=sanitize_field(block.text),
        items=tuple(replace(item, text=sanitize_field(item.text)) for item in block.items),
        rows=tuple(_clean_all(row) for row in block.rows),
        header=_clean_all(block.header),
        links=tuple(replace(link, text=sanitize_field(link.text)) for link in block.links),
    )


def _section(section: Section) -> Section:
    return replace(
        section,
        heading=sanitize_field(section.heading),
        heading_path=_clean_all(section.heading_path),
        blocks=tuple(_block(block) for block in section.blocks),
    )


def sanitized_document(document: ExtractedDocument) -> ExtractedDocument:
    """*document* with sanitized sections and title, and ``text`` rendered from those sections."""
    sections = tuple(_section(section) for section in document.sections)
    title = sanitize_field(document.info.get("title", ""))
    return replace(document, sections=sections, text=render_sections(sections), info={**document.info, "title": title})
