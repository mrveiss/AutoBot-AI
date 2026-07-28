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
