# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Visibility of knowledge summaries (#16665).

A summary carries no owner of its own: it derives from a source document (its ``document_id``),
so it is readable exactly when that source fact is. The decision is the canonical one
(:func:`knowledge.search_filters.filter_for_user_id`) applied to the source fact's metadata.
It fails closed: a summary whose source fact cannot be found is withheld, and so is one whose source is
research-quarantined. Temporal events derive from a source document the same way (:func:`visible_events`).
"""

import asyncio
from typing import Any, Callable, Dict, List

from knowledge.quarantine import is_quarantined
from knowledge.search_filters import KbReader, filter_for_user_id


def _source_metadata(kb, document_id: str) -> Dict[str, Any] | None:
    fact = kb.get_fact(document_id) if document_id else None
    return (fact or {}).get("metadata") or None


async def visible_by_source(
    items: List[dict], kb, reader: KbReader, document_id_of: Callable[[dict], Any]
) -> List[dict]:
    """*items* whose source fact *reader* may read; an unresolvable or quarantined source drops the item (#16665)."""
    sources: Dict[str, Dict[str, Any] | None] = {}
    candidates = []
    for item in items:
        document_id = str(document_id_of(item) or "")
        if document_id not in sources:
            sources[document_id] = await asyncio.to_thread(_source_metadata, kb, document_id)
        if sources[document_id] and not is_quarantined({"metadata": sources[document_id]}):
            candidates.append({"id": item.get("id", ""), "metadata": sources[document_id], "item": item})
    kept = await filter_for_user_id(candidates, kb, reader)
    return [c["item"] for c in kept]


async def visible_summaries(summaries: List[dict], kb, reader: KbReader) -> List[dict]:
    """*summaries* whose source fact *reader* may read; the rest, and any with no resolvable source, are dropped."""
    return await visible_by_source(summaries, kb, reader, lambda s: (s.get("metadata") or {}).get("document_id"))


async def visible_events(events: List[dict], kb, reader: KbReader) -> List[dict]:
    """Temporal *events* whose source document *reader* may read (#16665); an event carries no owner of its own."""
    return await visible_by_source(events, kb, reader, lambda e: e.get("source_document_id"))


async def document_is_visible(document_id: str, kb, reader: KbReader) -> bool:
    """Whether *reader* may read the source fact of *document_id*."""
    probe = [{"metadata": {"document_id": document_id}}]
    return bool(await visible_summaries(probe, kb, reader))
