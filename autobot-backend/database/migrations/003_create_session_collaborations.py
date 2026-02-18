# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration 003: Create Session Collaborations Table

Creates table for multi-user session collaboration with permissions.
Part of Issue #872 - Session Collaboration API (#608 Phase 3).
"""

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func


def upgrade(engine):
    """Create session_collaborations table."""
    from sqlalchemy import MetaData, Table

    metadata = MetaData()

    session_collaborations = Table(
        "session_collaborations",
        metadata,
        Column(
            "session_id",
            String(128),
            primary_key=True,
            nullable=False,
            index=True,
            comment="Chat session identifier",
        ),
        Column(
            "owner_id",
            UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            comment="User ID who owns the session",
        ),
        Column(
            "collaborators",
            JSONB,
            nullable=False,
            server_default="{}",
            comment="Map of user_id to permission_level",
        ),
        Column(
            "invitations",
            JSONB,
            nullable=False,
            server_default="[]",
            comment="Pending collaboration invitations",
        ),
        Column(
            "metadata",
            JSONB,
            nullable=False,
            server_default="{}",
            comment="Additional collaboration metadata",
        ),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )

    # Create table
    session_collaborations.create(engine)


def downgrade(engine):
    """Drop session_collaborations table."""
    from sqlalchemy import MetaData, Table

    metadata = MetaData()

    session_collaborations = Table(
        "session_collaborations",
        metadata,
        autoload_with=engine,
    )

    session_collaborations.drop(engine)
