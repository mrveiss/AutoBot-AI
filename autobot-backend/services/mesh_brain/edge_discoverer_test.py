# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for EdgeDiscoverer — LLM-based relationship naming (#2117)."""

from unittest.mock import AsyncMock

import pytest

from services.mesh_brain.edge_discoverer import DiscoveryReport, EdgeDiscoverer

# =============================================================================
# Helpers
# =============================================================================

_EDGE_A = "aaaaaaaa-0000-0000-0000-000000000001"
_EDGE_B = "bbbbbbbb-0000-0000-0000-000000000002"
_NODE_X = "xxxxxxxx-0000-0000-0000-000000000010"
_NODE_Y = "yyyyyyyy-0000-0000-0000-000000000011"
_NODE_Z = "zzzzzzzz-0000-0000-0000-000000000012"


def _make_db_mock() -> AsyncMock:
    """Return a DiscovererDB mock with empty defaults."""
    db = AsyncMock()
    db.fetch_candidate_edges = AsyncMock(return_value=[])
    db.update_edge = AsyncMock()
    db.log_evolution = AsyncMock()
    return db


async def _llm_returning(label: str):
    """Return a coroutine factory whose calls always resolve to label."""

    async def _llm(prompt: str) -> str:
        return label

    return _llm


def _make_edge(
    edge_id: str,
    from_node: str,
    from_content: str = "chunk text A",
    to_content: str = "chunk text B",
) -> dict:
    return {
        "id": edge_id,
        "from_node": from_node,
        "to_node": _NODE_Z,
        "edge_type": "CO_RETRIEVED",
        "weight": 0.85,
        "co_access_count": 7,
        "origin": "learner",
        "from_content": from_content,
        "to_content": to_content,
    }


def _make_discoverer(db: AsyncMock, llm_label: str = "CALLS") -> EdgeDiscoverer:
    async def _llm(prompt: str) -> str:
        return llm_label

    return EdgeDiscoverer(db=db, llm=_llm, batch_size=50)


# =============================================================================
# Tests
# =============================================================================


