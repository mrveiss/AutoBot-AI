# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
End-to-end wiring proof for PropertyGraph.shortest_path — Issue #13474.

#8198 implemented the traversal and closed on the implementation, not the
wiring: six unit tests exercised it and no production code path reached it.
This module asserts the call chain itself, with nothing stubbed between the
layers — only Redis and the entity store are faked:

    POST /graph-rag/path        api.graph_rag.graph_rag_path
      -> GraphRAGService.find_connection_path
        -> AutoBotMemoryGraph.find_path        (name -> entity id resolution)
          -> PropertyGraph.shortest_path       (the traversal under wiring)
            -> FakeRedis

A unit test on any single layer cannot catch a break in this chain — a renamed
kwarg, a swallowed exception, or a service that quietly stopped delegating all
pass their own tests while the feature is unreachable again.
"""

import json

import pytest

pytest.importorskip("fastapi")

from api.graph_rag import graph_rag_path  # noqa: E402
from api.schemas_knowledge import GraphRAGPathRequest  # noqa: E402
from services.graph_rag_service import GraphRAGService  # noqa: E402
from tests.memory_graph.graph_test_doubles import make_harness  # noqa: E402


async def _real_chain() -> GraphRAGService:
    """A real GraphRAGService over a real mixin + real PropertyGraph.

    ``rag_service`` is unused by the path traversal, so it is left as None: the
    point is that no test double sits between the service and the graph.
    """
    harness = await make_harness()
    return GraphRAGService(rag_service=None, memory_graph=harness)


def _body(response) -> dict:
    return json.loads(bytes(response.body).decode("utf-8"))


async def _call_endpoint(service: GraphRAGService, **kwargs) -> dict:
    response = await graph_rag_path(
        path_request=GraphRAGPathRequest(**kwargs),
        service=service,
        current_user={"id": "u1"},
    )
    return _body(response)


@pytest.mark.asyncio
async def test_endpoint_reaches_the_traversal_and_returns_a_real_path():
    """The full chain resolves names, traverses, and reports the edge crossed."""
    service = await _real_chain()

    body = await _call_endpoint(service, from_entity="Redis Config", to_entity="Incident 7")

    assert body["success"] is True
    assert body["found"] is True
    assert body["hops"] == 1
    assert body["from_entity"] == {"id": "e1", "name": "Redis Config", "type": "decision"}
    assert body["to_entity"] == {"id": "e2", "name": "Incident 7", "type": "incident"}
    step = body["path"][0]
    assert step["relation"] == "CAUSED"
    assert step["direction"] == "outgoing"
    assert step["node"]["name"] == "Incident 7"
    assert body["traversal_time"] >= 0.0


@pytest.mark.asyncio
async def test_endpoint_answers_the_reverse_question_by_default():
    """Only e1 -> e2 is stored; "how is the incident connected to the config"
    must still be answerable, or the endpoint is half-useful on a graph whose
    relations are mostly one-directional."""
    service = await _real_chain()

    body = await _call_endpoint(service, from_entity="Incident 7", to_entity="Redis Config")

    assert body["found"] is True
    assert body["hops"] == 1
    assert body["path"][0]["direction"] == "incoming"


@pytest.mark.asyncio
async def test_endpoint_reports_unconnected_entities_as_a_found_false_answer():
    service = await _real_chain()

    body = await _call_endpoint(service, from_entity="Redis Config", to_entity="Orphan")

    assert body["found"] is False
    assert body["reason"] == "no_path"
    assert body["path"] == []


@pytest.mark.asyncio
async def test_endpoint_404s_through_the_whole_chain_on_a_bad_name():
    from fastapi import HTTPException

    service = await _real_chain()

    with pytest.raises(HTTPException) as exc_info:
        await _call_endpoint(service, from_entity="Redis Config", to_entity="Nope")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["missing_entities"] == ["Nope"]


@pytest.mark.asyncio
async def test_relation_filter_survives_every_layer():
    """A filter dropped anywhere in the chain silently widens the traversal."""
    service = await _real_chain()

    matched = await _call_endpoint(service, from_entity="Redis Config", to_entity="Incident 7", relation="CAUSED")
    assert matched["found"] is True

    unmatched = await _call_endpoint(service, from_entity="Redis Config", to_entity="Incident 7", relation="BLOCKS")
    assert unmatched["found"] is False
    assert unmatched["reason"] == "no_path"


@pytest.mark.asyncio
async def test_direction_and_max_depth_survive_every_layer():
    service = await _real_chain()

    body = await _call_endpoint(
        service,
        from_entity="Incident 7",
        to_entity="Redis Config",
        direction="outgoing",
        max_depth=2,
    )

    assert body["found"] is False, "direction=outgoing must not find the reverse edge"
    assert body["query"] == {
        "from_entity": "Incident 7",
        "to_entity": "Redis Config",
        "relation": None,
        "max_depth": 2,
        "direction": "outgoing",
    }


@pytest.mark.asyncio
async def test_traversal_failure_is_not_reported_as_no_path():
    """A broken traversal must surface as an error, not as ``found: false``.

    Reporting a Redis outage as "these two are not connected" would make an
    outage indistinguishable from an answer — the caller has no way to tell that
    the question went unanswered. No layer in the chain may catch this.
    """
    from fastapi import HTTPException

    service = await _real_chain()

    async def _boom(*args, **kwargs):
        raise ConnectionError("redis down")

    service.graph.graph.shortest_path = _boom

    with pytest.raises(HTTPException) as exc_info:
        await _call_endpoint(service, from_entity="Redis Config", to_entity="Incident 7")

    # with_error_handling maps the propagated failure to a 5xx; what matters is
    # that it is an error at all rather than a 200 with found=False.
    assert exc_info.value.status_code >= 500
