# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Visibility of knowledge summaries (#16665).

A summary carries no owner of its own: it derives from a source document (its ``document_id``),
so it is readable exactly when that source fact is. The decision is the canonical one
(:func:`knowledge.search_filters.filter_for_user_id`) applied to the source fact's metadata.
It fails closed: a summary whose source fact cannot be found is withheld. Temporal events derive from a
source document the same way (:func:`visible_events`) and, having no marker of their own, are also withheld
when the source is research-quarantined, for an admin too (as the summaries' own marker is).
"""

import asyncio
from typing import Any, Callable, Dict, List

from autobot_shared.env_utils import env_int_clamped
from knowledge.quarantine import is_quarantined
from knowledge.search_filters import KbReader, filter_for_user_id

#: How many source-fact lookups run at once for one visibility pass.
SOURCE_LOOKUP_CONCURRENCY = env_int_clamped("AUTOBOT_KB_SOURCE_LOOKUP_CONCURRENCY", 8, min_v=1)


def _source_metadata(kb, document_id: str) -> Dict[str, Any] | None:
    fact = kb.get_fact(document_id) if document_id else None
    return (fact or {}).get("metadata") or None


async def _source_map(kb, document_ids: List[str]) -> Dict[str, Dict[str, Any] | None]:
    """Source metadata per distinct document id; at most SOURCE_LOOKUP_CONCURRENCY lookups in flight at once."""
    gate = asyncio.Semaphore(SOURCE_LOOKUP_CONCURRENCY)

    async def one(document_id: str):
        async with gate:
            return await asyncio.to_thread(_source_metadata, kb, document_id)

    ids = list(dict.fromkeys(document_ids))
    return dict(zip(ids, await asyncio.gather(*(one(i) for i in ids))))


async def visible_by_source(
    items: List[dict],
    kb,
    reader: KbReader,
    document_id_of: Callable[[dict], Any],
    *,
    withhold_quarantined_source: bool = False,
) -> List[dict]:
    """*items* whose source fact *reader* may read; an unresolvable source drops the item (#16665).

    A summary carries its own quarantine marker (#19163), so only items without one (events) ask the source.
    """
    doc_ids = [str(document_id_of(item) or "") for item in items]
    sources = await _source_map(kb, doc_ids)
    candidates = []
    for item, document_id in zip(items, doc_ids):
        meta = sources[document_id]
        if meta and not (withhold_quarantined_source and is_quarantined({"metadata": meta})):
            candidates.append({"id": item.get("id", ""), "metadata": meta, "item": item})
    kept = await filter_for_user_id(candidates, kb, reader)
    return [c["item"] for c in kept]


async def visible_summaries(summaries: List[dict], kb, reader: KbReader) -> List[dict]:
    """*summaries* whose source fact *reader* may read; the rest, and any with no resolvable source, are dropped."""
    return await visible_by_source(summaries, kb, reader, lambda s: (s.get("metadata") or {}).get("document_id"))


async def visible_events(events: List[dict], kb, reader: KbReader) -> List[dict]:
    """Temporal *events* whose source document *reader* may read (#16665); an event carries no owner of its own."""
    return await visible_by_source(
        events, kb, reader, lambda e: e.get("source_document_id"), withhold_quarantined_source=True
    )


async def document_is_visible(document_id: str, kb, reader: KbReader) -> bool:
    """Whether *reader* may read the source fact of *document_id*."""
    probe = [{"metadata": {"document_id": document_id}}]
    return bool(await visible_summaries(probe, kb, reader))
