# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ML Model Registry (Issue #904)

Tracks trained code completion models and their metadata.
"""

from datetime import datetime
from typing import Dict

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class MLModel(Base):
    """
    Trained ML model registry.

    Tracks versions, metrics, and deployment status of code completion models.
    """

    __tablename__ = "ml_models"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Model identification
    version = Column(String(50), unique=True, nullable=False, index=True)
    model_type = Column(String(50), nullable=False)  # e.g., "lstm_completion"
    language = Column(String(20))  # Filter used during training
    pattern_type = Column(String(50))  # Filter used during training

    # Model metadata
    file_path = Column(String(500), nullable=False)  # Path to .pt file
    config = Column(JSONB)  # Model architecture config

    # Training metrics
    val_loss = Column(Float)
    accuracy = Column(Float)
    mrr = Column(Float)  # Mean Reciprocal Rank
    hit_at_1 = Column(Float)
    hit_at_5 = Column(Float)
    hit_at_10 = Column(Float)

    # Training info
    epochs_trained = Column(Integer)
    training_duration_seconds = Column(Integer)
    num_parameters = Column(Integer)

    # Deployment status
    is_active = Column(Boolean, default=False, index=True)  # Currently serving
    deployed_at = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Notes
    notes = Column(Text)

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
        return (
            f"<MLModel(version={self.version}, type={self.model_type}, "
            f"active={self.is_active})>"
        )
