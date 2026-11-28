# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The canonical POST /search route filters results by the caller's access (#16665).

Uses the real KnowledgeOwnership.check_access rather than mocking it away, so
this proves the route's own filtering wiring, not just that a mock was called.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.ownership import KnowledgeOwnership
from testkit.read_path_fakes_16665 import RESEARCH, QuarantineGatedKB, quarantined_fact


def _make_kb(legacy_search_result: dict) -> MagicMock:
    kb = MagicMock()
    kb.initialized = True
    kb.ownership_manager = KnowledgeOwnership(redis_client=object())
    kb.get_stats = AsyncMock(return_value={"total_facts": 5})
    kb.search = AsyncMock(return_value=legacy_search_result)
    return kb


def _current_user(user_id: str, role: str = "user") -> dict:
    return {"user_id": user_id, "role": role}


def _make_request() -> MagicMock:
    return MagicMock()


@pytest.mark.asyncio
async def test_search_hides_another_users_private_fact():
    from api.knowledge_search import search
    from api.schemas_knowledge import SearchRequest

    mine = {"id": "f1", "content": "mine", "metadata": {"owner_id": "u1", "visibility": "private"}}
    others_private = {
        "id": "f2",
        "content": "not mine",
        "metadata": {"owner_id": "u99", "visibility": "private"},
    }
    kb = _make_kb({"results": [mine, others_private], "total_results": 2})

    with patch("api.knowledge_search.get_or_create_knowledge_base", new=AsyncMock(return_value=kb)):
        result = await search(SearchRequest(query="test"), _make_request(), current_user=_current_user("u1"))

    ids = {r["id"] for r in result["results"]}
    assert ids == {"f1"}, f"user u1 must not see u99's private fact: {result['results']}"
    assert result["total_results"] == 1


@pytest.mark.asyncio
async def test_search_returns_the_owners_own_private_fact():
    from api.knowledge_search import search
    from api.schemas_knowledge import SearchRequest

    mine = {"id": "f1", "content": "mine", "metadata": {"owner_id": "u1", "visibility": "private"}}
    kb = _make_kb({"results": [mine], "total_results": 1})

    with patch("api.knowledge_search.get_or_create_knowledge_base", new=AsyncMock(return_value=kb)):
        result = await search(SearchRequest(query="test"), _make_request(), current_user=_current_user("u1"))

    assert [r["id"] for r in result["results"]] == ["f1"]
    assert result["total_results"] == 1


@pytest.mark.asyncio
async def test_search_lets_an_admin_read_another_users_private_fact():
    from api.knowledge_search import search
    from api.schemas_knowledge import SearchRequest

    others_private = {
        "id": "f2",
        "content": "not mine",
        "metadata": {"owner_id": "u99", "visibility": "private"},
    }
    kb = _make_kb({"results": [others_private], "total_results": 1})

    with (
        patch("api.knowledge_search.get_or_create_knowledge_base", new=AsyncMock(return_value=kb)),
        patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)),
    ):  # the admin read is audited and committed before it returns (#19860)
        result = await search(
            SearchRequest(query="test"), _make_request(), current_user=_current_user("u1", role="admin")
        )

    assert [r["id"] for r in result["results"]] == ["f2"], "an explicit admin read must see every fact (#16665)"
    assert result["total_results"] == 1


def _quarantine_kb(gated: bool) -> QuarantineGatedKB:
    kb = QuarantineGatedKB(dict_results=True, only_quarantined=True)
    kb.initialized = True
    kb.get_stats = AsyncMock(return_value={"total_facts": 1})
    if not gated:
        kb.search = AsyncMock(return_value={"results": [quarantined_fact()], "total_results": 1})
    return kb


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["user", "admin"])
async def test_search_never_returns_a_research_quarantined_fact(role):
    """AC3 (#16665): the route reads through KB.search, whose gate withholds the quarantined fact (control: ungated)."""
    from api.knowledge_search import search
    from api.schemas_knowledge import SearchRequest

    async def run(kb) -> dict:
        with (
            patch("api.knowledge_search.get_or_create_knowledge_base", new=AsyncMock(return_value=kb)),
            patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)),
        ):
            return await search(SearchRequest(query="test"), _make_request(), current_user=_current_user("u1", role))

    assert RESEARCH in repr(await run(_quarantine_kb(gated=False))), "control: ungated, the fact is returned"
    assert RESEARCH not in repr(await run(_quarantine_kb(gated=True)))


@pytest.mark.asyncio
async def test_search_engine_leg_never_returns_a_research_quarantined_fact():
    """AC3 (#16665): the vector-engine leg bypasses KB.search, so servable_response must withhold the fact itself."""
    from api.knowledge_search import _execute_kb_search

    hit = quarantined_fact()
    engine = MagicMock()
    engine.search = AsyncMock(
        return_value=[MagicMock(text=hit["content"], score=0.9, metadata=hit["metadata"], source="f-q")]
    )
    kb = _quarantine_kb(gated=True)

    with patch("api.knowledge_search.get_vector_search_engine", new=AsyncMock(return_value=engine)):
        results = await _execute_kb_search(kb, "test", 10, "hybrid", "u1", None, [], False)
        with patch("api.knowledge_search.servable_response", new=lambda response, *a, **k: response):
            control = await _execute_kb_search(kb, "test", 10, "hybrid", "u1", None, [], False)

    assert RESEARCH in repr(control), "control: without servable_response the quarantined hit survives the leg"
    assert results == [], "a quarantined fact must not leave the engine leg"
