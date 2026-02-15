# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Activity Database Models

Issue #871 - Activity Entity Types (#608 Phase 4)

SQLAlchemy models for persisting activity entities with user attribution:
- TerminalActivityModel: Command execution tracking
- FileActivityModel: File operation tracking
- BrowserActivityModel: Web automation tracking
- DesktopActivityModel: GUI automation tracking
- SecretUsageModel: Secret access audit trail

All models include foreign key relationships to User entities.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Tuple
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from user_management.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from user_management.models.user import User


class TerminalActivityModel(Base, TimestampMixin):
    """
    Terminal command execution activity.

    Tracks shell commands with user attribution and secret usage.
    Enables knowledge extraction from command outputs and security auditing.
    """

    __tablename__ = "terminal_activities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # User attribution (REQUIRED)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Session context (optional - may be executed outside chat)
    session_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    # Command details
    command: Mapped[str] = mapped_column(Text, nullable=False)

    working_directory: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
    )

    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Secret usage tracking
    secrets_used: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        default=list,
    )

    # Additional metadata (shell type, env vars, duration, etc.)
    metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="terminal_activities")

    def __repr__(self) -> str:
        return (
            f"<TerminalActivity(id={self.id}, user_id={self.user_id}, "
            f"command={self.command[:50]}...)>"
        )


class FileActivityModel(Base, TimestampMixin):
    """
    File system operation activity.

    Tracks file CRUD operations with user attribution.
    Enables access control auditing and security monitoring.
    """

    __tablename__ = "file_activities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # User attribution (REQUIRED)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Session context
    session_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    # Operation details
    operation: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    path: Mapped[str] = mapped_column(String(2048), nullable=False)

    new_path: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
    )

    file_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Additional metadata (permissions, owner, hash, etc.)
    metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="file_activities")

    def __repr__(self) -> str:
        return (
            f"<FileActivity(id={self.id}, user_id={self.user_id}, "
            f"operation={self.operation}, path={self.path})>"
        )


class BrowserActivityModel(Base, TimestampMixin):
    """
    Browser automation activity.

    Tracks web navigation and form interactions with secret usage.
    Enables security auditing and workflow analysis.
    """

    __tablename__ = "browser_activities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # User attribution (REQUIRED)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Session context
    session_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    # Browser action details
    url: Mapped[str] = mapped_column(String(2048), nullable=False)

    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    selector: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )

    input_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Secret usage tracking
    secrets_used: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        default=list,
    )

    # Additional metadata (status code, cookies, headers, etc.)
    metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="browser_activities")

    def __repr__(self) -> str:
        return (
            f"<BrowserActivity(id={self.id}, user_id={self.user_id}, "
            f"action={self.action}, url={self.url[:50]}...)>"
        )


class DesktopActivityModel(Base, TimestampMixin):
    """
    Desktop automation activity.

    Tracks GUI automation actions (mouse, keyboard, windows).
    Enables workflow recording and security monitoring.
    """

    __tablename__ = "desktop_activities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # User attribution (REQUIRED)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Session context
    session_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    # Action details
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    coordinates: Mapped[Optional[tuple[int, int]]] = mapped_column(
        Tuple,
        nullable=True,
    )

    window_title: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )

    input_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    screenshot_path: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
    )

    # Additional metadata (app name, OCR results, etc.)
    metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="desktop_activities")

    def __repr__(self) -> str:
        return (
            f"<DesktopActivity(id={self.id}, user_id={self.user_id}, "
            f"action={self.action})>"
        )


class SecretUsageModel(Base, TimestampMixin):
    """
    Secret access audit trail.

    Comprehensive audit log for secret usage across all activity types.
    Enables security compliance, anomaly detection, and access analysis.
    """

    __tablename__ = "secret_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Secret and user (REQUIRED)
    secret_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Activity context
    activity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    session_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    # Access control
    access_granted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    denial_reason: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )

    # Additional metadata (IP, user agent, location, etc.)
    metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="secret_usage")

    def __repr__(self) -> str:
        return (
            f"<SecretUsage(id={self.id}, secret_id={self.secret_id}, "
            f"user_id={self.user_id}, activity_type={self.activity_type})>"
        )
