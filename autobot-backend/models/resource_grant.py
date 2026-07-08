# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Generic per-grantee access grant for shareable resources (#11277).

One row grants a user or group a permission on a skill or agent. Sharing = add
a row; revoking = delete a row. Authorization only — no crypto envelope.
"""

import uuid

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from user_management.models.base import Base


class ResourceGrant(Base):
    """One grant: (resource_type, resource_id) accessible to (grantee_type, grantee_id)."""

    __tablename__ = "resource_grants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # skill|agent
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    grantee_type: Mapped[str] = mapped_column(String(16), nullable=False)  # user|group
    grantee_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(16), nullable=False, default="use")  # view|use|manage
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "resource_type",
            "resource_id",
            "grantee_type",
            "grantee_id",
            name="uq_resource_grants_target",
        ),
    )
