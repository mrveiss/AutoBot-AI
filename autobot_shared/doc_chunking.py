# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Markdown section-chunking helpers — single-sourced (Issue #12663).

Previously duplicated verbatim across two entrypoints; the standalone CLI was
retired into a shim over the service (#18129), so the one consumer is:
  - autobot-backend/services/knowledge/doc_indexer.py (async service, #1385)
 This module
has zero AutoBot-specific dependencies (stdlib only) so it can be imported by
the standalone CLI without pulling in the full backend dependency graph.
"""

import re
from typing import Any, Dict, List

DEFAULT_CHUNK_MAX_TOKENS = 800
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def estimate_tokens(text: str) -> int:
    """Estimate token count (~4 chars per token)."""
    return len(text) // 4


def create_chunk(
    content: str,
    section: str,
    subsection: str | None,
    file_path: str,
    doc_type: str,
    category: str,
    title: str,
) -> Dict[str, Any]:
    """Create a chunk dictionary with metadata."""
    return {
        "content": content,
        "section": section,
        "subsection": subsection,
        "file_path": file_path,
        "doc_type": doc_type,
        "category": category,
        "title": title,
    }


def chunk_large_content(
    full_content: str,
    section_name: str,
    subsection_name: str | None,
    file_path: str,
    doc_type: str,
    category: str,
    doc_title: str,
    chunks: List[Dict[str, Any]],
    max_tokens: int = DEFAULT_CHUNK_MAX_TOKENS,
) -> None:
    """Split large content into paragraph-based chunks (~``max_tokens`` tokens)."""
    paragraphs = full_content.split("\n\n")
    current_chunk: List[str] = []
    current_size = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        if current_size + para_tokens > max_tokens and current_chunk:
            chunks.append(
                create_chunk(
                    "\n\n".join(current_chunk),
                    section_name,
                    subsection_name,
                    file_path,
                    doc_type,
                    category,
                    doc_title,
                )
            )
            current_chunk = [para]
            current_size = para_tokens
        else:
            current_chunk.append(para)
            current_size += para_tokens

    if current_chunk:
        chunks.append(
            create_chunk(
                "\n\n".join(current_chunk),
                section_name,
                subsection_name,
                file_path,
                doc_type,
                category,
                doc_title,
            )
        )


def process_h3_subsections(
    h3_splits: list,
    section_name: str,
    file_path: str,
    doc_type: str,
    category: str,
    doc_title: str,
    chunks: List[Dict[str, Any]],
) -> None:
    """Process H3 subsections within an H2 section. Helper for chunk_markdown (#1385/#250)."""
    j = 1
    while j < len(h3_splits):
        h3_header = h3_splits[j].strip() if j < len(h3_splits) else ""
        h3_content = h3_splits[j + 1].strip() if j + 1 < len(h3_splits) else ""
        j += 2

        h3_match = re.match(r"###\s+(.+)", h3_header)
        subsection_name = h3_match.group(1) if h3_match else "Subsection"

        full = f"## {section_name}\n\n### {subsection_name}\n\n{h3_content}"
        tokens = estimate_tokens(full)

        if tokens > 30:
            if tokens > 1000:
                chunk_large_content(
                    full,
                    section_name,
                    subsection_name,
                    file_path,
                    doc_type,
                    category,
                    doc_title,
                    chunks,
                )
            else:
                chunks.append(
                    create_chunk(
                        full,
                        section_name,
                        subsection_name,
                        file_path,
                        doc_type,
                        category,
                        doc_title,
                    )
                )


def process_h2_sections(
    h2_splits: list,
    file_path: str,
    doc_type: str,
    category: str,
    doc_title: str,
    chunks: List[Dict[str, Any]],
) -> None:
    """Process H2 sections and their H3 children. Helper for chunk_markdown (#1385/#250)."""
    i = 1
    while i < len(h2_splits):
        h2_header = h2_splits[i].strip() if i < len(h2_splits) else ""
        h2_content = h2_splits[i + 1].strip() if i + 1 < len(h2_splits) else ""
        i += 2

        h2_match = re.match(r"##\s+(.+)", h2_header)
        section_name = h2_match.group(1) if h2_match else "Section"

        h3_splits = re.split(r"^(###\s+.+)$", h2_content, flags=re.MULTILINE)
        h2_intro = h3_splits[0].strip() if h3_splits else ""

        if h2_intro and estimate_tokens(h2_intro) > 30:
            chunks.append(
                create_chunk(
                    f"## {section_name}\n\n{h2_intro}",
                    section_name,
                    None,
                    file_path,
                    doc_type,
                    category,
                    doc_title,
                )
            )

        process_h3_subsections(
            h3_splits,
            section_name,
            file_path,
            doc_type,
            category,
            doc_title,
            chunks,
        )


def _split_oversized(paragraph: str, max_tokens: int) -> List[str]:
    """Break one paragraph larger than the budget: sentences first, then word windows.

    ``chunk_large_content`` only splits *between* paragraphs, so a transcript
    that is a single unbroken block (#17830) would otherwise stay one chunk.
    """
    if estimate_tokens(paragraph) <= max_tokens:
        return [paragraph]
    pieces: List[str] = []
    for sentence in _SENTENCE_BOUNDARY.split(paragraph):
        if estimate_tokens(sentence) <= max_tokens:
            pieces.append(sentence)
            continue
        words = sentence.split()
        window = max(1, max_tokens * 4 // 6)  # ~6 chars per word incl. space
        pieces.extend(" ".join(words[i : i + window]) for i in range(0, len(words), window))
    return [part for piece in pieces for part in _hard_cap(piece, max_tokens)]


def _hard_cap(piece: str, max_tokens: int) -> List[str]:
    """Cut a piece that is still over budget (one token with no whitespace, e.g. base64) by characters."""
    limit = max(1, max_tokens * 4)
    if estimate_tokens(piece) <= max_tokens:
        return [piece]
    return [piece[i : i + limit] for i in range(0, len(piece), limit)]


def chunk_plain_text(text: str, max_tokens: int = DEFAULT_CHUNK_MAX_TOKENS) -> List[str]:
    """Split unstructured text (transcript, extracted PDF) into ~``max_tokens`` chunks.

    Reuses :func:`chunk_large_content` for the packing; only paragraphs larger
    than the whole budget are pre-split (sentences re-joined as paragraphs).
    Text within the budget is returned whole and unmodified.
    """
    if estimate_tokens(text) <= max_tokens:
        return [text]
    paragraphs = [p for para in text.split("\n\n") for p in _split_oversized(para, max_tokens)]
    chunks: List[Dict[str, Any]] = []
    chunk_large_content("\n\n".join(paragraphs), "", None, "", "", "", "", chunks, max_tokens=max_tokens)
    return [c["content"] for c in chunks if c["content"].strip()]
