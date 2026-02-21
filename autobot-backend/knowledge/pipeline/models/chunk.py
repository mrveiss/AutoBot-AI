# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chunk Model - ProcessedChunk representation for ECL pipeline.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    """Return timezone-aware UTC now (replaces deprecated datetime.utcnow)."""
    return datetime.now(timezone.utc)


class ProcessedChunk(BaseModel):
    """
    Represents a processed chunk of text from a document.

    Each chunk maintains references to its source document and position
    within that document, along with metadata for downstream processing.
    """

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat(), UUID: str},
    )

    id: UUID = Field(default_factory=uuid4, description="Unique chunk identifier")
    content: str = Field(..., description="Chunk text content")
    document_id: UUID = Field(..., description="Source document ID")
    chunk_index: int = Field(..., description="Position in document (0-based)")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (language, section, etc.)",
    )
    document_type: str = Field(
        default="unknown",
        description="Document classification (technical, narrative, etc.)",
    )
    start_offset: int = Field(
        default=0, description="Character offset where chunk starts in document"
    )
    end_offset: int = Field(
        default=0, description="Character offset where chunk ends in document"
    )
    created_at: datetime = Field(
        default_factory=_utcnow, description="Chunk creation timestamp"
    )
