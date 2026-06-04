# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for NodePromoter — daily anchor emergence for Neural Mesh RAG (#2119)."""

from unittest.mock import AsyncMock

import pytest

from services.mesh_brain.node_promoter import NodePromoter

# =============================================================================
# Helpers
# =============================================================================

_NODE_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_NODE_ID_2 = "bbbbbbbb-0000-0000-0000-000000000002"
_ANCHOR_ID = "cccccccc-0000-0000-0000-000000000003"

_SUMMARY = "These chunks share a common theme about networking."


def _make_db() -> AsyncMock:
    """Return a MeshDB mock with safe defaults (no candidates, no stale anchors)."""
    db = AsyncMock()
    db.get_promotion_candidates = AsyncMock(return_value=[])
    db.get_stale_anchors = AsyncMock(return_value=[])
    db.get_neighborhood = AsyncMock(return_value=[])
    db.promote_to_anchor = AsyncMock()
    db.demote_anchor = AsyncMock()
    return db


def _make_chroma() -> AsyncMock:
    """Return a ChromaCollection mock."""
    chroma = AsyncMock()
    chroma.upsert = AsyncMock()
    chroma.delete = AsyncMock()
    return chroma


async def _llm(prompt: str) -> str:
    """Stub LLM callable that always returns a fixed summary."""
    return _SUMMARY


def _make_promoter(db: AsyncMock, chroma: AsyncMock) -> NodePromoter:
    return NodePromoter(
        db=db,
        llm=_llm,
        chroma_client=chroma,
        promote_access_threshold=50,
        promote_min_edges=5,
        demote_access_threshold=10,
        demote_days=30,
    )


def _candidate(node_id: str = _NODE_ID) -> dict:
    return {"id": node_id, "access_count": 60, "edge_count": 7}


def _stale_anchor(node_id: str = _ANCHOR_ID) -> dict:
    return {"id": node_id, "access_count": 3, "days_inactive": 45}


def _neighborhood(size: int = 3) -> list[dict]:
    return [{"id": f"n-{i}", "content": f"chunk content {i}"} for i in range(size)]


# =============================================================================
# Tests — promote hot nodes
# =============================================================================


class TestEvaluatePromotesHotNodes:
    """evaluate() calls promote_to_anchor for every returned candidate."""

    @pytest.mark.asyncio
    async def test_evaluate_promotes_hot_nodes(self) -> None:
        """When a candidate is returned, promote_to_anchor is called with its ID."""
        db = _make_db()
        db.get_promotion_candidates = AsyncMock(return_value=[_candidate()])
        db.get_neighborhood = AsyncMock(return_value=_neighborhood())
        chroma = _make_chroma()

        promoter = _make_promoter(db, chroma)
        report = await promoter.evaluate()

        db.promote_to_anchor.assert_awaited_once_with(_NODE_ID)
        assert _NODE_ID in report.nodes_promoted

    @pytest.mark.asyncio
    async def test_promote_passes_correct_thresholds(self) -> None:
        """get_promotion_candidates is called with the configured thresholds."""
        db = _make_db()
        chroma = _make_chroma()

        promoter = NodePromoter(
            db=db,
            llm=_llm,
            chroma_client=chroma,
            promote_access_threshold=100,
            promote_min_edges=8,
            demote_access_threshold=10,
            demote_days=30,
        )
        await promoter.evaluate()

        db.get_promotion_candidates.assert_awaited_once_with(min_access=100, min_edges=8)


# =============================================================================
# Tests — demote stale anchors
# =============================================================================


class TestEvaluateDemotesStaleAnchors:
    """evaluate() calls demote_anchor for every stale anchor returned."""

    @pytest.mark.asyncio
    async def test_evaluate_demotes_stale_anchors(self) -> None:
        """When a stale anchor is returned, demote_anchor is called with its ID."""
        db = _make_db()
        db.get_stale_anchors = AsyncMock(return_value=[_stale_anchor()])
        chroma = _make_chroma()

        promoter = _make_promoter(db, chroma)
        report = await promoter.evaluate()

        db.demote_anchor.assert_awaited_once_with(_ANCHOR_ID)
        assert _ANCHOR_ID in report.nodes_demoted

    @pytest.mark.asyncio
    async def test_demote_passes_correct_thresholds(self) -> None:
        """get_stale_anchors is called with the configured thresholds."""
        db = _make_db()
        chroma = _make_chroma()

        promoter = NodePromoter(
            db=db,
            llm=_llm,
            chroma_client=chroma,
            promote_access_threshold=50,
            promote_min_edges=5,
            demote_access_threshold=5,
            demote_days=60,
        )
        await promoter.evaluate()

        db.get_stale_anchors.assert_awaited_once_with(max_access=5, inactive_days=60)


# =============================================================================
# Tests — ChromaDB interactions
# =============================================================================


