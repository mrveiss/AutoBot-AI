# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A Workflow Planner plan revision (#19934).

One row is one revision of one plan: the whole ``CompanyWorkflowPlan`` document in
``document`` (JSONB) and ``status`` as a real column, so a plan list filters in SQL (owner
decision D2). ``company_id`` is on the row itself, like every Company OS table, so a query
pins tenancy without a join.

Uniqueness is ``(company_id, plan_key, revision)``. At most ONE revision per plan is open
(not ``converted``) at a time (D14); the partial unique index below is declared here as well
as in the migration so every ``create_all`` test database carries it.
"""

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from autobot_shared.store_authority import system_of_record
from user_management.models.base import Base

# Postgres is the system of record; see autobot_shared/store_authority.py.
SYSTEM_OF_RECORD = system_of_record("company_os_model")

_OPEN = sa.text("status <> 'converted'")


class CompanyOsWorkflowPlan(Base):
    __tablename__ = "company_os_workflow_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    plan_key: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    revision: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1, server_default="1")
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="draft", server_default="draft")
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("company_id", "plan_key", "revision", name="uq_company_os_workflow_plans_revision"),
        sa.Index("ix_company_os_workflow_plans_status", "company_id", "status"),
        sa.Index(
            "uq_company_os_workflow_plans_one_open",
            "company_id",
            "plan_key",
            unique=True,
            postgresql_where=_OPEN,
            sqlite_where=_OPEN,
        ),
    )
