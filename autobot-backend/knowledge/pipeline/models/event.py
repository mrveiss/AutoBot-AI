# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Event Model - Temporal event representation for ECL pipeline.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

TemporalType = Literal["point", "range", "relative", "recurring"]
EventType = Literal["action", "decision", "change", "milestone", "occurrence"]


class TemporalEvent(BaseModel):
    """
    Represents a temporal event extracted from document processing.

    Events capture time-bound occurrences with participants, locations,
    and temporal expressions (absolute or relative).
    """

    id: UUID = Field(default_factory=uuid4, description="Unique event ID")
    name: str = Field(..., description="Event name or title")
    description: str = Field(default="", description="Event description or summary")
    timestamp: Optional[datetime] = Field(
        None, description="Absolute event timestamp (if known)"
    )
    date_range_start: Optional[datetime] = Field(
        None, description="Range start (for duration events)"
    )
    date_range_end: Optional[datetime] = Field(
        None, description="Range end (for duration events)"
    )
    temporal_expression: str = Field(
        default="", description="Original temporal expression from text"
    )
    temporal_type: TemporalType = Field(..., description="Temporal classification")
    participants: List[UUID] = Field(
        default_factory=list, description="Entity IDs of event participants"
    )
    location: Optional[str] = Field(None, description="Event location (if mentioned)")
    event_type: EventType = Field(..., description="Event classification")
    source_chunk_ids: List[UUID] = Field(
        default_factory=list, description="Chunks where event was mentioned"
    )
    source_document_id: UUID = Field(..., description="Source document ID")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Extraction confidence score"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Event creation timestamp"
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
