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

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.quarantine_read_audit import audit_admin_quarantine_read, quarantined_row_ids
from api.schemas_knowledge_chroma import (
    ChromaSearchRequest,
    ChromaSearchResponse,
    CollectionDetailResponse,
    CollectionListResponse,
    CollectionMetadata,
    DocumentListResponse,
    SearchResultItem,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from utils.async_chromadb_client import get_async_chromadb_client

logger = get_logger(__name__)

# Prefix must NOT include "/api" — the app factory prepends it (#9864:
# the old "/api/knowledge/chroma" prefix served /api/api/knowledge/chroma/*,
# 404ing every ChromaDBExplorer call).
router = APIRouter(
    prefix="/knowledge/chroma",
    tags=["knowledge-chroma", "chroma"],
)

# Substrings ChromaDB uses to signal a genuinely missing collection, across
# versions (ValueError "does not exist" in <1.0, NotFoundError "not found" in
# 1.x). Detecting by message keeps a real internal error from being mislabeled
# as a 404 and vice versa.
_NOT_FOUND_MARKERS = ("does not exist", "not found", "not exist")


def _is_collection_not_found(exc: Exception) -> bool:
    """True when the exception indicates the collection genuinely doesn't exist."""
    return any(marker in str(exc).lower() for marker in _NOT_FOUND_MARKERS)


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
    _: bool = Depends(check_admin_permission),
) -> CollectionListResponse:
    """
    List all ChromaDB collections with metadata.

    Returns collection names, document counts, and metadata for all collections
    in the ChromaDB instance.

    Args:
        _: Admin permission check -- the raw explorer bypasses fact visibility (#16666)

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
    _: bool = Depends(check_admin_permission),
) -> CollectionDetailResponse:
    """
    Get detailed metadata for a specific collection.

    Args:
        name: Collection name
        _: Admin permission check -- the raw explorer bypasses fact visibility (#16666)

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

    except Exception as e:
        if _is_collection_not_found(e):
            logger.warning(f"Collection not found: {name}")
            raise HTTPException(
                status_code=404,
                detail=f"Collection '{name}' not found",
            )
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
    _: bool = Depends(check_admin_permission),
    request: Request = None,
) -> DocumentListResponse:
    """
    List documents in a collection with pagination.

    Args:
        name: Collection name
        limit: Maximum number of documents to return (1-1000)
        offset: Number of documents to skip for pagination
        _: Admin permission check -- the raw explorer bypasses fact visibility (#16666)

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

        # Add embedding dimensionality info.
        # ChromaDB 1.x returns embeddings as a numpy ndarray; bare truthiness
        # (`if results.get("embeddings")`) raises "truth value of an array is
        # ambiguous" — use `is not None` + len() which is numpy-safe.
        embedding_dim = None
        embeddings = results.get("embeddings")
        if embeddings is not None and len(embeddings) > 0:
            embedding_dim = len(embeddings[0])

        # Get total count
        total = await collection.count()

        # #19163: admins may see research-quarantined rows, but audited and labelled.
        ids = results.get("ids", [])
        metadatas = results.get("metadatas", [])
        quarantined = quarantined_row_ids(ids, metadatas or [])
        if quarantined:
            await audit_admin_quarantine_read(request, f"chroma.list_documents:{name}", quarantined)

        return DocumentListResponse(
            success=True,
            data={
                "ids": ids,
                "documents": results.get("documents", []),
                "metadatas": metadatas,
                "embedding_dim": embedding_dim,
                "quarantined_ids": quarantined,
            },
            total=total,
        )

    except Exception as e:
        # ChromaDB signals a genuinely missing collection differently across
        # versions (ValueError in <1.0, NotFoundError in 1.x) — detect by
        # message so a real internal error isn't mislabeled as 404 and vice versa.
        if _is_collection_not_found(e):
            logger.warning(f"Collection not found: {name}")
            raise HTTPException(
                status_code=404,
                detail=f"Collection '{name}' not found",
            )
        logger.error(f"Failed to list documents in collection {name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"ChromaDB error: {str(e)}",
        )


@router.post("/collections/{name}/search", response_model=ChromaSearchResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_chroma_collection",
    error_code_prefix="CHROMA",
)
async def search_collection(
    name: str,
    request: ChromaSearchRequest,
    _: bool = Depends(check_admin_permission),
    http_request: Request = None,
) -> ChromaSearchResponse:
    """
    Perform similarity search on a collection using query text.

    Uses the collection's embedding function to convert query text to vectors
    and performs similarity search.

    Args:
        name: Collection name
        request: Search parameters (query, n_results, where filter)
        _: Admin permission check -- the raw explorer bypasses fact visibility (#16666)

    Returns:
        ChromaSearchResponse with matching documents and similarity scores

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

            quarantined = set(quarantined_row_ids(ids, metadatas))
            for i, doc_id in enumerate(ids):
                search_results.append(
                    SearchResultItem(
                        id=doc_id,
                        document=documents[i] if i < len(documents) else None,
                        metadata=metadatas[i] if i < len(metadatas) else None,
                        distance=distances[i] if i < len(distances) else None,
                        quarantined=doc_id in quarantined,
                    )
                )
            if quarantined:
                await audit_admin_quarantine_read(http_request, f"chroma.search_collection:{name}", sorted(quarantined))

        return ChromaSearchResponse(
            success=True,
            data=search_results,
            query=request.query,
        )

    except HTTPException:
        raise
    except Exception as e:
        if _is_collection_not_found(e):
            logger.warning(f"Collection not found: {name}")
            raise HTTPException(
                status_code=404,
                detail=f"Collection '{name}' not found",
            )
        logger.error(f"Search failed in collection {name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"ChromaDB search error: {str(e)}",
        )
