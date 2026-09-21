# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC board approval gate model (GH#8214).

FROZEN, READ-ONLY as of #17043: the service layer no longer creates rows
here -- it reads and writes ``models.approval.Approval`` directly (the
unified platform table). ``llc_approvals`` stays mapped only so the table
itself, and any pre-#17043 row, is never an unowned orphan; the 094
migration copied every row it held onto ``approvals``, keyed by the same
id. Do not add a new insert/update against this class: ``type``/``status``
bind to the merged ``ApprovalType``/``ApprovalStatus`` (a superset of the
narrower Postgres-native ``approvaltype``/``approvalstatus`` enum types
this table's own columns were created with), so a value outside the
original 6 LLC members would fail at the database, not at the ORM.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base

from .enums import ApprovalStatus, ApprovalType, pg_enum_values


class LLCApproval(Base):
    """Board approval gate record — one row per approval request.

    Frozen for reads only since #17043 -- see the module docstring. Never
    insert or update through this class.
    """

    __tablename__ = "llc_approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    type: Mapped[str] = mapped_column(
        sa.Enum(ApprovalType, name="approvaltype", create_type=False, values_callable=pg_enum_values),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(ApprovalStatus, name="approvalstatus", create_type=False, values_callable=pg_enum_values),
        nullable=False,
        server_default=ApprovalStatus.PENDING.value,
        index=True,
    )

    requested_by_agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )

    # From 2026-09-18 (#17042): the verified human caller's user id. Earlier rows
    # hold whatever the client sent, or the board sentinel, and are not rewritten.
    decided_by_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<LLCApproval(id={self.id}, type={self.type}, status={self.status})>"


__all__ = ["LLCApproval"]
