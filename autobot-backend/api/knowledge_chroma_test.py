# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for ChromaDB REST API endpoints (MVA-2046).

Tests all 4 endpoints with success cases, error cases, and edge cases.
Uses pytest with async test support and mocks ChromaDB client.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.knowledge_chroma import (
    SearchRequest,
    get_collection_detail,
    list_collections,
    list_documents,
    search_collection,
)


@pytest.fixture
def mock_current_user():
    """Mock authenticated user."""
    return {"email": "test@example.com", "role": "user"}


@pytest.fixture
def mock_chroma_client():
    """Mock AsyncChromaClient."""
    client = AsyncMock()
    client.list_collections = AsyncMock(return_value=["test_collection", "docs"])
    return client


@pytest.fixture
def mock_chroma_collection():
    """Mock AsyncChromaCollection."""
    collection = AsyncMock()
    collection.name = "test_collection"
    collection.metadata = {"description": "Test collection"}
    collection.count = AsyncMock(return_value=42)
    return collection


# =============================================================================
# Test list_collections endpoint
# =============================================================================


@pytest.mark.asyncio
async def test_list_collections_success(mock_current_user, mock_chroma_client, mock_chroma_collection):
    """Test successful listing of all collections."""
    mock_chroma_client.get_collection = AsyncMock(return_value=mock_chroma_collection)

    with patch("api.knowledge_chroma.get_async_chromadb_client", return_value=mock_chroma_client):
        response = await list_collections(current_user=mock_current_user)

    assert response.success is True
    assert len(response.data) == 2
    assert response.data[0].name == "test_collection"
    assert response.data[0].count == 42
    assert response.error is None


@pytest.mark.asyncio
async def test_list_collections_partial_failure(mock_current_user, mock_chroma_client):
    """Test listing collections when one collection fails to load."""
    # First collection succeeds, second fails
    good_collection = AsyncMock()
    good_collection.name = "good"
    good_collection.metadata = {}
    good_collection.count = AsyncMock(return_value=10)

    async def get_collection_side_effect(name):
        if name == "test_collection":
            return good_collection
        raise Exception("Collection unavailable")

    mock_chroma_client.get_collection = AsyncMock(side_effect=get_collection_side_effect)

    with patch("api.knowledge_chroma.get_async_chromadb_client", return_value=mock_chroma_client):
        response = await list_collections(current_user=mock_current_user)

    # Should still return data with partial results
    assert response.success is True
    assert len(response.data) == 2
    # First collection has full data
    assert response.data[0].count == 10
    # Second collection has partial data (count=0, no metadata)
    assert response.data[1].count == 0
    assert response.data[1].metadata is None


@pytest.mark.asyncio
async def test_list_collections_connection_error(mock_current_user):
    """Test handling of ChromaDB connection failure."""
    with patch("api.knowledge_chroma.get_async_chromadb_client", side_effect=Exception("Connection failed")):
        with pytest.raises(HTTPException) as exc_info:
            await list_collections(current_user=mock_current_user)

    assert exc_info.value.status_code == 500
    assert "ChromaDB connection error" in exc_info.value.detail


# =============================================================================
# Test get_collection_detail endpoint
# =============================================================================


@pytest.mark.asyncio
async def test_get_collection_detail_success(mock_current_user, mock_chroma_client, mock_chroma_collection):
    """Test successful retrieval of collection details."""
    mock_chroma_client.get_collection = AsyncMock(return_value=mock_chroma_collection)

    with patch("api.knowledge_chroma.get_async_chromadb_client", return_value=mock_chroma_client):
        response = await get_collection_detail(name="test_collection", current_user=mock_current_user)

    assert response.success is True
    assert response.data.name == "test_collection"
    assert response.data.count == 42
    assert response.data.metadata == {"description": "Test collection"}
    assert response.error is None


@pytest.mark.asyncio
async def test_get_collection_detail_not_found(mock_current_user, mock_chroma_client):
    """Test 404 when collection doesn't exist."""
    mock_chroma_client.get_collection = AsyncMock(side_effect=ValueError("Collection not found"))

    with patch("api.knowledge_chroma.get_async_chromadb_client", return_value=mock_chroma_client):
        with pytest.raises(HTTPException) as exc_info:
            await get_collection_detail(name="nonexistent", current_user=mock_current_user)

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_collection_detail_connection_error(mock_current_user, mock_chroma_client):
    """Test 500 on ChromaDB connection error."""
    mock_chroma_client.get_collection = AsyncMock(side_effect=Exception("Connection lost"))

    with patch("api.knowledge_chroma.get_async_chromadb_client", return_value=mock_chroma_client):
        with pytest.raises(HTTPException) as exc_info:
            await get_collection_detail(name="test_collection", current_user=mock_current_user)

    assert exc_info.value.status_code == 500
    assert "ChromaDB error" in exc_info.value.detail


