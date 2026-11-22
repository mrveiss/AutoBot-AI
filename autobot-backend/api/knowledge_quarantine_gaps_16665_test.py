# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The research quarantine holds on /multi-source relations and the category graph path (#16665 AC3).

Both read facts straight from Redis hashes (``metadata`` is a JSON string), not through ``KB.search``,
so neither passes the search gate: each applies the canonical quarantine predicate itself.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.knowledge_graph_facts import visible_facts_page
from api.schemas_knowledge import SearchRequest
from autobot_shared.ssot_config import config
from knowledge.ownership import KnowledgeOwnership
from testkit.read_path_fakes_16665 import OPEN_META, CategoryKB

QUARANTINE = config.research_quarantine_collection


def _hash(fact_id: str, **meta) -> dict:
    """A fact as ``hgetall`` returns it: bytes keys and values, metadata a JSON string."""
    row = {"content": f"fact {fact_id}", "metadata": json.dumps({**OPEN_META, **meta})}
    return {k.encode(): v.encode() for k, v in row.items()}


async def _category_kb(quarantined: bool = True) -> CategoryKB:
    kb = CategoryKB()
    await kb.add_fact("f-open")
    await kb.add_fact("f-research", **({"collection": QUARANTINE} if quarantined else {}))
    return kb


@pytest.mark.asyncio
async def test_a_category_listing_never_returns_a_quarantined_fact():
    result = await (await _category_kb()).get_facts_in_category("cat1")

    assert [f["id"] for f in result["facts"]] == ["f-open"]


@pytest.mark.asyncio
async def test_the_graph_category_path_never_returns_a_quarantined_fact():
    page = await visible_facts_page(await _category_kb(), "cat1", 10, 0, "u1", None, [], False)

    assert [f["id"] for f in page.facts] == ["f-open"]


@pytest.mark.asyncio
async def test_the_category_quarantine_test_is_sensitive_to_a_leak():
    """With no quarantined marker the fact is listed, so the absence above is the filter's doing."""
    result = await (await _category_kb(quarantined=False)).get_facts_in_category("cat1")

    assert sorted(f["id"] for f in result["facts"]) == ["f-open", "f-research"]


def _related(fact_id: str, **meta) -> dict:
    fact = {k.decode(): v.decode() for k, v in _hash(fact_id, **meta).items()}
    return {**fact, "id": fact_id}


def _relation_kb(target: dict, source: dict) -> MagicMock:
    kb = MagicMock()
    kb.ownership_manager = KnowledgeOwnership(redis_client=object())
    kb.search = AsyncMock(return_value={"results": [{"id": "f1", "content": "hit", "metadata": OPEN_META}]})
    relations = [
        {"direction": "outgoing", "type": "related_to", "to": target["id"], "target_fact": target},
        {"direction": "incoming", "type": "related_to", "from": source["id"], "source_fact": source},
    ]
    kb.get_fact_relations = AsyncMock(return_value={"success": True, "relations": relations})
    return kb


async def _related_ids(kb: MagicMock) -> set:
    from api.knowledge_search_aggregator import search

    body = SearchRequest(query="test", include_sources=["facts", "relations"], expand_relations=True)
    with patch("api.knowledge_search_aggregator.get_or_create_knowledge_base", new=AsyncMock(return_value=kb)):
        result = await search(MagicMock(), body, current_user={"user_id": "u1", "role": "user"})
    return {f["id"] for f in result["related_facts"]}


@pytest.mark.asyncio
async def test_multi_source_search_withholds_a_quarantined_related_fact():
    kb = _relation_kb(_related("t-research", collection=QUARANTINE), _related("s-research", collection=QUARANTINE))

    assert await _related_ids(kb) == set()


@pytest.mark.asyncio
async def test_multi_source_search_still_returns_an_unquarantined_related_fact():
    kb = _relation_kb(_related("t-open"), _related("s-research", collection=QUARANTINE))

    assert await _related_ids(kb) == {"t-open"}
