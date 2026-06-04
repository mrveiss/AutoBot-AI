# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Causal Edge Model - Causal relationship representation for ECL pipeline.

Issue #3395: RAG semantic chunking, fact extraction, entity resolution.
"""

from datetime import datetime
from typing import List, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from autobot_shared.time_utils import now_utc

EffectType = Literal[
    "CAUSES",
    "ENABLES",
    "PREVENTS",
    "AMPLIFIES",
    "REDUCES",
    "INHIBITS",
    "ACCELERATES",
    "DECELERATES",
]


def _utcnow() -> datetime:
    """Return timezone-aware UTC now (replaces deprecated datetime.utcnow)."""
    return now_utc()


class CausalEdge(BaseModel):
    """
    Represents an extracted causal relationship between two entities.

    Distinguishes explicit causality ("X CAUSES Y") from correlation
    ("X and Y both increase"). Includes condition/context for when the
    causal link holds.

    Issue #3395: Extract causal knowledge for RAG graph structure.
    """

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat(), UUID: str},
    )

    id: UUID = Field(default_factory=uuid4, description="Unique causal edge ID")
    source_name: str = Field(..., description="Cause entity name (e.g., 'cache_ttl')")
    source_entity_id: UUID | None = Field(
        default=None,
        description="Source entity UUID if resolved to Knowledge Base entity",
    )
    target_name: str = Field(..., description="Effect entity name (e.g., 'query_latency')")
    target_entity_id: UUID | None = Field(
        default=None,
        description="Target entity UUID if resolved to Knowledge Base entity",
    )
    effect_type: EffectType = Field(..., description="Type of causal effect (CAUSES, ENABLES, PREVENTS, etc.)")
    condition: str = Field(
        default="",
        description="Condition under which causality holds (e.g., 'when cache is full')",
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence score (1.0=explicit, <0.7=inferred)",
    )
    evidence_text: str = Field(default="", description="Quoted evidence sentence from source text")
    evidence_source: str | None = Field(default=None, description="Source document/section identifier")
    source_chunk_ids: List[UUID] = Field(default_factory=list, description="Chunks where relationship was extracted")
    bidirectional: bool = Field(
        default=False,
        description="Whether the inverse relationship also holds (rare for causality)",
    )
    created_at: datetime = Field(default_factory=_utcnow, description="Causal edge creation timestamp")
    updated_at: datetime = Field(default_factory=_utcnow, description="Last update timestamp")

    def to_causal_string(self) -> str:
        """Format as human-readable causal statement."""
        stmt = f"{self.source_name} {self.effect_type.lower()}s {self.target_name}"
        if self.condition:
            stmt += f" (when {self.condition})"
        return stmt
