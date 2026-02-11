# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Summary Model - Hierarchical summary representation for ECL pipeline.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

SummaryLevel = Literal["chunk", "section", "document"]


class Summary(BaseModel):
    """
    Represents a hierarchical summary of text content.

    Summaries can be generated at chunk, section, or document level
    with parent-child relationships for drill-down navigation.
    """

    id: UUID = Field(default_factory=uuid4, description="Unique summary ID")
    content: str = Field(..., description="Summary text")
    level: SummaryLevel = Field(..., description="Summary hierarchy level")
    parent_summary_id: Optional[UUID] = Field(
        None, description="Parent summary ID (for hierarchical navigation)"
    )
    child_summary_ids: List[UUID] = Field(
        default_factory=list, description="Child summary IDs (for drill-down)"
    )
    source_chunk_ids: List[UUID] = Field(
        default_factory=list, description="Source chunks summarized"
    )
    source_document_id: UUID = Field(..., description="Source document ID")
    key_topics: List[str] = Field(
        default_factory=list, description="Main topics covered in summary"
    )
    key_entities: List[UUID] = Field(
        default_factory=list, description="Key entities mentioned in summary"
    )
    word_count: int = Field(default=0, description="Number of words in summary")
    compression_ratio: float = Field(
        default=0.0, description="Ratio of summary to original text length"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Summary creation timestamp"
    )

    class Config:
        """Pydantic model configuration."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
        }
