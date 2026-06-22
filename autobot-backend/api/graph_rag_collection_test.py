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
    _collect_collection_edges,
    _serialize_graph_nodes,
    collection_graph,
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
