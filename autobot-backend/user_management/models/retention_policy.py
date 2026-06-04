# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Retention Policy Model (MVA-3145, GH#8995)

Stores configurable data retention policies for chat, files, audit logs, and knowledge base.
Supports both global policies and user-specific overrides.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from user_management.models.base import Base


class RetentionPolicy(Base):
    """
    Data retention policy configuration.

    Supports global policies (user_id=NULL) and user-specific overrides.
    Policy resolution: user-specific overrides global defaults.
    """

    __tablename__ = "retention_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Policy type: chat, file, audit, kb
    policy_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Retention period in days
    retention_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # User-specific override (NULL = global policy)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Anonymization flag (GDPR compliance)
    anonymize_instead_of_delete: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Unique constraint: one policy per (policy_type, user_id)
    __table_args__ = (
        UniqueConstraint("policy_type", "user_id", name="uq_policy_type_user"),
        Index("idx_policy_type_user", "policy_type", "user_id"),
    )
