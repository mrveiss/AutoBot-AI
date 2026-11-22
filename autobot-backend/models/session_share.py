# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Durable participant set of a shared chat (#18890).

One row per (chat, participant); the only store of who a chat is shared with and the source of every access
decision (``security/session_shares.py``). The legacy Redis sets ``session:shared_with:*`` and
``user:shared_sessions:*`` are adoption input only. ``user_id`` is the same string the share endpoint is given,
so no foreign key: a participant may be a username.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from autobot_shared.store_authority import system_of_record
from user_management.models.base import Base

SYSTEM_OF_RECORD = system_of_record("session_shares")


class SessionShare(Base):
    """A chat shared with one participant, until the owner unshares it."""

    __tablename__ = "chat_session_shares"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    shared_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SessionShareAdoption(Base):
    """One-shot completion record of the Redis-to-table share adoption (#18890).

    A row means every pre-table Redis share was copied in and adoption never runs again, even if the Redis
    marker is lost and legacy ``session:shared_with:*`` keys come back. Lives in the system of record next to
    the shares it guards.
    """

    __tablename__ = "chat_session_share_adoption"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
