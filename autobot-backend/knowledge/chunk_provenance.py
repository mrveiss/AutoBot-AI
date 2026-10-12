# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-chunk page provenance for chunked documents (#18407).

``page_spans`` is recorded as offsets into the *whole* stored text. Once the text
is split, a chunk must carry only the pages it covers, with offsets re-based to
the chunk -- otherwise a citation points at the wrong place.
"""

from typing import Any, Dict, List, Optional, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def locate_chunks(text: str, chunks: List[str]) -> List[Optional[Tuple[int, int]]]:
    """``[start, end)`` of each chunk in *text*, or ``None`` where it cannot be located.

    Chunks are whitespace-normalised pieces of the text in order, so each is located by
    walking its words forward from the end of the previous chunk.
    """
    offsets: List[Optional[Tuple[int, int]]] = []
    cursor = 0
    for chunk in chunks:
        pos, start = cursor, None
        for word in chunk.split():
            found = text.find(word, pos)
            if found < 0:
                start = None
                break
            start = found if start is None else start
            pos = found + len(word)
        if start is None:
            offsets.append(None)
            continue
        offsets.append((start, pos))
        cursor = pos
    return offsets


def _rebase(spans: List[Dict[str, int]], start: int, end: int) -> List[Dict[str, int]]:
    return [
        {"page": s["page"], "start": max(s["start"], start) - start, "end": min(s["end"], end) - start}
        for s in spans
        if s["start"] < end and s["end"] > start
    ]


def chunk_page_metadata(metadata: Dict[str, Any], offsets: Optional[Tuple[int, int]]) -> Dict[str, Any]:
    """Copy of *metadata* whose page provenance describes just the chunk at *offsets*.

    A chunk that cannot be located gets no page provenance rather than a wrong one.
    """
    if "page_spans" not in metadata:
        return dict(metadata)
    out = {k: v for k, v in metadata.items() if k not in ("page_spans", "pages_with_text")}
    if offsets is None:
        logger.warning("chunk could not be located in the document text; page_spans omitted for it")
        return out
    spans = _rebase(metadata["page_spans"], *offsets)
    out["page_spans"] = spans
    out["pages_with_text"] = sorted({s["page"] for s in spans})
    return out