# =============================================================================
# Test list_documents endpoint
# =============================================================================


@pytest.mark.asyncio
async def test_list_documents_success(mock_current_user, mock_chroma_client, mock_chroma_collection):
    """Test successful listing of documents with pagination."""
    mock_chroma_collection.get = AsyncMock(
        return_value={
            "ids": ["doc1", "doc2", "doc3"],
            "documents": ["Text 1", "Text 2", "Text 3"],
            "metadatas": [{"source": "a"}, {"source": "b"}, {"source": "c"}],
            "embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]],
        }
    )

    mock_chroma_client.get_collection = AsyncMock(return_value=mock_chroma_collection)

    with patch("api.knowledge_chroma.get_async_chromadb_client", return_value=mock_chroma_client):
        response = await list_documents(
            name="test_collection",
            limit=100,
            offset=0,
            current_user=mock_current_user,
        )

    assert response.success is True
    assert response.total == 42  # From mock collection count
    assert response.data["embedding_dim"] == 3
    assert len(response.data["ids"]) == 3
    assert response.data["ids"][0] == "doc1"

    # Verify pagination parameters were passed
    mock_chroma_collection.get.assert_called_once()
    call_kwargs = mock_chroma_collection.get.call_args.kwargs
    assert call_kwargs["limit"] == 100
    assert call_kwargs["offset"] == 0


@pytest.mark.asyncio
async def test_list_documents_pagination(mock_current_user, mock_chroma_client, mock_chroma_collection):
    """Test pagination parameters are correctly passed."""
    mock_chroma_collection.get = AsyncMock(
        return_value={
            "ids": ["doc4", "doc5"],
            "documents": ["Text 4", "Text 5"],
            "metadatas": [{}, {}],
            "embeddings": [[0.1], [0.2]],
        }
    )

    mock_chroma_client.get_collection = AsyncMock(return_value=mock_chroma_collection)

    with patch("api.knowledge_chroma.get_async_chromadb_client", return_value=mock_chroma_client):
        response = await list_documents(
            name="test_collection",
            limit=50,
            offset=100,
            current_user=mock_current_user,
        )

    # Verify pagination was used
    call_kwargs = mock_chroma_collection.get.call_args.kwargs
    assert call_kwargs["limit"] == 50
    assert call_kwargs["offset"] == 100


@pytest.mark.asyncio
async def test_list_documents_empty_collection(mock_current_user, mock_chroma_client, mock_chroma_collection):
    """Test listing documents from empty collection."""
    mock_chroma_collection.get = AsyncMock(
        return_value={
            "ids": [],
            "documents": [],
            "metadatas": [],
            "embeddings": [],
        }
    )
    mock_chroma_collection.count = AsyncMock(return_value=0)

    mock_chroma_client.get_collection = AsyncMock(return_value=mock_chroma_collection)

    with patch("api.knowledge_chroma.get_async_chromadb_client", return_value=mock_chroma_client):
        response = await list_documents(
            name="empty_collection",
            current_user=mock_current_user,
        )

    assert response.success is True
    assert response.total == 0
    assert response.data["embedding_dim"] is None
    assert len(response.data["ids"]) == 0


@pytest.mark.asyncio
async def test_list_documents_not_found(mock_current_user, mock_chroma_client):
    """Test 404 when collection doesn't exist."""
    mock_chroma_client.get_collection = AsyncMock(side_effect=ValueError("Not found"))

    with patch("api.knowledge_chroma.get_async_chromadb_client", return_value=mock_chroma_client):
        with pytest.raises(HTTPException) as exc_info:
            await list_documents(name="nonexistent", current_user=mock_current_user)

    assert exc_info.value.status_code == 404


# =============================================================================
# Test search_collection endpoint
# =============================================================================


