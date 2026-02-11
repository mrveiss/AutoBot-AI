# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Relationship Model - Entity relationship representation for ECL pipeline.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

from datetime import datetime
from typing import List, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

RelationType = Literal[
    "CAUSES",
    "ENABLES",
    "PREVENTS",
    "TRIGGERS",
    "CONTAINS",
    "PART_OF",
    "COMPOSED_OF",
    "RELATES_TO",
    "SIMILAR_TO",
    "CONTRASTS_WITH",
    "PRECEDES",
    "FOLLOWS",
    "DURING",
    "IS_A",
    "INSTANCE_OF",
    "SUBTYPE_OF",
    "CREATED_BY",
    "AUTHORED_BY",
    "OWNED_BY",
    "IMPLEMENTS",
    "EXTENDS",
    "DEPENDS_ON",
    "USES",
]


class Relationship(BaseModel):
    """
    Represents a directed relationship between two entities.

    Relationships capture semantic connections extracted from text,
    with optional bidirectionality for symmetric relations.
    """

    id: UUID = Field(default_factory=uuid4, description="Unique relationship ID")
    source_entity_id: UUID = Field(
        ..., description="Source entity (subject of relationship)"
    )
    target_entity_id: UUID = Field(
        ..., description="Target entity (object of relationship)"
    )
    relationship_type: RelationType = Field(
        ..., description="Semantic relationship type"
    )
    description: str = Field(
        default="", description="Relationship description or context"
    )
    bidirectional: bool = Field(
        default=False,
        description="Whether relationship is symmetric (e.g., SIMILAR_TO)",
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Extraction confidence score"
    )
    source_chunk_ids: List[UUID] = Field(
        default_factory=list, description="Chunks where relationship was found"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Relationship creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )

    class Config:
        """Pydantic model configuration."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
        }
