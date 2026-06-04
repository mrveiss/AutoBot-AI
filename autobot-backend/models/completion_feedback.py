# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Completion Feedback Model (Issue #905)

Tracks user feedback on code completion suggestions.
"""

from datetime import datetime
from typing import Dict

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class CompletionFeedback(Base):
    """
    User feedback on code completion suggestions.

    Tracks which suggestions were accepted or rejected for learning loop.
    """

    __tablename__ = "completion_feedback"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # User context
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Completion context
    context: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Feedback
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Pattern reference
    pattern_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Additional metadata
    confidence_score: Mapped[str | None] = mapped_column(String(10), nullable=True)
    completion_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def to_dict(self) -> Dict:
        """Convert feedback to dictionary for API responses."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "user_id": self.user_id,
            "context": (self.context[:100] + "..." if len(self.context) > 100 else self.context),
            "suggestion": self.suggestion,
            "language": self.language,
            "file_path": self.file_path,
            "action": self.action,
            "pattern_id": self.pattern_id,
            "confidence_score": self.confidence_score,
            "completion_rank": self.completion_rank,
        }

    @property
    def was_accepted(self) -> bool:
        """Check if suggestion was accepted."""
        return self.action == "accepted"

    def __repr__(self) -> str:
        return f"<CompletionFeedback(id={self.id}, action={self.action}, " f"pattern_id={self.pattern_id})>"
