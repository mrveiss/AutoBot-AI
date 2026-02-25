# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for SummarySearchService with mocked ChromaDB.

Issue #1075: Test coverage for summary search and drill-down.
"""

import logging
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from knowledge.summary_search import SummarySearchService

logger = logging.getLogger(__name__)


# --- Fixtures ---


@pytest.fixture
def mock_chromadb():
    return AsyncMock()


@pytest.fixture
def service(mock_chromadb):
    return SummarySearchService(mock_chromadb)


@pytest.fixture
def mock_collection():
    return AsyncMock()


# --- Search Summaries ---


class TestSearchSummaries:
    """Tests for search_summaries."""

    @pytest.mark.asyncio
    async def test_basic_search(self, service, mock_chromadb, mock_collection):
        mock_chromadb.get_collection.return_value = mock_collection
        mock_collection.query.return_value = {
            "ids": [["s1", "s2"]],
            "documents": [["Summary one", "Summary two"]],
            "metadatas": [[{"level": "chunk"}, {"level": "section"}]],
            "distances": [[0.1, 0.3]],
        }

        results = await service.search_summaries("test query")
        assert len(results) == 2
        assert results[0]["score"] == pytest.approx(0.9)
        assert results[0]["content"] == "Summary one"

    @pytest.mark.asyncio
    async def test_with_level_filter(self, service, mock_chromadb, mock_collection):
        mock_chromadb.get_collection.return_value = mock_collection
        mock_collection.query.return_value = {
            "ids": [["s1"]],
            "documents": [["Doc summary"]],
            "metadatas": [[{"level": "document"}]],
            "distances": [[0.05]],
        }

        await service.search_summaries("query", level="document")
        mock_collection.query.assert_called_once()
        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {"level": "document"}

    @pytest.mark.asyncio
    async def test_no_results(self, service, mock_chromadb, mock_collection):
        mock_chromadb.get_collection.return_value = mock_collection
        mock_collection.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        results = await service.search_summaries("nothing")
        assert results == []

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, service, mock_chromadb):
        mock_chromadb.get_collection.side_effect = Exception("Connection error")
        results = await service.search_summaries("query")
        assert results == []


# --- Document Overview ---


class TestGetDocumentOverview:
    """Tests for get_document_overview."""

    @pytest.mark.asyncio
    async def test_overview_with_data(self, service, mock_chromadb, mock_collection):
        doc_id = uuid4()
        mock_chromadb.get_collection.return_value = mock_collection

        mock_collection.get.side_effect = [
            {
                "ids": ["doc-sum"],
                "documents": ["Full document summary"],
                "metadatas": [{"level": "document"}],
            },
            {
                "ids": ["sec-1", "sec-2"],
                "documents": ["Section 1", "Section 2"],
                "metadatas": [{"level": "section"}, {"level": "section"}],
            },
        ]

        overview = await service.get_document_overview(doc_id)
        assert overview["document_id"] == str(doc_id)
        assert len(overview["document_summary"]) == 1
        assert len(overview["section_summaries"]) == 2

    @pytest.mark.asyncio
    async def test_overview_no_document_summary(
        self, service, mock_chromadb, mock_collection
    ):
        doc_id = uuid4()
        mock_chromadb.get_collection.return_value = mock_collection
        mock_collection.get.side_effect = [
            {"ids": [], "documents": [], "metadatas": []},
            {"ids": [], "documents": [], "metadatas": []},
        ]

        overview = await service.get_document_overview(doc_id)
        assert overview["document_summary"] == []
        assert overview["section_summaries"] == []

    @pytest.mark.asyncio
    async def test_overview_error_returns_empty(self, service, mock_chromadb):
        mock_chromadb.get_collection.side_effect = Exception("DB down")
        doc_id = uuid4()
        overview = await service.get_document_overview(doc_id)
        assert overview["document_summary"] is None
        assert overview["section_summaries"] == []


# --- Drill Down ---


class TestDrillDown:
    """Tests for drill_down."""

    @pytest.mark.asyncio
    async def test_drill_down_with_children(
        self, service, mock_chromadb, mock_collection
    ):
        summary_id = uuid4()
        mock_chromadb.get_collection.return_value = mock_collection

        mock_collection.get.side_effect = [
            {
                "ids": [str(summary_id)],
                "documents": ["Parent summary"],
                "metadatas": [{"level": "section"}],
            },
            {
                "ids": ["child-1", "child-2"],
                "documents": ["Child 1", "Child 2"],
                "metadatas": [{"level": "chunk"}, {"level": "chunk"}],
            },
        ]

        result = await service.drill_down(summary_id)
        assert result["summary"] is not None
        assert len(result["children"]) == 2
        assert result["level"] == "section"

    @pytest.mark.asyncio
    async def test_drill_down_not_found(self, service, mock_chromadb, mock_collection):
        mock_chromadb.get_collection.return_value = mock_collection
        mock_collection.get.return_value = {
            "ids": [],
            "documents": [],
            "metadatas": [],
        }

        result = await service.drill_down(uuid4())
        assert result["summary"] is None
        assert result["children"] == []

    @pytest.mark.asyncio
    async def test_drill_down_error(self, service, mock_chromadb):
        mock_chromadb.get_collection.side_effect = Exception("fail")
        result = await service.drill_down(uuid4())
        assert result["summary"] is None


# --- Result Formatting ---


class TestFormatResults:
    """Tests for _format_results helper."""

    def test_format_query_results(self, service):
        results = {
            "ids": [["id1", "id2"]],
            "documents": [["Doc 1", "Doc 2"]],
            "metadatas": [[{"level": "chunk"}, {"level": "section"}]],
            "distances": [[0.2, 0.5]],
        }
        formatted = service._format_results(results)
        assert len(formatted) == 2
        assert formatted[0]["score"] == pytest.approx(0.8)
        assert formatted[1]["id"] == "id2"

    def test_format_empty_results(self, service):
        assert service._format_results(None) == []
        assert service._format_results({}) == []
        assert service._format_results({"ids": None}) == []

    def test_format_no_distances(self, service):
        results = {
            "ids": [["id1"]],
            "documents": [["Doc"]],
            "metadatas": [[{"level": "chunk"}]],
        }
        formatted = service._format_results(results)
        assert formatted[0]["score"] == 1.0


class TestFormatGetResults:
    """Tests for _format_get_results helper."""

    def test_format_get_results(self, service):
        results = {
            "ids": ["id1", "id2"],
            "documents": ["Doc 1", "Doc 2"],
            "metadatas": [{"level": "chunk"}, {"level": "section"}],
        }
        formatted = service._format_get_results(results)
        assert len(formatted) == 2
        assert formatted[0]["id"] == "id1"
        assert formatted[1]["content"] == "Doc 2"

    def test_format_get_empty(self, service):
        assert service._format_get_results(None) == []
        assert service._format_get_results({"ids": []}) == []
