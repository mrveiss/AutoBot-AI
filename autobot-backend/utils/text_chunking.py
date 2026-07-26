#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Canonical paragraph-based text chunker.

Issue #12736 (fork-convergence D3, umbrella #12645): converges the
paragraph-splitting ``_chunk_text`` copies in
``knowledge/connectors/file_server.py`` and
``services/knowledge/cognition_seeder.py`` onto one parameterized
implementation. Every caller passes its own ``max_chars`` and flags so
output is byte-identical to the pre-convergence behavior.

Two other ``_chunk_text`` forks (``utils/payload_optimizer.py`` and
``knowledge/pipeline/extractors/semantic_chunker.py``) use genuinely
different algorithms (fixed-size sliding window with overlap, and
token-count-based segmentation with overlap-by-segment respectively)
and are intentionally NOT folded in here — see the PR description for
#12736 for the full rationale.
"""

from typing import List


def chunk_text(
    text: str,
    *,
    max_chars: int = 2000,
    separator_len: int = 0,
    split_oversized: bool = True,
    fallback_to_original: bool = False,
) -> List[str]:
    """Split *text* into paragraph-based chunks of at most *max_chars* chars.

    Args:
        text: Source text, paragraphs separated by blank lines (``\\n\\n``).
        max_chars: Maximum characters per chunk.
        separator_len: Extra chars reserved in the size check for the
            ``\\n\\n`` joiner between paragraphs already in the current
            chunk (0 = file_server semantics, 2 = cognition_seeder
            semantics).
        split_oversized: When True, a single paragraph longer than
            ``max_chars`` is hard-split into fixed-size pieces
            (file_server semantics). When False, an oversized paragraph
            becomes its own (over-limit) chunk instead of being split
            (cognition_seeder semantics).
        fallback_to_original: When True and no chunks were produced
            (empty/whitespace-only input), return ``[text]`` instead of
            ``[]`` (cognition_seeder semantics).

    Returns:
        List of chunk strings.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        prospective = current_len + (separator_len if current else 0) + len(para)
        if prospective > max_chars and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0

        if split_oversized and len(para) > max_chars:
            for i in range(0, len(para), max_chars):
                chunks.append(para[i : i + max_chars])
            continue

        current_len = len(para) if not current else current_len + separator_len + len(para)
        current.append(para)

    if current:
        chunks.append("\n\n".join(current))

    if not chunks and fallback_to_original:
        return [text]

    return chunks
