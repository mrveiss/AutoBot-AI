#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the KB-explorer collection graph endpoint — Issue #9018 Phase 2.

Covers:
- _serialize_graph_nodes maps entities → explorer node dicts (drops id-less).
- _collect_collection_edges gathers + dedupes outgoing relations.
- collection_graph returns entities + relations JSON (read-only).

Calls the endpoint function directly with a mocked GraphRAGService to avoid
spinning up the full FastAPI app (and its Redis dependency at import time).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")

from api.graph_rag import (  # noqa: E402
    _check_component_health,
    _collect_collection_edges,
    _determine_overall_status,
    _probe_component,
    _serialize_graph_nodes,
    collection_graph,
    graph_rag_health,
)


def test_serialize_graph_nodes_maps_fields():
    entities = [
        {"id": "e1", "name": "Service X", "type": "service", "observations": ["runs config Y"]},
        {"id": "e2", "name": "Incident 7", "type": "incident", "observations": []},
    ]
    nodes = _serialize_graph_nodes(entities)
    assert len(nodes) == 2
    assert nodes[0] == {
        "id": "e1",
        "name": "Service X",
        "type": "service",
        "observations": ["runs config Y"],
    }


def test_serialize_graph_nodes_drops_idless():
    entities = [{"name": "no id"}, {"id": "e1", "name": "ok"}]
    nodes = _serialize_graph_nodes(entities)
    assert [n["id"] for n in nodes] == ["e1"]


async def test_collect_collection_edges_dedupes():
    service = MagicMock()
    rel = {"from": "e1", "to": "e2", "type": "OWNS", "direction": "outgoing", "metadata": {}}
    # Same edge returned twice (e1 then duplicate path) must dedupe to one.
    service.graph = MagicMock()
    service.graph.get_relations = AsyncMock(return_value={"relations": [rel]})
    edges = await _collect_collection_edges(service, ["e1", "e1"])
    assert len(edges) == 1
    assert edges[0]["type"] == "OWNS"


async def test_collection_graph_returns_nodes_and_edges():
    entities = [
        {"id": "e1", "name": "Service X", "type": "service", "observations": ["o"]},
        {"id": "e2", "name": "Incident 7", "type": "incident", "observations": []},
    ]
    rel = {"from": "e1", "to": "e2", "type": "OWNS", "direction": "outgoing", "metadata": {}}

    service = MagicMock()
    service.graph = MagicMock()
    service.graph.search_entities = AsyncMock(return_value=entities)

    async def _rels(entity_id, direction="both"):
        return {"relations": [rel]} if entity_id == "e1" else {"relations": []}

    service.graph.get_relations = AsyncMock(side_effect=_rels)

    response = await collection_graph(
        collection_id="col-123",
        service=service,
        current_user={"id": "u1"},
    )

    body = json.loads(bytes(response.body).decode("utf-8"))
    assert body["collection_id"] == "col-123"
    assert body["node_count"] == 2
    assert body["edge_count"] == 1
    assert {n["name"] for n in body["nodes"]} == {"Service X", "Incident 7"}
    assert body["edges"][0]["type"] == "OWNS"
    # Collection-scoped query: tag filter applied.
    service.graph.search_entities.assert_awaited_once()
    _, kwargs = service.graph.search_entities.await_args
    assert kwargs.get("tags") == ["col-123"]


# ---------------------------------------------------------------------------
# Graph-RAG /health endpoint — #12316
#
# Regression: graph_rag_health 500'd with
#   AttributeError: 'AutoBotMemoryGraph' object has no attribute 'initialized'
# A health probe must degrade gracefully — always return a status, never 500.
# ---------------------------------------------------------------------------


class _GraphMissingInitialized:
    """Stand-in for the pre-fix AutoBotMemoryGraph: truthy but no ``initialized``.

    Accessing ``.initialized`` raises AttributeError — exactly the #12316 crash.
    """


def _health_body(response):
    return json.loads(bytes(response.body).decode("utf-8"))


def test_probe_component_reports_unavailable_on_exception():
    def _boom() -> bool:
        raise AttributeError("no attribute 'initialized'")

    assert _probe_component("memory_graph", _boom) == "unavailable"


