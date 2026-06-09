# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ChromaDB REST API endpoints for frontend explorer UI.

Issue MVA-2046: Provides REST API to expose ChromaDB collections and documents.
Endpoints support listing collections, getting details, browsing documents,
and performing similarity searches.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from utils.async_chromadb_client import get_async_chromadb_client

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/knowledge/chroma",
    tags=["knowledge-chroma", "chroma"],
)


# ============================================================================
# Pydantic Models
# ============================================================================


class CollectionMetadata(BaseModel):
    """Metadata for a ChromaDB collection."""

    name: str = Field(..., description="Collection name")
    count: int = Field(..., description="Number of documents in collection")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Collection metadata")


class CollectionListResponse(BaseModel):
    """Response for listing all collections."""

    success: bool = True
    data: List[CollectionMetadata]
    error: Optional[str] = None


class CollectionDetailResponse(BaseModel):
    """Response for getting collection details."""

    success: bool = True
    data: Optional[CollectionMetadata] = None
    error: Optional[str] = None


class DocumentItem(BaseModel):
    """A document in a collection."""

    id: str = Field(..., description="Document ID")
    document: Optional[str] = Field(None, description="Document text content")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Document metadata")
    embedding_dim: Optional[int] = Field(None, description="Embedding vector dimensionality")


class DocumentListResponse(BaseModel):
    """Response for listing documents in a collection."""

    success: bool = True
    data: Optional[Dict[str, Any]] = Field(
        None,
        description="Documents with ids, documents, metadatas, embeddings summary",
    )
    total: Optional[int] = Field(None, description="Total document count")
    error: Optional[str] = None


class SearchRequest(BaseModel):
    """Request for similarity search."""

    query: str = Field(..., description="Query text for similarity search")
    n_results: int = Field(10, ge=1, le=100, description="Number of results to return")
    where: Optional[Dict[str, Any]] = Field(None, description="Metadata filter (ChromaDB where clause)")


class SearchResultItem(BaseModel):
    """A single search result."""

    id: str
    document: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    distance: Optional[float] = Field(None, description="Similarity distance score")


