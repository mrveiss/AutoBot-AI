# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Durable participant set of a shared chat (#18890).

One row per (chat, participant). The Redis sets ``session:shared_with:*`` and
``user:shared_sessions:*`` are projections of these rows (see
``security/session_shares.py``). ``user_id`` is the same string the share
endpoint is given, so no foreign key: a participant may be a username.
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
