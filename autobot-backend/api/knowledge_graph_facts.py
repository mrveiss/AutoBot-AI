# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Facts of the multi-source knowledge graph: permission first, then count and page (#20945, #16665).

Moved out of ``knowledge_search_aggregator`` (which must not grow). The listing is scanned in batches up
to ``GRAPH_SCAN_LIMIT``, each batch filtered by what the caller may read, and ``offset``/``max_facts``
page the *visible* set. The reported total is the visible total: it never counts a fact the caller
cannot see, and a short page means the end, not a filtered-out page.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from constants.threshold_constants import CategoryDefaults
from knowledge.graph_limits import GRAPH_SCAN_LIMIT, SCAN_BATCH
from knowledge.root_read import AdminReadLedger
from knowledge.search_filters import filter_search_results_by_permission


@dataclass(frozen=True)
class FactsPage:
    """One page of the facts the caller may read; ``total`` is None when the listing could not be read."""

    facts: List[Dict[str, Any]] = field(default_factory=list)
    total: int | None = None
    truncated: bool = False


def decode_fact_metadata(raw_fact: Dict[str, Any]) -> Dict[str, Any]:
    """knowledge/facts.py hset()s "metadata" as a JSON *string* (#16665 review:
    wrapping it un-decoded read every fact as owner_id=None, denying everyone
    including the owner)."""
    raw = raw_fact.get("metadata")
    if not isinstance(raw, str):
        return raw if isinstance(raw, dict) else {}
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


async def _readable_batch(kb: Any, category_filter: str | None, offset: int, size: int, who: tuple) -> tuple:
    """One raw batch of facts and the part of it the caller may read: ``(raw count, readable facts)``."""
    if category_filter:
        # get_facts_in_category's facts carry metadata JSON-encoded, unlike kb.search()'s decoded results (#16665)
        result = await kb.get_facts_in_category(
            category_id=category_filter, include_descendants=True, limit=size, offset=offset
        )
        raw = result.get("facts", []) if result.get("success") else []
        facts = [{**fact, "metadata": decode_fact_metadata(fact)} for fact in raw]
    else:
        # #19727: listed, not a search for "*", which the keyword fallback matches nothing for; quarantine stays out
        raw = await kb.get_all_facts(limit=size, offset=offset)
        category_of = lambda fact: (fact.get("metadata") or {}).get("category", CategoryDefaults.GENERAL)  # noqa: E731
        facts = [{**fact, "id": fact.get("fact_id"), "category": category_of(fact)} for fact in raw]
    user_id, user_org_id, user_group_ids, is_admin = who
    readable = await filter_search_results_by_permission(
        facts,
        user_id=user_id,
        user_org_id=user_org_id,
        user_group_ids=user_group_ids,
        ownership_manager=getattr(kb, "ownership_manager", None),
        is_admin=bool(is_admin),  # the ledger records only the returned page, not the whole scan
    )
    return len(raw), readable


async def visible_facts_page(
    kb: Any,
    category_filter: str | None,
    max_facts: int,
    offset: int,
    user_id: str,
    user_org_id: str | None,
    user_group_ids: List[str],
    is_admin: Any,
) -> FactsPage:
    """The page of facts *user_id* may read, with the visible total (#16665: filtered before counted)."""
    visible: List[Dict[str, Any]] = []
    scanned, truncated = 0, False
    who = (user_id, user_org_id, user_group_ids, is_admin)
    while True:
        if scanned >= GRAPH_SCAN_LIMIT:
            truncated = True
            break
        size = min(SCAN_BATCH, GRAPH_SCAN_LIMIT - scanned)
        raw_count, readable = await _readable_batch(kb, category_filter, scanned, size, who)
        scanned += raw_count
        visible.extend(readable)
        if raw_count < size:
            break
    page = visible[offset : offset + max_facts]
    if isinstance(is_admin, AdminReadLedger):  # #19860: the admin read is audited for what it returns
        is_admin.record(page)
    return FactsPage(page, len(visible), truncated)
