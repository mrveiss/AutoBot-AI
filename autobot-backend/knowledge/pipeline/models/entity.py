# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Entity Model - Extracted entity representation for ECL pipeline.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

EntityType = Literal[
    "PERSON",
    "ORGANIZATION",
    "CONCEPT",
    "TECHNOLOGY",
    "LOCATION",
    "EVENT",
    "DOCUMENT",
    "USER",  # Issue #870: User entity for chat sessions and ownership tracking
]


def _utcnow() -> datetime:
    """Return timezone-aware UTC now (replaces deprecated datetime.utcnow)."""
    return datetime.now(timezone.utc)


class Entity(BaseModel):
    """
    Represents an extracted entity from document processing.

    Entities are named objects, concepts, or things identified in text
    with relationships to other entities and supporting evidence.
    """

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat(), UUID: str},
    )

    id: UUID = Field(default_factory=uuid4, description="Unique entity ID")
    name: str = Field(..., description="Entity name as mentioned in text")
    canonical_name: str = Field(
        ..., description="Normalized/standardized name for deduplication"
    )
    entity_type: EntityType = Field(..., description="Entity classification type")
    description: str = Field(default="", description="Entity description or summary")
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional entity properties (role, title, etc.)",
    )
    source_chunk_ids: List[UUID] = Field(
        default_factory=list, description="Chunks where entity was mentioned"
    )
    source_document_id: UUID = Field(..., description="Primary source document ID")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Extraction confidence score"
    )
    extraction_count: int = Field(
        default=1, description="Number of times entity was extracted"
    )
    created_at: datetime = Field(
        default_factory=_utcnow, description="Entity creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=_utcnow, description="Last update timestamp"
    )
