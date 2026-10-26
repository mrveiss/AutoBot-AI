# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Visibility of knowledge summaries (#16665).

A summary carries no owner of its own: it derives from a source document (its ``document_id``),
so it is readable exactly when that source fact is. The decision is the canonical one
(:func:`knowledge.search_filters.filter_for_user_id`) applied to the source fact's metadata.
It fails closed: a summary whose source fact cannot be found is withheld.
"""

import asyncio
from typing import Any, Dict, List

from knowledge.search_filters import KbReader, filter_for_user_id


def _source_metadata(kb, document_id: str) -> Dict[str, Any] | None:
    fact = kb.get_fact(document_id) if document_id else None
    return (fact or {}).get("metadata") or None


async def visible_summaries(summaries: List[dict], kb, reader: KbReader) -> List[dict]:
    """*summaries* whose source fact *reader* may read; the rest, and any with no resolvable source, are dropped."""
    sources: Dict[str, Dict[str, Any] | None] = {}
    candidates = []
    for summary in summaries:
        document_id = str((summary.get("metadata") or {}).get("document_id") or "")
        if document_id not in sources:
            sources[document_id] = await asyncio.to_thread(_source_metadata, kb, document_id)
        if sources[document_id]:
            candidates.append({"id": summary.get("id", ""), "metadata": sources[document_id], "summary": summary})
    kept = await filter_for_user_id(candidates, kb, reader)
    return [c["summary"] for c in kept]


async def document_is_visible(document_id: str, kb, reader: KbReader) -> bool:
    """Whether *reader* may read the source fact of *document_id*."""
    probe = [{"metadata": {"document_id": document_id}}]
    return bool(await visible_summaries(probe, kb, reader))
