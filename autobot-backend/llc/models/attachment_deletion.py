# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Deletion outbox for attachment files (#19756).

One row per attachment file whose database row a caller has deleted. It is written in the
same transaction as that delete, so the two cannot disagree, and it is removed only when the
file is gone. Nothing else writes here: a file with no deleted row is never listed.
"""

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class LLCAttachmentFileDeletion(Base):
    """A file removal owed because its attachment row was deleted."""

    __tablename__ = "llc_attachment_file_deletions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    #: The deleted attachment's id. Not a foreign key: the row it names is gone by design.
    attachment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    storage_path: Mapped[str] = mapped_column(sa.Text, nullable=False)
    attempts: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    last_error: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)
