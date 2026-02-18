# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Pattern Model (Issue #903)

Stores extracted code patterns for ML training and completion suggestions.
"""

from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class CodePattern(Base):
    """
    Extracted code pattern for completion suggestions.

    Stores function signatures, implementations, and usage patterns
    from the AutoBot codebase for ML training and pattern-based completion.
    """

    __tablename__ = "code_patterns"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Pattern identification
    pattern_type = Column(
        String(50), nullable=False, index=True
    )  # function, error_handling, api_usage, etc.
    language = Column(String(20), nullable=False, index=True)  # python, typescript, vue
    category = Column(String(50), index=True)  # fastapi, redis, vue_composable, etc.

    # Pattern content
    signature = Column(Text, nullable=False)  # Function signature or pattern template
    body = Column(Text)  # Function body or implementation
    context = Column(
        JSONB
    )  # Additional context: imports, decorators, parent class, etc.

    # Pattern metadata
    file_path = Column(String(500))  # Source file where pattern was found
    line_number = Column(Integer)  # Line number in source file
    frequency = Column(Integer, default=1, index=True)  # How many times pattern appears

    # Usage statistics (for learning loop - Issue #905)
    times_suggested = Column(Integer, default=0)
    times_accepted = Column(Integer, default=0)
    acceptance_rate = Column(Float, default=0.0, index=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    last_seen = Column(
        DateTime, default=datetime.utcnow
    )  # Last time pattern was found in codebase

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
    def get_redis_key(
        cls, pattern_type: str, language: str, category: Optional[str] = None
    ) -> str:
        """Generate Redis key for caching hot patterns."""
        if category:
            return f"patterns:{language}:{pattern_type}:{category}"
        return f"patterns:{language}:{pattern_type}"

    def __repr__(self) -> str:
        return (
            f"<CodePattern(id={self.id}, type={self.pattern_type}, "
            f"lang={self.language}, freq={self.frequency})>"
        )
