# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Markdown section-chunking helpers — single-sourced (Issue #12663).

Previously duplicated verbatim across two entrypoints:
  - autobot-backend/services/knowledge/doc_indexer.py (async service, #1385)
  - autobot-infrastructure/shared/tools/index_documentation.py (standalone CLI, #250)

Both entrypoints chunk markdown by H2/H3 section boundaries the same way; only
the surrounding orchestration (async vs sync, ChromaDB client wiring, doc-type
inference) legitimately differs between the service and the CLI. This module
has zero AutoBot-specific dependencies (stdlib only) so it can be imported by
the standalone CLI without pulling in the full backend dependency graph.
"""

import re
from typing import Any, Dict, List


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
) -> None:
    """Split large content into paragraph-based chunks (~800 tokens)."""
    paragraphs = full_content.split("\n\n")
    current_chunk: List[str] = []
    current_size = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        if current_size + para_tokens > 800 and current_chunk:
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
