# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request/response schemas for the ChromaDB explorer API (api/knowledge_chroma.py)."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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


class ChromaSearchRequest(BaseModel):
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
    quarantined: bool = Field(False, description="Research-quarantined fact, read through the audited opt-out (#19163)")


class ChromaSearchResponse(BaseModel):
    """Response for similarity search."""

    success: bool = True
    data: Optional[List[SearchResultItem]] = None
    query: Optional[str] = None
    error: Optional[str] = None