def test_probe_component_healthy_and_unavailable():
    assert _probe_component("x", lambda: True) == "healthy"
    assert _probe_component("x", lambda: False) == "unavailable"


def test_check_component_health_all_healthy():
    service = MagicMock()
    service.rag = MagicMock()
    service.graph = MagicMock()
    service.graph.initialized = True
    components = _check_component_health(service)
    assert components == {
        "graph_rag_service": "healthy",
        "rag_service": "healthy",
        "memory_graph": "healthy",
    }


def test_check_component_health_degraded_when_graph_uninitialized():
    service = MagicMock()
    service.rag = MagicMock()
    service.graph = MagicMock()
    service.graph.initialized = False
    components = _check_component_health(service)
    assert components["memory_graph"] == "unavailable"
    assert _determine_overall_status(components) == "degraded"


def test_check_component_health_survives_missing_initialized_attr():
    # The exact #12316 crash: graph object lacks ``initialized``.
    service = MagicMock()
    service.rag = MagicMock()
    service.graph = _GraphMissingInitialized()
    components = _check_component_health(service)  # must not raise
    assert components["memory_graph"] == "unavailable"


async def test_graph_rag_health_returns_200_when_healthy():
    service = MagicMock()
    service.rag = MagicMock()
    service.graph = MagicMock()
    service.graph.initialized = True

    response = await graph_rag_health(service=service, current_user={"id": "u1"})
    assert response.status_code == 200
    body = _health_body(response)
    assert body["status"] == "healthy"
    assert body["components"]["memory_graph"] == "healthy"


async def test_graph_rag_health_returns_degraded_not_500_when_subsystem_down():
    # Subsystem unavailable (graph missing ``initialized``) must yield a usable
    # status (503 degraded), never the GRAPH_RAG_0310 500 from #12316.
    service = MagicMock()
    service.rag = MagicMock()
    service.graph = _GraphMissingInitialized()

    response = await graph_rag_health(service=service, current_user={"id": "u1"})
    assert response.status_code == 503
    body = _health_body(response)
    assert body["status"] == "degraded"
    assert "status" in body  # monitoring always gets a status field
    assert body["components"]["memory_graph"] == "unavailable"


# ---------------------------------------------------------------------------
# Graph-RAG /path endpoint — #13474
#
# Gives PropertyGraph.shortest_path a production caller. /search expands a
# neighbourhood ("what relates to X"); /path answers "how does X reach Y".
# ---------------------------------------------------------------------------

from fastapi import HTTPException  # noqa: E402

from api.graph_rag import graph_rag_path  # noqa: E402
from api.schemas_knowledge import GraphRAGPathRequest  # noqa: E402


def _path_service(result: dict) -> MagicMock:
    service = MagicMock()
    service.find_connection_path = AsyncMock(return_value=result)
    return service


