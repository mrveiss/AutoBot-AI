# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Collaboration Event History Model

Issue #16460 — persisted history for the collaboration activity feed and
secret-share notifications. #16443 delivered both live-only, over
websocket/presence.py's generic broadcast relay; this is the durable copy a
client that wasn't connected at the time (or reconnects later) can read back.

Never stores a secret's value -- only its id/name/type and who shared it.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from autobot_shared.store_authority import system_of_record
from autobot_shared.time_utils import now_utc
from user_management.models.base import Base

# #16460: declares Postgres as the durable, sole home of this concept --
# see autobot_shared/store_authority.py.
SYSTEM_OF_RECORD = system_of_record("collaboration_event_history")


class CollaborationEvent(Base):
    """
    One persisted collaboration event: an activity broadcast, or a
    secret-share notification, for a session.

    Attributes:
        id: Event identifier
        session_id: Session this event belongs to
        kind: 'activity' | 'secret_shared' -- same vocabulary as the live
            broadcast's payload.kind (websocket/presence.py), so a stored row
            and a live message are interchangeable to a client that reads both.
        user_id: Acting user, nullable so an event survives the user's own
            deletion (ON DELETE SET NULL, unlike session_collaborations'
            owner_id CASCADE -- an audit trail should not vanish with its actor)
        username: Denormalized display name at write time (see
            useSessionCollaboration.ts's own "no real user-lookup" gap --
            capturing it here is the same best-effort compromise)
        payload: Kind-specific fields. For 'secret_shared': secret_id,
            secret_name, secret_type, shared_by, shared_by_username -- never
            the secret's value, which nothing here ever reads in the first
            place. For 'activity': the SessionActivity shape (type, content,
            metadata, secretsUsed -- ids only).
        created_at: When the event was recorded (from Base)
    """

    __tablename__ = "collaboration_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    session_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("session_collaborations.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    username: Mapped[str | None] = mapped_column(String(255), nullable=True)

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<CollaborationEvent(id={self.id}, session_id={self.session_id}, kind={self.kind})>"