class SearchResponse(BaseModel):
    """Response for similarity search."""

    success: bool = True
    data: Optional[List[SearchResultItem]] = None
    query: Optional[str] = None
    error: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/collections", response_model=CollectionListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_chroma_collections",
    error_code_prefix="CHROMA",
)
async def list_collections(
    current_user: dict = Depends(get_current_user),
) -> CollectionListResponse:
    """
    List all ChromaDB collections with metadata.

    Returns collection names, document counts, and metadata for all collections
    in the ChromaDB instance.

    Args:
        current_user: Authenticated user (injected by auth middleware)

    Returns:
        CollectionListResponse with list of collections and their metadata

    Raises:
        HTTPException: 500 if ChromaDB connection fails
    """
    try:
        client = await get_async_chromadb_client()
        collection_names = await client.list_collections()

        collections_data = []
        for name in collection_names:
            try:
                collection = await client.get_collection(name)
                count = await collection.count()
                collections_data.append(
                    CollectionMetadata(
                        name=name,
                        count=count,
                        metadata=collection.metadata,
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to get metadata for collection {name}: {e}")
                # Include collection with partial data
                collections_data.append(CollectionMetadata(name=name, count=0, metadata=None))

        return CollectionListResponse(success=True, data=collections_data)

    except Exception as e:
        logger.error(f"Failed to list ChromaDB collections: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"ChromaDB connection error: {str(e)}",
        )


@router.get("/collections/{name}", response_model=CollectionDetailResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_chroma_collection",
    error_code_prefix="CHROMA",
)
async def get_collection_detail(
    name: str,
    current_user: dict = Depends(get_current_user),
) -> CollectionDetailResponse:
    """
    Get detailed metadata for a specific collection.

    Args:
        name: Collection name
        current_user: Authenticated user (injected by auth middleware)

    Returns:
        CollectionDetailResponse with collection metadata

    Raises:
        HTTPException: 404 if collection not found, 500 on connection error
    """
    try:
        client = await get_async_chromadb_client()
        collection = await client.get_collection(name)
        count = await collection.count()

        return CollectionDetailResponse(
            success=True,
            data=CollectionMetadata(
                name=name,
                count=count,
                metadata=collection.metadata,
            ),
        )

    except ValueError:
        # ChromaDB raises ValueError for missing collection
        logger.warning(f"Collection not found: {name}")
        raise HTTPException(
            status_code=404,
            detail=f"Collection '{name}' not found",
        )
    except Exception as e:
        logger.error(f"Failed to get collection {name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"ChromaDB error: {str(e)}",
        )


@router.get("/collections/{name}/documents", response_model=DocumentListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_chroma_documents",
    error_code_prefix="CHROMA",
)
async def list_documents(
    name: str,
    limit: int = Query(100, ge=1, le=1000, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    current_user: dict = Depends(get_current_user),
) -> DocumentListResponse:
    """
    List documents in a collection with pagination.

    Args:
        name: Collection name
        limit: Maximum number of documents to return (1-1000)
        offset: Number of documents to skip for pagination
        current_user: Authenticated user (injected by auth middleware)

    Returns:
        DocumentListResponse with document data (ids, documents, metadatas, embeddings)

    Raises:
        HTTPException: 404 if collection not found, 500 on error
    """
    try:
        client = await get_async_chromadb_client()
        collection = await client.get_collection(name)

        # Get documents with pagination
        results = await collection.get(
            limit=limit,
            offset=offset,
            include=["documents", "metadatas", "embeddings"],
        )

        # Add embedding dimensionality info
        embedding_dim = None
        if results.get("embeddings") and len(results["embeddings"]) > 0:
            embedding_dim = len(results["embeddings"][0])

        # Get total count
        total = await collection.count()

        return DocumentListResponse(
            success=True,
            data={
                "ids": results.get("ids", []),
                "documents": results.get("documents", []),
                "metadatas": results.get("metadatas", []),
                "embedding_dim": embedding_dim,
            },
            total=total,
        )

    except ValueError:
        logger.warning(f"Collection not found: {name}")
        raise HTTPException(
            status_code=404,
            detail=f"Collection '{name}' not found",
        )
    except Exception as e:
        logger.error(f"Failed to list documents in collection {name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"ChromaDB error: {str(e)}",
        )


@router.post("/collections/{name}/search", response_model=SearchResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_chroma_collection",
    error_code_prefix="CHROMA",
)
async def search_collection(
    name: str,
    request: SearchRequest,
    current_user: dict = Depends(get_current_user),
) -> SearchResponse:
    """
    Perform similarity search on a collection using query text.

    Uses the collection's embedding function to convert query text to vectors
    and performs similarity search.

    Args:
        name: Collection name
        request: Search parameters (query, n_results, where filter)
        current_user: Authenticated user (injected by auth middleware)

    Returns:
        SearchResponse with matching documents and similarity scores

    Raises:
        HTTPException: 400 for invalid parameters, 404 if collection not found,
                      500 on search error
    """
    try:
        if not request.query or not request.query.strip():
            raise HTTPException(
                status_code=400,
                detail="Query text cannot be empty",
            )

        client = await get_async_chromadb_client()
        collection = await client.get_collection(name)

        # Perform search using query_texts (ChromaDB will handle embedding)
        results = await collection.query(
            query_texts=[request.query],
            n_results=request.n_results,
            where=request.where,
            include=["documents", "metadatas", "distances"],
        )

        # Format results into flat list (query returns nested lists)
        search_results = []
        if results.get("ids") and len(results["ids"]) > 0:
            ids = results["ids"][0]
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            for i, doc_id in enumerate(ids):
                search_results.append(
                    SearchResultItem(
                        id=doc_id,
                        document=documents[i] if i < len(documents) else None,
                        metadata=metadatas[i] if i < len(metadatas) else None,
                        distance=distances[i] if i < len(distances) else None,
                    )
                )

        return SearchResponse(
            success=True,
            data=search_results,
            query=request.query,
        )

    except HTTPException:
        raise
    except ValueError:
        logger.warning(f"Collection not found: {name}")
        raise HTTPException(
            status_code=404,
            detail=f"Collection '{name}' not found",
        )
    except Exception as e:
        logger.error(f"Search failed in collection {name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"ChromaDB search error: {str(e)}",
        )