async def test_path_endpoint_returns_the_traversal():
    service = _path_service(
        {
            "found": True,
            "reason": None,
            "missing_entities": [],
            "from_entity": {"id": "e1", "name": "Redis Config", "type": "decision"},
            "to_entity": {"id": "e2", "name": "Incident 7", "type": "incident"},
            "hops": 1,
            "path": [{"relation": "CAUSED", "direction": "outgoing", "node": {"id": "e2"}}],
            "query": {"direction": "both"},
            "traversal_time": 0.004,
        }
    )

    response = await graph_rag_path(
        path_request=GraphRAGPathRequest(from_entity="Redis Config", to_entity="Incident 7"),
        service=service,
        current_user={"id": "u1"},
    )

    body = json.loads(bytes(response.body).decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["found"] is True
    assert body["hops"] == 1
    assert body["path"][0]["relation"] == "CAUSED"
    assert body["request_id"]


async def test_path_endpoint_forwards_every_query_parameter():
    """A parameter the router drops is a parameter the caller cannot use."""
    service = _path_service({"found": False, "reason": "no_path", "hops": 0, "path": []})

    await graph_rag_path(
        path_request=GraphRAGPathRequest(
            from_entity="A",
            to_entity="B",
            relation="CAUSED",
            max_depth=3,
            direction="incoming",
            timeout=5.0,
        ),
        service=service,
        current_user={"id": "u1"},
    )

    service.find_connection_path.assert_awaited_once_with(
        from_entity="A",
        to_entity="B",
        relation="CAUSED",
        max_depth=3,
        direction="incoming",
        timeout=5.0,
    )


async def test_path_endpoint_always_carries_a_deadline_by_default():
    """#13474 review: a 'both'-direction walk branches twice per node and issues
    a Redis round-trip per edge, so an unbounded traversal is a denial-of-service
    vector on an authenticated endpoint. The request model supplies a default."""
    service = _path_service({"found": False, "reason": "no_path", "hops": 0, "path": []})

    await graph_rag_path(
        path_request=GraphRAGPathRequest(from_entity="A", to_entity="B"),
        service=service,
        current_user={"id": "u1"},
    )

    assert service.find_connection_path.await_args.kwargs["timeout"] is not None


async def test_path_endpoint_reports_a_timeout_as_504_not_as_no_path():
    """An abandoned walk is not evidence that two entities are unconnected."""
    import asyncio

    service = MagicMock()
    service.find_connection_path = AsyncMock(side_effect=asyncio.TimeoutError())

    with pytest.raises(HTTPException) as exc_info:
        await graph_rag_path(
            path_request=GraphRAGPathRequest(from_entity="A", to_entity="B"),
            service=service,
            current_user={"id": "u1"},
        )

    assert exc_info.value.status_code == 504


async def test_path_endpoint_does_not_leak_the_exception_message():
    """with_error_handling would otherwise return the raw exception type and
    message to the client (#13740) — for a Redis failure, an internal host and
    port. /search guards the same way."""
    service = MagicMock()
    service.find_connection_path = AsyncMock(
        side_effect=ConnectionError("Error 111 connecting to internal-host:6379")
    )

    with pytest.raises(HTTPException) as exc_info:
        await graph_rag_path(
            path_request=GraphRAGPathRequest(from_entity="A", to_entity="B"),
            service=service,
            current_user={"id": "u1"},
        )

    assert exc_info.value.status_code == 500
    assert "internal-host" not in str(exc_info.value.detail)
    assert "6379" not in str(exc_info.value.detail)


async def test_path_endpoint_returns_200_when_unconnected():
    """ "They exist but are not connected" is a valid answer, not an error."""
    service = _path_service(
        {
            "found": False,
            "reason": "no_path",
            "missing_entities": [],
            "from_entity": {"id": "e1"},
            "to_entity": {"id": "e3"},
            "hops": 0,
            "path": [],
            "query": {},
            "traversal_time": 0.001,
        }
    )

    response = await graph_rag_path(
        path_request=GraphRAGPathRequest(from_entity="A", to_entity="B"),
        service=service,
        current_user={"id": "u1"},
    )

    body = json.loads(bytes(response.body).decode("utf-8"))
    assert response.status_code == 200
    assert body["found"] is False
    assert body["reason"] == "no_path"


async def test_path_endpoint_404s_on_unresolvable_entity():
    """A name that does not exist is a bad reference, distinct from "no path"."""
    service = _path_service(
        {
            "found": False,
            "reason": "entity_not_found",
            "missing_entities": ["Does Not Exist"],
            "from_entity": {"id": "e1"},
            "to_entity": None,
            "hops": 0,
            "path": [],
            "query": {},
            "traversal_time": 0.001,
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await graph_rag_path(
            path_request=GraphRAGPathRequest(from_entity="A", to_entity="Does Not Exist"),
            service=service,
            current_user={"id": "u1"},
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["missing_entities"] == ["Does Not Exist"]


def test_path_request_rejects_whitespace_entity_names():
    with pytest.raises(ValueError):
        GraphRAGPathRequest(from_entity="   ", to_entity="B")


def test_path_request_rejects_out_of_range_depth_and_direction():
    with pytest.raises(ValueError):
        GraphRAGPathRequest(from_entity="A", to_entity="B", max_depth=99)
    with pytest.raises(ValueError):
        GraphRAGPathRequest(from_entity="A", to_entity="B", direction="sideways")


def test_path_request_trims_entity_names():
    req = GraphRAGPathRequest(from_entity="  Redis Config  ", to_entity=" Incident 7 ")
    assert req.from_entity == "Redis Config"
    assert req.to_entity == "Incident 7"
