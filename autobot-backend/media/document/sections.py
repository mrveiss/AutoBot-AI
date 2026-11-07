# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The section model: the cross-source contract of a canonical :class:`ExtractedDocument` (#18826, #18851).

Owner decision on #18826, option (a): document structure is part of the canonical
model and the text is rendered from it. Structural markdown is **not** the canonical
text format. Every producer -- HTML, DOCX, PDF, audio and the KB connectors -- emits
this one shape, and every consumer -- the section-aware chunker (#18856), the
structure-built graph (#18857) and the connector/audio producers (#18855) -- reads it.
**Consumers must not assume HTML**: a field a producer cannot fill keeps its default,
and nothing here is specific to one source format.

A document is an ordered tuple of :class:`Section`. Each has a heading level (1-6;
``0`` for content before the first heading), its heading text, its
:attr:`Section.heading_path`, an optional :class:`SourceSpan`, and its
:class:`Block` content: paragraphs, lists, tables (``header`` + ``rows``), code and
quotes. Link targets travel as :class:`Link` values on the block that carries them.

Which producer fills which field:

=====================  ====================================================
Field                  Producer
=====================  ====================================================
level, heading,        HTML (:mod:`media.document.html_extraction`) today;
heading_path, blocks   DOCX outline levels (#17985); connectors (#18855)
Block.header           HTML (``thead``, or a leading all-``th`` row); DOCX/PDF
                       tables and Jira/Notion tables when they know a header
Block.code_language    HTML (``class="language-x"``); Notion/Jira code blocks
SourceSpan.page_*      PDF and DOCX producers (1-based page numbers)
SourceSpan.time_*_s    audio/video producers (segment start/end in seconds)
=====================  ====================================================

HTML leaves every span ``None``: a web page has neither pages nor a timeline.

This module imports nothing from ``extraction.py`` at runtime, so
``extraction.py`` can name :class:`Section` in its dataclass without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


class BlockKind(str, Enum):
    """The block types a section may hold."""

    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    CODE = "code"
    QUOTE = "quote"


@dataclass(frozen=True)
class SourceSpan:
    """Where a section or block sits in its source; every field is optional.

    ``page_start``/``page_end`` are 1-based, inclusive page numbers, filled by the
    PDF and DOCX producers. ``time_start_s``/``time_end_s`` are offsets in seconds,
    filled by the audio/video producers from transcript segments. A producer whose
    source has neither (HTML) leaves the whole span ``None`` on the section/block.
    """

    page_start: Optional[int] = None
    page_end: Optional[int] = None
    time_start_s: Optional[float] = None
    time_end_s: Optional[float] = None


@dataclass(frozen=True)
class Link:
    """A hyperlink: its visible text and its absolute target."""

    text: str
    target: str


@dataclass(frozen=True)
class ListItem:
    """One list item; ``depth`` is 0 for a top-level item, 1 for a nested one, ..."""

    text: str
    depth: int = 0
    ordered: bool = False


@dataclass(frozen=True)
class Block:
    """One unit of section content.

    ``text`` holds a paragraph, quote or code body; ``items`` a list. A table is
    its ``header`` (the column-header cells, ``()`` when the source marks none) and
    its body ``rows``, each a tuple of cell strings -- the row shape
    ``ExtractedDocument.tables`` uses. ``code_language`` is the code block's
    declared language, metadata only and never part of ``text``. ``span`` locates
    the block in a paged or timed source; see :class:`SourceSpan`.
    """

    kind: BlockKind
    text: str = ""
    items: Tuple[ListItem, ...] = ()
    rows: Tuple[Tuple[str, ...], ...] = ()
    links: Tuple[Link, ...] = ()
    header: Tuple[str, ...] = ()
    code_language: Optional[str] = None
    span: Optional[SourceSpan] = None


@dataclass(frozen=True)
class Section:
    """A heading and the blocks under it, up to the next heading.

    ``heading_path`` is the producer-set chain of ancestor heading texts ending with
    this section's own heading, e.g. ``("Report", "Data", "Counts")``; it is ``()``
    for content before the first heading. Levels may skip (an ``h1`` then an
    ``h3``): the path holds the headings actually present, not one per level.
    ``span`` locates the section in a paged or timed source; see :class:`SourceSpan`.
    """

    level: int
    heading: str
    blocks: Tuple[Block, ...] = ()
    heading_path: Tuple[str, ...] = ()
    span: Optional[SourceSpan] = None


def _render_list(items: Sequence[ListItem]) -> str:
    """Render list items one per line, indented by depth, numbered when ordered."""
    counters: Dict[int, int] = {}
    lines: List[str] = []
    for item in items:
        counters = {depth: count for depth, count in counters.items() if depth <= item.depth}
        counters[item.depth] = counters.get(item.depth, 0) + 1
        marker = f"{counters[item.depth]}." if item.ordered else "-"
        lines.append(f"{'  ' * item.depth}{marker} {item.text}")
    return "\n".join(lines)


def render_block(block: Block) -> str:
    """Render one block as plain text; a table renders its header row first, then its body rows."""
    if block.kind is BlockKind.LIST:
        return _render_list(block.items)
    if block.kind is BlockKind.TABLE:
        # Local import: provenance imports extraction, which names Section.
        from media.document.provenance import render_tables

        head = [list(block.header)] if block.header else []
        return render_tables([head + [list(row) for row in block.rows]])
    return block.text


def render_sections(sections: Iterable[Section]) -> str:
    """Render sections as plain text: each heading on its own line, then its blocks."""
    parts: List[str] = []
    for section in sections:
        if section.heading:
            parts.append(section.heading)
        parts.extend(text for text in (render_block(block) for block in section.blocks) if text)
    return "\n\n".join(parts)
