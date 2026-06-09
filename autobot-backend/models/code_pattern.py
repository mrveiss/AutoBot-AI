# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Code Pattern Model (Issue #903)

Stores extracted code patterns for ML training and completion suggestions.
"""

from datetime import datetime
from typing import Dict

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class CodePattern(Base):
    """
    Extracted code pattern for completion suggestions.

    Stores function signatures, implementations, and usage patterns
    from the AutoBot codebase for ML training and pattern-based completion.
    """

    __tablename__ = "code_patterns"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Pattern identification
    pattern_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # function, error_handling, api_usage, etc.
    language: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Pattern content
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Pattern metadata
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frequency: Mapped[int] = mapped_column(Integer, default=1, index=True)

    # Usage statistics (for learning loop - Issue #905)
    times_suggested: Mapped[int] = mapped_column(Integer, default=0)
    times_accepted: Mapped[int] = mapped_column(Integer, default=0)
    acceptance_rate: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )

    # Indexes for fast lookup
    __table_args__ = (
        Index("ix_pattern_lookup", "pattern_type", "language", "category"),
        Index("ix_pattern_frequency", "frequency", "acceptance_rate"),
        Index("ix_pattern_language_type", "language", "pattern_type"),
    )

    def to_dict(self) -> Dict:
        """Convert pattern to dictionary for API responses."""
        return {
            "id": self.id,
            "pattern_type": self.pattern_type,
            "language": self.language,
            "category": self.category,
            "signature": self.signature,
            "body": self.body,
            "context": self.context,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "frequency": self.frequency,
            "times_suggested": self.times_suggested,
            "times_accepted": self.times_accepted,
            "acceptance_rate": self.acceptance_rate,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }

    @classmethod
    def get_redis_key(cls, pattern_type: str, language: str, category: str | None = None) -> str:
        """Generate Redis key for caching hot patterns."""
        if category:
            return f"patterns:{language}:{pattern_type}:{category}"
        return f"patterns:{language}:{pattern_type}"

    def __repr__(self) -> str:
        return f"<CodePattern(id={self.id}, type={self.pattern_type}, " f"lang={self.language}, freq={self.frequency})>"
