# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Facts of the multi-source knowledge graph: permission first, then count and page (#20945, #16665).

Moved out of ``knowledge_search_aggregator`` (which must not grow). The listing is scanned in batches up
to ``GRAPH_SCAN_LIMIT``, each batch filtered by what the caller may read, and ``offset``/``max_facts``
page the *visible* set (``get_all_facts`` drops quarantined facts before its offset/limit, #20866, so a short
listing batch is the real end); every page carries a ``cursor`` to the first raw position it did not return.
The reported total is the visible total: it never counts a fact the caller cannot see,
and a short page means the end, not a filtered-out page.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from constants.threshold_constants import CategoryDefaults
from knowledge.graph_bucket_visibility import within_admin_tenant
from knowledge.graph_limits import GRAPH_SCAN_LIMIT, SCAN_BATCH
from knowledge.root_read import AdminReadLedger
from knowledge.search_filters import filter_search_results_by_permission


@dataclass(frozen=True)
class FactsPage:
    """One page of the facts the caller may read; ``total`` is None when the listing could not be read."""

    facts: List[Dict[str, Any]] = field(default_factory=list)
    total: int | None = None
    truncated: bool = False
    cursor: str | None = None  # first raw position not yet returned (``position:skip``); None on the last page
    by_cursor: bool = False  # the page was read from a cursor, so no visible total exists (O(batch) per page)
    failed: bool = False  # the read raised: the listing is unknown, not empty (reported on the section)


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


def _fact_in_tenant(fact: Dict[str, Any], user_org_id: str | None, is_admin: Any, is_superadmin: bool) -> bool:
    """An admin bypass is bound to the caller's tenant; only a superadmin crosses tenants (#20945)."""
    return within_admin_tenant(fact.get("metadata") or {}, bool(is_admin), is_superadmin, user_org_id)


async def _readable_batch(kb: Any, category_filter: str | None, offset: int, size: int, who: tuple) -> tuple:
    """One raw batch of facts: ``(scan advance, more listing remains, readable facts)``."""
    user_id, user_org_id, user_group_ids, is_admin, is_superadmin = who
    if category_filter:
        # get_facts_in_category's facts carry metadata JSON-encoded, unlike kb.search()'s decoded results (#16665)
        result = await kb.get_facts_in_category(
            category_id=category_filter, include_descendants=True, limit=size, offset=offset
        )
        if not result.get("success"):
            raise RuntimeError(f"category {category_filter!r} listing unreadable")  # the route reports an unknown total
        raw = result.get("facts", [])
        facts = [{**fact, "metadata": decode_fact_metadata(fact)} for fact in raw]
        advance, more = size, bool(result.get("has_more"))  # a deleted fact shortens the batch, not the index
    else:
        # #19727: listed, not a search for "*", which the keyword fallback matches nothing for; quarantine stays out
        raw = await kb.get_all_facts(limit=size, offset=offset)
        category_of = lambda fact: (fact.get("metadata") or {}).get("category", CategoryDefaults.GENERAL)  # noqa: E731
        facts = [{**fact, "id": fact.get("fact_id"), "category": category_of(fact)} for fact in raw]
        advance, more = len(raw), len(raw) >= size
    facts = [f for f in facts if _fact_in_tenant(f, user_org_id, is_admin, is_superadmin)]
    readable = await filter_search_results_by_permission(
        facts,
        user_id=user_id,
        user_org_id=user_org_id,
        user_group_ids=user_group_ids,
        ownership_manager=getattr(kb, "ownership_manager", None),
        is_admin=bool(is_admin),  # the ledger records only the returned page, not the whole scan
    )
    return advance, more, readable


async def _more_visible(kb: Any, category_filter: str | None, position: int, who: tuple) -> bool:
    """Whether the caller may read a fact at or after *position*: the probe goes through the same
    permission filter as the page it continues, so it never reports another owner's facts.

    One scan window is probed; a window with nothing readable and a listing that goes on is the scan cap,
    which the page reports as truncated.
    """
    probed = 0
    while probed < GRAPH_SCAN_LIMIT:
        size = min(SCAN_BATCH, GRAPH_SCAN_LIMIT - probed)
        advance, more, readable = await _readable_batch(kb, category_filter, position + probed, size, who)
        if readable:
            return True
        probed += advance
        if not more:
            return False
    return True


