# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Slash Command Preset Models (GH#8595)

SQLAlchemy model for slash command presets with org and user scoping.
Table: slash_command_presets
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text, UniqueConstraint
from sqlalchemy.types import Uuid

from user_management.models.base import Base


class SlashCommandPreset(Base):
    """A reusable slash command preset with org/user scoping (GH#8595)."""

    __tablename__ = "slash_command_presets"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    user_id = Column(String(255), nullable=True, index=True)
    command = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    prompt_template = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("org_id", "user_id", "command", name="uq_scope_command"),)

    def __repr__(self) -> str:
        return f"<SlashCommandPreset id={self.id} command={self.command!r} user_id={self.user_id!r} org_id={self.org_id!r}>"