class TestPromoteStoresAnchorInChroma:
    """_promote_node upserts the neighborhood summary into mesh_anchors."""

    @pytest.mark.asyncio
    async def test_promote_stores_anchor_in_chroma(self) -> None:
        """chroma.upsert is called with collection='mesh_anchors' and correct id."""
        db = _make_db()
        db.get_promotion_candidates = AsyncMock(return_value=[_candidate()])
        db.get_neighborhood = AsyncMock(return_value=_neighborhood(size=3))
        chroma = _make_chroma()

        promoter = _make_promoter(db, chroma)
        await promoter.evaluate()

        chroma.upsert.assert_awaited_once()
        _, kwargs = chroma.upsert.call_args
        assert kwargs["collection"] == "mesh_anchors"
        assert kwargs["ids"] == [f"anchor_{_NODE_ID}"]
        assert kwargs["documents"] == [_SUMMARY]

    @pytest.mark.asyncio
    async def test_promote_metadata_contains_node_id_and_size(self) -> None:
        """Metadata passed to chroma.upsert includes node_id and neighborhood_size."""
        db = _make_db()
        neighborhood = _neighborhood(size=4)
        db.get_promotion_candidates = AsyncMock(return_value=[_candidate()])
        db.get_neighborhood = AsyncMock(return_value=neighborhood)
        chroma = _make_chroma()

        promoter = _make_promoter(db, chroma)
        await promoter.evaluate()

        _, kwargs = chroma.upsert.call_args
        meta = kwargs["metadatas"][0]
        assert meta["node_id"] == str(_NODE_ID)
        assert meta["neighborhood_size"] == 4


class TestDemoteRemovesFromChroma:
    """_demote_node calls chroma.delete with the anchor ID."""

    @pytest.mark.asyncio
    async def test_demote_removes_from_chroma(self) -> None:
        """chroma.delete is called with collection='mesh_anchors' and correct id."""
        db = _make_db()
        db.get_stale_anchors = AsyncMock(return_value=[_stale_anchor()])
        chroma = _make_chroma()

        promoter = _make_promoter(db, chroma)
        await promoter.evaluate()

        chroma.delete.assert_awaited_once_with(
            collection="mesh_anchors",
            ids=[f"anchor_{_ANCHOR_ID}"],
        )


# =============================================================================
# Tests — LLM neighborhood summary
# =============================================================================


class TestPromoteGeneratesNeighborhoodSummary:
    """_summarize_neighborhood passes neighborhood content to the LLM."""

    @pytest.mark.asyncio
    async def test_promote_generates_neighborhood_summary(self):
        """LLM is called once per promoted node and its result stored as the document."""
        db = _make_db()
        db.get_promotion_candidates = AsyncMock(return_value=[_candidate()])
        db.get_neighborhood = AsyncMock(return_value=_neighborhood(size=2))
        chroma = _make_chroma()

        llm_calls: list[str] = []

        async def recording_llm(prompt: str) -> str:
            llm_calls.append(prompt)
            return _SUMMARY

        promoter = NodePromoter(
            db=db,
            llm=recording_llm,
            chroma_client=chroma,
            promote_access_threshold=50,
            promote_min_edges=5,
            demote_access_threshold=10,
            demote_days=30,
        )
        await promoter.evaluate()

        assert len(llm_calls) == 1
        assert "chunk content 0" in llm_calls[0]
        assert "chunk content 1" in llm_calls[0]

    @pytest.mark.asyncio
    async def test_summarize_caps_neighborhood_at_ten_nodes(self):
        """Only the first 10 neighborhood nodes are included in the LLM prompt."""
        db = _make_db()
        db.get_promotion_candidates = AsyncMock(return_value=[_candidate()])
        db.get_neighborhood = AsyncMock(return_value=_neighborhood(size=15))
        chroma = _make_chroma()

        llm_calls: list[str] = []

        async def recording_llm(prompt: str) -> str:
            llm_calls.append(prompt)
            return _SUMMARY

        promoter = NodePromoter(
            db=db,
            llm=recording_llm,
            chroma_client=chroma,
            promote_access_threshold=50,
            promote_min_edges=5,
            demote_access_threshold=10,
            demote_days=30,
        )
        await promoter.evaluate()

        # Nodes 10-14 must not appear in the prompt
        assert "chunk content 10" not in llm_calls[0]
        assert "chunk content 9" in llm_calls[0]


# =============================================================================
# Tests — PromotionReport contents
# =============================================================================


class TestReportContents:
    """evaluate() returns a PromotionReport with the correct node ID lists."""

    @pytest.mark.asyncio
    async def test_report_contains_promoted_ids(self) -> None:
        """nodes_promoted contains all promoted node IDs."""
        db = _make_db()
        db.get_promotion_candidates = AsyncMock(return_value=[_candidate(_NODE_ID), _candidate(_NODE_ID_2)])
        db.get_neighborhood = AsyncMock(return_value=_neighborhood())
        chroma = _make_chroma()

        promoter = _make_promoter(db, chroma)
        report = await promoter.evaluate()

        assert _NODE_ID in report.nodes_promoted
        assert _NODE_ID_2 in report.nodes_promoted
        assert len(report.nodes_promoted) == 2

    @pytest.mark.asyncio
    async def test_report_contains_demoted_ids(self) -> None:
        """nodes_demoted contains all demoted node IDs."""
        db = _make_db()
        db.get_stale_anchors = AsyncMock(return_value=[_stale_anchor()])
        chroma = _make_chroma()

        promoter = _make_promoter(db, chroma)
        report = await promoter.evaluate()

        assert _ANCHOR_ID in report.nodes_demoted
        assert len(report.nodes_demoted) == 1

    @pytest.mark.asyncio
    async def test_no_candidates_returns_empty_report(self) -> None:
        """When there are no candidates and no stale anchors, both lists are empty."""
        db = _make_db()
        chroma = _make_chroma()

        promoter = _make_promoter(db, chroma)
        report = await promoter.evaluate()

        assert report.nodes_promoted == []
        assert report.nodes_demoted == []
        db.promote_to_anchor.assert_not_awaited()
        db.demote_anchor.assert_not_awaited()
        chroma.upsert.assert_not_awaited()
        chroma.delete.assert_not_awaited()
