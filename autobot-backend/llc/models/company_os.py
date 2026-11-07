# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Processes, workflow graphs and role skills (#18390).

The workflow layer is the EXISTING ``workflows`` table (``models/workflow.py``),
extended with role ownership, a kind and one trigger. These tables add what hangs
off it; there is no second workflow registry (owner decision 2026-10-12):

* ``llc_processes``            -- a reusable unit of work with one owner role
* ``llc_workflow_nodes``       -- Start / process / meta-skill call / End
* ``llc_workflow_transitions`` -- typed edges, including a cross-role handoff
* ``llc_role_skills``          -- skills and meta skills a role holds

Every table carries ``company_id`` itself, so a query pins tenancy without a join
(same reasoning as ``llc_role_assignments``). Like ``llc_role_workflows`` there is
no foreign key to ``roles``/organisations -- the role/company check lives in the
service -- but the graph tables do reference ``workflows``/``llc_processes`` so a
row can never point at a missing one.
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


def _now_column() -> Mapped[datetime]:
    return mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _wf_fk(columns: list, ondelete: str, tag: str, table: str = "nodes") -> sa.ForeignKeyConstraint:
    """Composite ``(company_id, <col>) -> workflows(company_id, id)``.

    A row can therefore only point at a workflow of its OWN company: the database
    refuses a cross-company reference even if a service check is ever bypassed.
    """
    return sa.ForeignKeyConstraint(
        ["company_id", *columns],
        ["workflows.company_id", "workflows.id"],
        ondelete=ondelete,
        name=f"fk_llc_workflow_{table}_{tag}" if table != "role_skills" else f"fk_llc_role_skills_{tag}",
    )


class LLCProcess(Base):
    """A reusable process: one owner role, optional required skills."""

    __tablename__ = "llc_processes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    process_key: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    owner_role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # Skill names the owner role must hold (directly or through a meta skill).
    required_skills: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = _now_column()
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("company_id", "process_key", name="uq_llc_processes_company_key"),
        # Target of the composite (company_id, process_id) foreign key on nodes.
        sa.UniqueConstraint("company_id", "id", name="uq_llc_processes_company_id_id"),
    )


class LLCWorkflowNode(Base):
    """One node of a workflow graph. ``node_key`` is unique within the workflow."""

    __tablename__ = "llc_workflow_nodes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    workflow_row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    node_key: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    kind: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    label: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    process_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    meta_skill_row_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    end_outcome: Mapped[str | None] = mapped_column(sa.String(16), nullable=True)
    # Authoring order, so a graph reads back as it was written.
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = _now_column()

    __table_args__ = (
        sa.UniqueConstraint("workflow_row_id", "node_key", name="uq_llc_workflow_nodes_key"),
        _wf_fk(["workflow_row_id"], "CASCADE", "workflow_row"),
        _wf_fk(["meta_skill_row_id"], "RESTRICT", "meta_skill"),
        sa.ForeignKeyConstraint(
            ["company_id", "process_id"],
            ["llc_processes.company_id", "llc_processes.id"],
            ondelete="RESTRICT",
            name="fk_llc_workflow_nodes_process",
        ),
        sa.CheckConstraint("(kind = 'process') = (process_id IS NOT NULL)", name="ck_llc_workflow_nodes_process"),
        sa.CheckConstraint(
            "(kind = 'meta_skill') = (meta_skill_row_id IS NOT NULL)", name="ck_llc_workflow_nodes_meta_skill"
        ),
        sa.CheckConstraint("(kind = 'end') = (end_outcome IS NOT NULL)", name="ck_llc_workflow_nodes_end"),
    )


class LLCWorkflowTransition(Base):
    """A typed edge. A handoff has no ``to_node_key``: it targets another workflow."""

    __tablename__ = "llc_workflow_transitions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    workflow_row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    from_node_key: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    to_node_key: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    kind: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    retry_max: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    condition: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    timeout_seconds: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    handoff_row_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = _now_column()

    __table_args__ = (
        _wf_fk(["workflow_row_id"], "CASCADE", "workflow_row", table="transitions"),
        _wf_fk(["handoff_row_id"], "RESTRICT", "handoff", table="transitions"),
        sa.CheckConstraint("(kind = 'handoff') = (handoff_row_id IS NOT NULL)", name="ck_llc_transitions_handoff"),
        sa.CheckConstraint("(kind = 'handoff') = (to_node_key IS NULL)", name="ck_llc_transitions_target"),
    )


class LLCRoleSkill(Base):
    """A skill, or a meta skill, held by a role (not by whoever holds the role)."""

    __tablename__ = "llc_role_skills"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    skill_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    meta_skill_row_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = _now_column()

    __table_args__ = (
        _wf_fk(["meta_skill_row_id"], "RESTRICT", "meta_skill", table="role_skills"),
        sa.UniqueConstraint("role_id", "skill_name", name="uq_llc_role_skills_name"),
        sa.UniqueConstraint("role_id", "meta_skill_row_id", name="uq_llc_role_skills_meta"),
        sa.CheckConstraint("(skill_name IS NULL) <> (meta_skill_row_id IS NULL)", name="ck_llc_role_skills_one_of"),
    )
