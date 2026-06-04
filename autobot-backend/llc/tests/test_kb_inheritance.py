# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for KbInheritanceResolver (GH#8241)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from llc.kb.inheritance import KbInheritanceResolver

PARENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
CHILD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
GRANDCHILD_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")


def _make_org(org_id: uuid.UUID, parent_id=None, weight=0.6):
    org = MagicMock()
    org.id = org_id
    org.parent_org_id = parent_id
    org.kb_inheritance_weight = weight
    return org


@pytest.fixture
def rag_assembler():
    return MagicMock()


@pytest.fixture
def resolver(rag_assembler):
    return KbInheritanceResolver(rag_assembler=rag_assembler)


class TestGetQueryCollections:
    @pytest.mark.asyncio
    async def test_root_company_returns_single_collection(self, resolver):
        root_org = _make_org(PARENT_ID, parent_id=None)
        session = AsyncMock()
        session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=root_org))

        result = await resolver.get_query_collections(session, str(PARENT_ID))

        assert len(result) == 1
        collection_name, weight = result[0]
        assert collection_name == f"{PARENT_ID}:company"
        assert weight == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_child_returns_two_collections_with_weight_decay(self, resolver):
        parent_org = _make_org(PARENT_ID, parent_id=None, weight=0.6)
        child_org = _make_org(CHILD_ID, parent_id=PARENT_ID, weight=0.6)

        execute_results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=child_org)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=parent_org)),
        ]
        session = AsyncMock()
        session.execute.side_effect = execute_results

        result = await resolver.get_query_collections(session, str(CHILD_ID))

        assert len(result) == 2
        assert result[0] == (f"{CHILD_ID}:company", pytest.approx(1.0))
        assert result[1] == (f"{PARENT_ID}:company", pytest.approx(0.6))

    @pytest.mark.asyncio
    async def test_grandchild_returns_three_collections_with_compound_decay(self, resolver):
        parent_org = _make_org(PARENT_ID, parent_id=None, weight=0.6)
        child_org = _make_org(CHILD_ID, parent_id=PARENT_ID, weight=0.6)
        grandchild_org = _make_org(GRANDCHILD_ID, parent_id=CHILD_ID, weight=0.6)

        execute_results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=grandchild_org)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=child_org)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=parent_org)),
        ]
        session = AsyncMock()
        session.execute.side_effect = execute_results

        result = await resolver.get_query_collections(session, str(GRANDCHILD_ID))

        assert len(result) == 3
        assert result[0][1] == pytest.approx(1.0)
        assert result[1][1] == pytest.approx(0.6)
        assert result[2][1] == pytest.approx(0.36)

    @pytest.mark.asyncio
    async def test_missing_company_raises_value_error(self, resolver):
        session = AsyncMock()
        session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        with pytest.raises(ValueError, match="not found"):
            await resolver.get_query_collections(session, str(PARENT_ID))

    @pytest.mark.asyncio
    async def test_custom_weight_multiplier(self, resolver):
        parent_org = _make_org(PARENT_ID, parent_id=None, weight=0.5)
        child_org = _make_org(CHILD_ID, parent_id=PARENT_ID, weight=0.5)

        execute_results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=child_org)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=parent_org)),
        ]
        session = AsyncMock()
        session.execute.side_effect = execute_results

        result = await resolver.get_query_collections(session, str(CHILD_ID))

        assert result[1][1] == pytest.approx(0.5)


class TestSearchWithInheritance:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_collections(self, resolver):
        session = AsyncMock()
        session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        with pytest.raises(ValueError):
            await resolver.search_with_inheritance(session, str(PARENT_ID), "query")

    @pytest.mark.asyncio
    async def test_merges_and_reranks_by_weighted_score(self, resolver):
        parent_org = _make_org(PARENT_ID, parent_id=None, weight=0.6)
        child_org = _make_org(CHILD_ID, parent_id=PARENT_ID, weight=0.6)

        execute_results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=child_org)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=parent_org)),
        ]
        session = AsyncMock()
        session.execute.side_effect = execute_results

        child_context = MagicMock()
        child_context.chunks = [{"id": "doc-1", "content": "child doc", "similarity_score": 0.9}]
        parent_context = MagicMock()
        parent_context.chunks = [{"id": "doc-2", "content": "parent doc", "similarity_score": 1.0}]

        resolver.rag_assembler.assemble = AsyncMock(side_effect=[child_context, parent_context])

        results = await resolver.search_with_inheritance(session, str(CHILD_ID), "query", top_k=10)

        assert len(results) == 2
        assert results[0]["weighted_score"] >= results[1]["weighted_score"]
        assert results[0]["id"] == "doc-1"
        assert results[0]["source_company_id"] == str(CHILD_ID)

    @pytest.mark.asyncio
    async def test_deduplicates_by_doc_id_keeping_higher_weight(self, resolver):
        parent_org = _make_org(PARENT_ID, parent_id=None, weight=0.6)
        child_org = _make_org(CHILD_ID, parent_id=PARENT_ID, weight=0.6)

        execute_results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=child_org)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=parent_org)),
        ]
        session = AsyncMock()
        session.execute.side_effect = execute_results

        child_context = MagicMock()
        child_context.chunks = [{"id": "shared-doc", "content": "child version", "similarity_score": 0.8}]
        parent_context = MagicMock()
        parent_context.chunks = [{"id": "shared-doc", "content": "parent version", "similarity_score": 0.5}]

        resolver.rag_assembler.assemble = AsyncMock(side_effect=[child_context, parent_context])

        results = await resolver.search_with_inheritance(session, str(CHILD_ID), "query")

        assert len(results) == 1
        assert results[0]["source_company_id"] == str(CHILD_ID)
        assert results[0]["weighted_score"] == pytest.approx(0.8 * 1.0)

    @pytest.mark.asyncio
    async def test_work_item_id_propagated_to_assemble(self, resolver):
        """work_item_id context filter must reach every rag_assembler.assemble() call (GH#8599)."""
        parent_org = _make_org(PARENT_ID, parent_id=None, weight=0.6)
        child_org = _make_org(CHILD_ID, parent_id=PARENT_ID, weight=0.6)

        execute_results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=child_org)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=parent_org)),
        ]
        session = AsyncMock()
        session.execute.side_effect = execute_results

        empty_context = MagicMock()
        empty_context.chunks = []
        resolver.rag_assembler.assemble = AsyncMock(return_value=empty_context)

        work_item_id = str(uuid.uuid4())
        await resolver.search_with_inheritance(session, str(CHILD_ID), "query", work_item_id=work_item_id)

        for call in resolver.rag_assembler.assemble.call_args_list:
            assert call.kwargs.get("work_item_id") == work_item_id, f"work_item_id not propagated in call: {call}"
