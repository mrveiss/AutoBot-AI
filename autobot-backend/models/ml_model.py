# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ML Model Registry (Issue #904)

Tracks trained code completion models and their metadata.
"""

from datetime import datetime
from typing import Dict

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class MLModel(Base):
    """
    Trained ML model registry.

    Tracks versions, metrics, and deployment status of code completion models.
    """

    __tablename__ = "ml_models"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Model identification
    version: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pattern_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Model metadata
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Training metrics
    val_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    mrr: Mapped[float | None] = mapped_column(Float, nullable=True)
    hit_at_1: Mapped[float | None] = mapped_column(Float, nullable=True)
    hit_at_5: Mapped[float | None] = mapped_column(Float, nullable=True)
    hit_at_10: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Training info
    epochs_trained: Mapped[int | None] = mapped_column(Integer, nullable=True)
    training_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_parameters: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Deployment status
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_dict(self) -> Dict:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "version": self.version,
            "model_type": self.model_type,
            "language": self.language,
            "pattern_type": self.pattern_type,
            "file_path": self.file_path,
            "config": self.config,
            "metrics": {
                "val_loss": self.val_loss,
                "accuracy": self.accuracy,
                "mrr": self.mrr,
                "hit@1": self.hit_at_1,
                "hit@5": self.hit_at_5,
                "hit@10": self.hit_at_10,
            },
            "training_info": {
                "epochs_trained": self.epochs_trained,
                "training_duration_seconds": self.training_duration_seconds,
                "num_parameters": self.num_parameters,
            },
            "is_active": self.is_active,
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "notes": self.notes,
        }

    def __repr__(self) -> str:
        return f"<MLModel(version={self.version}, type={self.model_type}, " f"active={self.is_active})>"
