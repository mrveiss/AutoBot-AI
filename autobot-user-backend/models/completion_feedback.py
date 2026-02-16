# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Completion Feedback Model (Issue #905)

Tracks user feedback on code completion suggestions.
"""

from datetime import datetime
from typing import Dict

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class CompletionFeedback(Base):
    """
    User feedback on code completion suggestions.

    Tracks which suggestions were accepted or rejected for learning loop.
    """

    __tablename__ = "completion_feedback"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Timestamp
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # User context
    user_id = Column(String(100), index=True)  # Optional: for personalization

    # Completion context
    context = Column(Text, nullable=False)  # Code context before completion
    suggestion = Column(Text, nullable=False)  # Suggested completion
    language = Column(String(20))  # Programming language
    file_path = Column(String(500))  # File where completion occurred

    # Feedback
    action = Column(String(20), nullable=False, index=True)  # 'accepted' or 'rejected'

    # Pattern reference
    pattern_id = Column(Integer, index=True)  # Link to CodePattern if applicable

    # Additional metadata
    confidence_score = Column(String(10))  # Model confidence at suggestion time
    completion_rank = Column(Integer)  # Position in top-k suggestions (1-indexed)

    def to_dict(self) -> Dict:
        """Convert feedback to dictionary for API responses."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "user_id": self.user_id,
            "context": self.context[:100] + "..."
            if len(self.context) > 100
            else self.context,
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
        return (
            f"<CompletionFeedback(id={self.id}, action={self.action}, "
            f"pattern_id={self.pattern_id})>"
        )
