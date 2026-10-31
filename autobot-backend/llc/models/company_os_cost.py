# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One row per LLM call an agent reported, tied to the work item that incurred it (#16016).

``llc_agent_budgets`` is an aggregate -- one running total per agent -- so it cannot say
which work item a cost belongs to; a work-item id stored on a running total would only
name the last writer. This table is the per-event record. ``work_item_id`` is nullable
because not every caller of ``BudgetService.ingest_cost_event`` knows the item (a
scheduler-dispatched run reports usage after the fact); a row without one is an
unattributed cost, not a malformed one. The foreign key is ``SET NULL`` so deleting a
work item keeps the spend that was incurred.
"""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from autobot_shared.store_authority import system_of_record
from user_management.models.base import Base

# Postgres is the system of record; see autobot_shared/store_authority.py.
SYSTEM_OF_RECORD = system_of_record("company_os_model")


class CompanyOsCostEvent(Base):
    __tablename__ = "company_os_cost_events"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("llc_work_items.id", ondelete="SET NULL", name="fk_company_os_cost_events_work_item"),
        nullable=True,
        index=True,
    )
    model: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    tokens_in: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    tokens_out: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    cost: Mapped[Decimal] = mapped_column(sa.Numeric(15, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
