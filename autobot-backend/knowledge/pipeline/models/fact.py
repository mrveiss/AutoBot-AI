# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Fact Model - Atomic factual statement representation for RAG optimization.

Issue #3395: RAG optimization — semantic chunking, fact extraction, entity resolution.
Phase 2 — Atomic Facts Extraction: Extract atomic factual statements from documents
as discrete retrievable units alongside full chunks.
"""

from datetime import datetime
from typing import List, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from autobot_shared.time_utils import now_utc

FactType = Literal[
    "statement",  # Simple declarative fact (e.g., "X is Y")
    "relationship",  # Relationship fact (e.g., "X enables Y")
    "property",  # Property fact (e.g., "X has property Y")
    "definition",  # Definitional fact (e.g., "X is defined as...")
    "rule",  # Rule or constraint (e.g., "If X then Y")
    "measurement",  # Quantitative fact (e.g., "X has value Y")
]


def _utcnow() -> datetime:
    """Return timezone-aware UTC now (replaces deprecated datetime.utcnow)."""
    return now_utc()


class AtomicFact(BaseModel):
    """
    Represents an atomic factual statement extracted from document processing.

    Atomic facts are indivisible units of factual information that can stand alone
    and be independently retrieved. Each fact connects one or more entities and
    can be represented as a subject-predicate-object triple or similar structure.

    Examples:
    - "AutoBot is an AI-powered automation platform"
    - "ChromaDB is used for knowledge base indexing"
    - "Entity resolution improves retrieval accuracy by 25%"
    """

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat(), UUID: str},
    )

    id: UUID = Field(default_factory=uuid4, description="Unique fact ID")
    subject: str = Field(..., description="Subject entity or concept (e.g., 'AutoBot')")
    predicate: str = Field(..., description="Relationship or property (e.g., 'is', 'enables', 'has'")
    object_: str = Field(..., alias="object", description="Object entity or value (e.g., 'AI platform')")
    fact_type: FactType = Field(
        default="statement",
        description="Type of factual statement",
    )
    description: str = Field(default="", description="Natural language description of the fact")
    context: str = Field(
        default="",
        description="Supporting context from original text (max 500 chars)",
    )
    source_chunk_ids: List[UUID] = Field(default_factory=list, description="Chunks where fact was extracted")
    source_document_id: UUID = Field(..., description="Source document ID")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score")
    supported_by_count: int = Field(
        default=1,
        description="Number of chunks supporting this fact (cross-validation)",
    )
    created_at: datetime = Field(default_factory=_utcnow, description="Fact creation timestamp")
    updated_at: datetime = Field(default_factory=_utcnow, description="Last update timestamp")

    def as_triple(self) -> tuple[str, str, str]:
        """Return fact as (subject, predicate, object) triple for graph representation."""
        return (self.subject, self.predicate, self.object_)
