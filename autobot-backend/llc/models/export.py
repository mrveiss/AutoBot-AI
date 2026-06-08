# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC export artifact model (GH#8245).

Lightweight record of each template / snapshot export produced by
PortabilityService. The exported JSON payload is written to Redis under
``storage_path`` (a ``llc:export:<company_id>:<artifact_id>`` key) with a 7-day TTL.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class LLCExportArtifact(Base):
    """Record of a company template or snapshot export."""

    __tablename__ = "llc_export_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    type: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        server_default="export_artifact",
        comment="export_artifact",
    )
    export_kind: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        comment="template | snapshot",
    )
    schema_version: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="1.0")
    storage_path: Mapped[str] = mapped_column(sa.Text, nullable=False, comment="Redis key holding the JSON payload")
    created_by: Mapped[str] = mapped_column(sa.String(255), nullable=False, server_default="system")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (sa.Index("ix_llc_export_artifacts_company_id", "company_id"),)


__all__ = ["LLCExportArtifact"]