class TestDiscoverTypesEdges:
    """EdgeDiscoverer.discover() calls update_edge with the LLM label."""

    @pytest.mark.asyncio
    async def test_discover_types_candidate_edges(self) -> None:
        """update_edge is called for each candidate with the LLM-assigned label."""
        db = _make_db_mock()
        edge1 = _make_edge(_EDGE_A, _NODE_X)
        edge2 = _make_edge(_EDGE_B, _NODE_Y)
        db.fetch_candidate_edges = AsyncMock(return_value=[edge1, edge2])

        discoverer = _make_discoverer(db, llm_label="CALLS")
        await discoverer.discover()

        db.update_edge.assert_any_call(_EDGE_A, edge_type="CALLS", origin="discoverer")
        db.update_edge.assert_any_call(_EDGE_B, edge_type="CALLS", origin="discoverer")

    @pytest.mark.asyncio
    async def test_discover_returns_report_with_counts(self) -> None:
        """DiscoveryReport reflects the number of edges typed and LLM calls made."""
        db = _make_db_mock()
        # Two edges from different from_nodes → 2 clusters → 2 LLM calls
        edge1 = _make_edge(_EDGE_A, _NODE_X)
        edge2 = _make_edge(_EDGE_B, _NODE_Y)
        db.fetch_candidate_edges = AsyncMock(return_value=[edge1, edge2])

        discoverer = _make_discoverer(db, llm_label="DEPENDS_ON")
        report = await discoverer.discover()

        assert isinstance(report, DiscoveryReport)
        assert report.edges_typed == 2
        assert report.llm_calls == 2

    @pytest.mark.asyncio
    async def test_discover_clusters_same_from_node_into_one_llm_call(self):
        """Two edges sharing from_node use one LLM call, but both get typed."""
        db = _make_db_mock()
        edge1 = _make_edge(_EDGE_A, _NODE_X)
        edge2 = _make_edge(_EDGE_B, _NODE_X)  # same from_node as edge1
        db.fetch_candidate_edges = AsyncMock(return_value=[edge1, edge2])

        call_count = 0

        async def _counting_llm(prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            return "TRIGGERS"

        discoverer = EdgeDiscoverer(db=db, llm=_counting_llm, batch_size=50)
        report = await discoverer.discover()

        assert call_count == 1
        assert report.edges_typed == 2
        assert report.llm_calls == 1


class TestDiscoverSkipsOnEmpty:
    """discover() does nothing and does not call LLM when candidates are empty."""

    @pytest.mark.asyncio
    async def test_discover_skips_on_empty_candidates(self):
        """No candidates → DiscoveryReport(0, 0) and LLM is never called."""
        db = _make_db_mock()
        db.fetch_candidate_edges = AsyncMock(return_value=[])

        llm_called = False

        async def _llm(prompt: str) -> str:
            nonlocal llm_called
            llm_called = True
            return "CALLS"

        discoverer = EdgeDiscoverer(db=db, llm=_llm, batch_size=50)
        report = await discoverer.discover()

        assert report.edges_typed == 0
        assert report.llm_calls == 0
        assert not llm_called
        db.update_edge.assert_not_awaited()
        db.log_evolution.assert_not_awaited()


class TestClassifyRelationship:
    """_classify_relationship sends chunk text to LLM and normalises the result."""

    @pytest.mark.asyncio
    async def test_classify_relationship_calls_llm(self):
        """LLM prompt includes from_content and to_content of the edge."""
        db = _make_db_mock()
        received_prompt: list[str] = []

        async def _llm(prompt: str) -> str:
            received_prompt.append(prompt)
            return "CALLS"

        discoverer = EdgeDiscoverer(db=db, llm=_llm)
        edge = _make_edge(_EDGE_A, _NODE_X, from_content="service A code", to_content="service B code")
        await discoverer._classify_relationship(edge)

        assert len(received_prompt) == 1
        assert "service A code" in received_prompt[0]
        assert "service B code" in received_prompt[0]

    @pytest.mark.asyncio
    async def test_classify_relationship_normalizes_output(self):
        """LLM response with surrounding whitespace/newlines is stripped and uppercased."""
        db = _make_db_mock()

        async def _llm(prompt: str) -> str:
            return " calls\n"

        discoverer = EdgeDiscoverer(db=db, llm=_llm)
        edge = _make_edge(_EDGE_A, _NODE_X)
        result = await discoverer._classify_relationship(edge)

        assert result == "CALLS"


class TestClustering:
    """_cluster_by_content_similarity groups edges by from_node."""

    def test_clustering_groups_by_from_node(self) -> None:
        """Edges with the same from_node form one cluster; different from_nodes → two clusters."""
        db = _make_db_mock()
        discoverer = EdgeDiscoverer(db=db, llm=AsyncMock())

        edge1 = _make_edge(_EDGE_A, _NODE_X)
        edge2 = _make_edge(_EDGE_B, _NODE_X)  # same from_node
        edge3 = _make_edge("edge-c", _NODE_Y)  # different from_node

        clusters = discoverer._cluster_by_content_similarity([edge1, edge2, edge3])

        assert len(clusters) == 2
        cluster_sizes = sorted(len(c) for c in clusters)
        assert cluster_sizes == [1, 2]

    def test_clustering_single_from_node_is_one_cluster(self) -> None:
        """All edges from the same node → exactly one cluster."""
        db = _make_db_mock()
        discoverer = EdgeDiscoverer(db=db, llm=AsyncMock())

        edges = [_make_edge(f"e-{i}", _NODE_X) for i in range(4)]
        clusters = discoverer._cluster_by_content_similarity(edges)

        assert len(clusters) == 1
        assert len(clusters[0]) == 4


class TestEvolutionLogging:
    """log_evolution is called once per typed edge."""

    @pytest.mark.asyncio
    async def test_evolution_logged_for_each_typed_edge(self) -> None:
        """log_evolution is called for every edge, recording CO_RETRIEVED → new label."""
        db = _make_db_mock()
        edge1 = _make_edge(_EDGE_A, _NODE_X)
        edge2 = _make_edge(_EDGE_B, _NODE_Y)
        db.fetch_candidate_edges = AsyncMock(return_value=[edge1, edge2])

        discoverer = _make_discoverer(db, llm_label="VALIDATES")
        await discoverer.discover()

        assert db.log_evolution.await_count == 2
        db.log_evolution.assert_any_call(
            "edge_typed",
            _EDGE_A,
            {"edge_type": "CO_RETRIEVED"},
            {"edge_type": "VALIDATES"},
            "discoverer",
        )
        db.log_evolution.assert_any_call(
            "edge_typed",
            _EDGE_B,
            {"edge_type": "CO_RETRIEVED"},
            {"edge_type": "VALIDATES"},
            "discoverer",
        )
