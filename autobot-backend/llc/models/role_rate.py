# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What an hour of a role costs, so a step's cost can be derived (#14607).

The rate sits on the **role**, not on the person holding it, for the same
reason the workflows and tools do (#14221):

    people get promoted or leave the company, but the role stays — and so do
    the tools and workflows attached to the role

A rate attached to a person would have to be re-entered every time the holder
changed, and every historical figure would move with them.

Why a separate table rather than a column on ``roles``: that row is the
canonical RBAC role, shared by every consumer of ``user_management``. An hourly
rate is an organisational fact, not an authorisation one, and putting money on
the permission model would push a Company OS concern into everybody else's
security schema. ``llc_role_assignments``, ``llc_role_workflows``,
``llc_role_tools`` and ``llc_role_credentials`` all extend the canonical role
from the LLC side in exactly this way; this follows them rather than inventing
a fifth shape.

Currency is stored explicitly. The product this was researched against supports
one currency and says so; storing the amount without the unit would repeat that
limitation *silently*, which is worse — a number with no unit reads as whatever
the reader assumes.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base

#: ISO 4217 is three characters. Stored as given; no conversion happens here,
#: because a converted amount would need a rate and a date to be meaningful.
CURRENCY_CODE_LENGTH = 3


class LLCRoleRate(Base):
    """The hourly cost of one role, in one company."""

    __tablename__ = "llc_role_rates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Carried on the row so every query pins scope without depending on a join
    # to the role — a lost join condition cannot widen the result. Same
    # reasoning as llc_role_workflows and llc_role_assignments.
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Numeric, not Float: money compared or summed as binary floating point
    # drifts, and this feeds a cost total people are meant to trust.
    hourly_rate: Mapped[float] = mapped_column(sa.Numeric(15, 6), nullable=False)
    currency: Mapped[str] = mapped_column(sa.String(CURRENCY_CODE_LENGTH), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    __table_args__ = (
        # One rate per role. A second row would make "the rate" ambiguous, and
        # every derived cost would depend on which one a query happened to read.
        sa.UniqueConstraint("role_id", name="uq_llc_role_rates_role"),
    )