def parse_cursor(cursor: str | None) -> tuple:
    """``(raw scan position, readable facts to skip in that batch)`` of a cursor; ValueError when malformed."""
    position, skip = (int(part) for part in (cursor or "0:0").split(":"))
    if position < 0 or skip < 0:
        raise ValueError("cursor out of range")
    return position, skip


def _cursor(position: int, skip: int) -> str:
    return f"{position}:{skip}"


async def _page_from_cursor(kb: Any, category_filter: str | None, max_facts: int, who: tuple, cursor: str) -> FactsPage:
    """The next ``max_facts`` readable facts from *cursor*, scanning at most ``GRAPH_SCAN_LIMIT`` raw records.

    Resumes at the batch the previous page ended in and skips the readable facts it already returned, so no
    readable fact is unreachable however deep the listing is.
    """
    position, skip = parse_cursor(cursor)
    taken: List[Dict[str, Any]] = []
    scanned, next_cursor = 0, None
    while scanned < GRAPH_SCAN_LIMIT and next_cursor is None:
        size = min(SCAN_BATCH, GRAPH_SCAN_LIMIT - scanned)
        advance, more, readable = await _readable_batch(kb, category_filter, position, size, who)
        readable, room = readable[skip:], max_facts - len(taken)
        if len(readable) > room:  # the page ends inside this batch
            taken.extend(readable[:room])
            next_cursor = _cursor(position, skip + room)
            break
        taken.extend(readable)
        position, scanned, skip = position + advance, scanned + advance, 0
        if not more:
            break
        if len(taken) == max_facts or scanned >= GRAPH_SCAN_LIMIT:
            if await _more_visible(kb, category_filter, position, who):
                next_cursor = _cursor(position, 0)
            break
    return FactsPage(taken, None, False, next_cursor, True)


async def visible_facts_page(
    kb: Any,
    category_filter: str | None,
    max_facts: int,
    offset: int,
    user_id: str,
    user_org_id: str | None,
    user_group_ids: List[str],
    is_admin: Any,
    is_superadmin: bool = False,
    cursor: str | None = None,
) -> FactsPage:
    """The page of facts *user_id* may read, with the visible total (#16665: filtered before counted).

    With a *cursor* the scan resumes there instead (``offset`` is ignored for facts; no total is computed).
    Without one, the first ``GRAPH_SCAN_LIMIT`` records are scanned and, when the cap cut the listing short,
    the returned ``cursor`` continues after them.
    """
    who = (user_id, user_org_id, user_group_ids, is_admin, is_superadmin)
    if cursor:
        page = await _page_from_cursor(kb, category_filter, max_facts, who, cursor)
    else:
        page = await _page_from_start(kb, category_filter, max_facts, offset, who)
    if isinstance(is_admin, AdminReadLedger):  # #19860: the admin read is audited for what it returns
        is_admin.record(page.facts)
    return page


def _resume_cursor(windows: List[tuple], end: int, scanned: int, truncated: bool) -> str | None:
    """Where a continuation starts: the first raw position whose readable fact the page did not return.

    *windows* are ``(raw position, readable facts before it, readable facts in it)`` per scanned batch and *end*
    is the visible index the page stopped at, so the cursor lands in the batch holding visible fact *end* with
    the readable facts of that batch the page already returned as the skip. Past the last scanned fact the
    continuation is the scan cap (``truncated``); None only when the listing really ends.
    """
    for position, before, count in windows:
        if before <= end < before + count:
            return _cursor(position, end - before)
    return _cursor(scanned, 0) if truncated else None


async def _page_from_start(kb: Any, category_filter: str | None, max_facts: int, offset: int, who: tuple) -> FactsPage:
    visible: List[Dict[str, Any]] = []
    windows: List[tuple] = []
    scanned, truncated = 0, False
    while scanned < GRAPH_SCAN_LIMIT:
        size = min(SCAN_BATCH, GRAPH_SCAN_LIMIT - scanned)
        advance, more, readable = await _readable_batch(kb, category_filter, scanned, size, who)
        windows.append((scanned, len(visible), len(readable)))
        scanned += advance
        visible.extend(readable)
        if not more:
            break
        if scanned >= GRAPH_SCAN_LIMIT:
            truncated = await _more_visible(kb, category_filter, scanned, who)
    end = offset + max_facts
    return FactsPage(visible[offset:end], len(visible), truncated, _resume_cursor(windows, end, scanned, truncated))