@pytest.mark.asyncio
async def test_search_collection_success(mock_current_user, mock_chroma_client, mock_chroma_collection):
    """Test successful similarity search."""
    mock_chroma_collection.query = AsyncMock(
        return_value={
            "ids": [["doc1", "doc2"]],
            "documents": [["Match 1", "Match 2"]],
            "metadatas": [[{"score": 0.9}, {"score": 0.8}]],
            "distances": [[0.1, 0.2]],
        }
    )

    mock_chroma_client.get_collection = AsyncMock(return_value=mock_chroma_collection)

    search_req = SearchRequest(query="test query", n_results=10)

    with patch("api.knowledge_chroma.get_async_chromadb_client", return_value=mock_chroma_client):
        response = await search_collection(
            name="test_collection",
            request=search_req,
            current_user=mock_current_user,
        )

    assert response.success is True
    assert response.query == "test query"
    assert len(response.data) == 2
    assert response.data[0].id == "doc1"
    assert response.data[0].document == "Match 1"
    assert response.data[0].distance == 0.1

    # Verify search parameters
    mock_chroma_collection.query.assert_called_once()
    call_kwargs = mock_chroma_collection.query.call_args.kwargs
    assert call_kwargs["query_texts"] == ["test query"]
    assert call_kwargs["n_results"] == 10


@pytest.mark.asyncio
async def test_search_collection_with_filter(mock_current_user, mock_chroma_client, mock_chroma_collection):
    """Test search with metadata filter."""
    mock_chroma_collection.query = AsyncMock(
        return_value={
            "ids": [["doc1"]],
            "documents": [["Filtered match"]],
            "metadatas": [[{"category": "tech"}]],
            "distances": [[0.1]],
        }
    )

    mock_chroma_client.get_collection = AsyncMock(return_value=mock_chroma_collection)

    search_req = SearchRequest(query="test", n_results=5, where={"category": "tech"})

    with patch("api.knowledge_chroma.get_async_chromadb_client", return_value=mock_chroma_client):
        response = await search_collection(
            name="test_collection",
            request=search_req,
            current_user=mock_current_user,
        )

    # Verify filter was passed
    call_kwargs = mock_chroma_collection.query.call_args.kwargs
    assert call_kwargs["where"] == {"category": "tech"}


@pytest.mark.asyncio
async def test_search_collection_empty_query(mock_current_user, mock_chroma_client):
    """Test 400 error for empty query."""
    search_req = SearchRequest(query="", n_results=10)

    with patch("api.knowledge_chroma.get_async_chromadb_client", return_value=mock_chroma_client):
        with pytest.raises(HTTPException) as exc_info:
            await search_collection(
                name="test_collection",
                request=search_req,
                current_user=mock_current_user,
            )

    assert exc_info.value.status_code == 400
    assert "empty" in exc_info.value.detail


@pytest.mark.asyncio
async def test_search_collection_whitespace_query(mock_current_user, mock_chroma_client):
    """Test 400 error for whitespace-only query."""
    search_req = SearchRequest(query="   ", n_results=10)

    with patch("api.knowledge_chroma.get_async_chromadb_client", return_value=mock_chroma_client):
        with pytest.raises(HTTPException) as exc_info:
            await search_collection(
                name="test_collection",
                request=search_req,
                current_user=mock_current_user,
            )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_search_collection_no_results(mock_current_user, mock_chroma_client, mock_chroma_collection):
    """Test search returning no results."""
    mock_chroma_collection.query = AsyncMock(
        return_value={
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
    )

    mock_chroma_client.get_collection = AsyncMock(return_value=mock_chroma_collection)

    search_req = SearchRequest(query="no matches", n_results=10)

    with patch("api.knowledge_chroma.get_async_chromadb_client", return_value=mock_chroma_client):
        response = await search_collection(
            name="test_collection",
            request=search_req,
            current_user=mock_current_user,
        )

    assert response.success is True
    assert response.data == []


@pytest.mark.asyncio
async def test_search_collection_not_found(mock_current_user, mock_chroma_client):
    """Test 404 when collection doesn't exist."""
    mock_chroma_client.get_collection = AsyncMock(side_effect=ValueError("Not found"))

    search_req = SearchRequest(query="test", n_results=10)

    with patch("api.knowledge_chroma.get_async_chromadb_client", return_value=mock_chroma_client):
        with pytest.raises(HTTPException) as exc_info:
            await search_collection(
                name="nonexistent",
                request=search_req,
                current_user=mock_current_user,
            )

    assert exc_info.value.status_code == 404
