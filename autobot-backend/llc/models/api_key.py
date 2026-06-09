# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC agent API key ORM model (GH#8218)."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class LLCApiKey(Base):
    """Per-agent bearer key record.

    key_hash stores SHA-256 hex of the plaintext token for O(1) DB lookup.
    Raw token is shown once at creation time and never stored.
    """

    __tablename__ = "llc_agent_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    company_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    # GH#9623: optional TTL backstop for ephemeral run-scoped keys. NULL = never
    # expires (default for long-lived keys); a value self-expires the key even if
    # explicit revocation never runs (e.g. scheduler crash mid-run).
    expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)


__all__ = ["LLCApiKey"]
