# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the relation-graph/citation expansion fix at api/knowledge_search_aggregator.py (#16708).

``RelationsMixin.get_fact_relations()`` has always returned a flat
``"relations"`` list, each item carrying its own ``"direction"``/``"to"``/
``"from"``/``"type"`` -- never top-level ``"outgoing"``/``"incoming"`` keys,
and never ``"target_id"``/``"source_id"``/``"relation_type"``/``"strength"``
per item. Every fixture below is shaped exactly like the real return value
(see ``knowledge/relations.py::RelationsMixin.get_fact_relations``), not a
loosely-typed mock, so a regression back to the old wrong-key reads fails
these tests instead of silently passing the way an auto-vivifying Mock would.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from api.knowledge_search_aggregator import (
    _expand_fact_relations,
    _get_fact_relations_for_graph,
    _process_relations_for_citations,
)

_USER_ID = "u1"


def _real_relations_result(fact_id: str) -> dict:
    """A `get_fact_relations(direction="both", include_fact_details=True)` result, real shape."""
    return {
        "success": True,
        "fact_id": fact_id,
        "relations": [
            {
                "from": fact_id,
                "to": "fact-target",
                "type": "supports",
                "direction": "outgoing",
                "metadata": {},
                "target_fact": {"id": "fact-target", "content": "target content"},
            },
            {
                "from": "fact-source",
                "to": fact_id,
                "type": "contradicts",
                "direction": "incoming",
                "source_fact": {"id": "fact-source", "content": "source content"},
            },
        ],
    }


@pytest.mark.asyncio
async def test_expand_fact_relations_processes_both_directions():
    """#16708: both the outgoing and the incoming relation must surface, not just neither."""
    mock_kb = AsyncMock()
    mock_kb.get_fact_relations.return_value = _real_relations_result("fact-1")
    related_ids: set = set()
    results: list = []

    with patch(
        "api.knowledge_search_aggregator.filter_search_results_by_permission",
        AsyncMock(side_effect=lambda results, **_kw: results),
    ):
        await _expand_fact_relations(mock_kb, "fact-1", related_ids, results, _USER_ID, None, [], False)

    assert related_ids == {"fact-target", "fact-source"}
    assert {r["id"] for r in results} == {"fact-target", "fact-source"}
    assert {r["relation_type"] for r in results} == {"supports", "contradicts"}


@pytest.mark.asyncio
async def test_expand_fact_relations_keeps_multiple_outgoing_relations():
    """The old `target_id`-less dedup key always resolved to None, so a second
    outgoing relation collided with the first and was dropped. Two distinct
    targets must both survive."""
    mock_kb = AsyncMock()
    mock_kb.get_fact_relations.return_value = {
        "success": True,
        "fact_id": "fact-1",
        "relations": [
            {
                "from": "fact-1",
                "to": "fact-a",
                "type": "supports",
                "direction": "outgoing",
                "target_fact": {"id": "fact-a", "content": "a"},
            },
            {
                "from": "fact-1",
                "to": "fact-b",
                "type": "supports",
                "direction": "outgoing",
                "target_fact": {"id": "fact-b", "content": "b"},
            },
        ],
    }
    related_ids: set = set()
    results: list = []

    with patch(
        "api.knowledge_search_aggregator.filter_search_results_by_permission",
        AsyncMock(side_effect=lambda results, **_kw: results),
    ):
        await _expand_fact_relations(mock_kb, "fact-1", related_ids, results, _USER_ID, None, [], False)

    assert related_ids == {"fact-a", "fact-b"}
    assert len(results) == 2


@pytest.mark.asyncio
async def test_process_relations_for_citations_builds_related_information_section():
    mock_kb = AsyncMock()
    mock_kb.get_fact_relations.return_value = {
        "success": True,
        "fact_id": "fact-1",
        "relations": [
            {
                "from": "fact-1",
                "to": "fact-target",
                "type": "supports",
                "direction": "outgoing",
                "target_fact": {"id": "fact-target", "content": "target content"},
            }
        ],
    }
    context_parts: list = []
    citations = [{"id": "fact-1"}]

    with patch(
        "api.knowledge_search_aggregator.filter_search_results_by_permission",
        AsyncMock(side_effect=lambda results, **_kw: results),
    ):
        total_length = await _process_relations_for_citations(
            mock_kb, citations, 10_000, context_parts, 0, _USER_ID, None, [], False
        )

    text = "".join(context_parts)
    assert "## Related Information" in text
    assert "[supports]" in text
    assert "target content" in text
    assert total_length > 0


@pytest.mark.asyncio
async def test_process_relations_for_citations_skips_when_no_outgoing_relations():
    mock_kb = AsyncMock()
    mock_kb.get_fact_relations.return_value = {"success": True, "fact_id": "fact-1", "relations": []}
    context_parts: list = []

    total_length = await _process_relations_for_citations(
        mock_kb, [{"id": "fact-1"}], 10_000, context_parts, 0, _USER_ID, None, [], False
    )

    assert context_parts == []
    assert total_length == 0


@pytest.mark.asyncio
async def test_get_fact_relations_for_graph_returns_edges():
    """The target ("fact-target") must also be in fact_ids for the edge to
    qualify, and both fact_ids get queried -- so "fact-target" needs its own
    (empty) relations response, distinct from "fact-1"'s."""
    mock_kb = AsyncMock()
    empty = {"success": True, "fact_id": "fact-target", "relations": []}
    mock_kb.get_fact_relations.side_effect = lambda fact_id, **_kw: (
        _real_relations_result("fact-1") if fact_id == "fact-1" else empty
    )

    edges = await _get_fact_relations_for_graph(mock_kb, ["fact-1", "fact-target"])

    assert edges == [{"from": "fact-1", "to": "fact-target", "type": "supports", "strength": 0.8}]
