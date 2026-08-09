# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Name resolution prefers an exact match over a relevance hit (#13761).

``get_entity(entity_name=X)`` ran ``search_entities(query=X, limit=1)`` and
returned the top hit unconditionally, so a name that does not exist still
resolved — to whatever ranked first. Behind ``/graph-rag/path``, the
``memory.path`` MCP tool and the Connection Path tab, that means a typo returns
a real, correct path to the wrong entity.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from autobot_memory_graph.entities import EntityOperationsMixin

_INCIDENT_7 = {"id": "id-7", "name": "Incident 7", "type": "incident"}
_INCIDENT_71 = {"id": "id-71", "name": "Incident 71", "type": "incident"}


def _graph(*search_results):
    """An EntityOperationsMixin whose only live dependency is search_entities.

    Relevance order is the argument order, so a test states "Incident 71 ranks
    first" simply by listing it first — which is the situation being guarded.
    """
    graph = EntityOperationsMixin()
    graph.ensure_initialized = lambda: None
    graph.search_entities = AsyncMock(return_value=list(search_results))
    graph.search_cache = SimpleNamespace(clear=lambda: None)
    graph.embedding_cache = {}
    graph.redis_client = AsyncMock()
    graph.redis_client.delete = AsyncMock(return_value=1)
    return graph


# --------------------------------------------------------------- resolution


@pytest.mark.asyncio
async def test_a_name_that_does_not_exist_is_not_reported_as_an_exact_hit():
    """ "Incident 7" is a typo; only "Incident 71" exists."""
    graph = _graph(_INCIDENT_71)

    entity = await graph.get_entity(entity_name="Incident 7")

    assert entity["id"] == "id-71"
    assert entity["_resolution"] == "fuzzy", "a near-miss must be marked, not passed off as the entity"


@pytest.mark.asyncio
async def test_the_exact_name_wins_over_a_higher_ranked_near_miss():
    """Both exist and the near-miss ranks first — the exact name must still win."""
    graph = _graph(_INCIDENT_71, _INCIDENT_7)

    entity = await graph.get_entity(entity_name="Incident 7")

    assert entity["id"] == "id-7"
    assert entity["_resolution"] == "exact"


@pytest.mark.asyncio
async def test_case_differences_are_still_the_same_entity():
    """Entity names are display strings; case is not identity."""
    graph = _graph(_INCIDENT_71, _INCIDENT_7)

    entity = await graph.get_entity(entity_name="incident 7")

    assert entity["id"] == "id-7"
    assert entity["_resolution"] == "exact"


@pytest.mark.asyncio
async def test_an_exact_match_below_the_first_page_is_still_found():
    """Resolution scans candidates, not just the top hit."""
    crowd = [{"id": f"id-{i}", "name": f"Incident 7{i}", "type": "incident"} for i in range(1, 20)]
    graph = _graph(*crowd, _INCIDENT_7)

    entity = await graph.get_entity(entity_name="Incident 7")

    assert entity["id"] == "id-7"
    assert entity["_resolution"] == "exact"
    assert graph.search_entities.await_args.kwargs["limit"] > 1


@pytest.mark.asyncio
async def test_no_results_is_still_none():
    graph = _graph()

    assert await graph.get_entity(entity_name="Nothing At All") is None


# ------------------------------------------------- writes refuse a near-miss


@pytest.mark.asyncio
async def test_delete_by_name_refuses_a_near_miss():
    """ "delete Incident 7" must never delete "Incident 71"."""
    graph = _graph(_INCIDENT_71)

    deleted = await graph.delete_entity(entity_name="Incident 7")

    assert deleted is False
    graph.redis_client.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_by_name_still_works_for_a_real_name():
    graph = _graph(_INCIDENT_71, _INCIDENT_7)

    assert await graph.delete_entity(entity_name="Incident 7") is True


@pytest.mark.asyncio
async def test_add_observations_refuses_a_near_miss():
    """Writing observations into a near-miss puts one entity's facts on another."""
    graph = _graph(_INCIDENT_71)

    with pytest.raises(RuntimeError):
        await graph.add_observations(entity_name="Incident 7", observations=["something true about 7"])

    graph.redis_client.json.assert_not_called()
