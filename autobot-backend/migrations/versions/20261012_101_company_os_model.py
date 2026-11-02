# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company OS model: roles -> workflows -> processes (#18390).

Extends the EXISTING ``workflows`` table (the Automation store) into the workflow
layer -- no second registry -- and adds what hangs off it:

* ``workflows``: ``kind``, ``owner_role_id``, ``trigger_type``, ``trigger_config``.
  Every existing row becomes ``kind = 'workflow'`` with no role and no trigger, which
  is exactly what a pre-Company-OS row is, so no row is rewritten beyond the default.
* ``llc_processes``, ``llc_workflow_nodes``, ``llc_workflow_transitions``,
  ``llc_role_skills``.

Plain ``op.create_table`` / ``op.add_column`` with literal names, which the
baseline-adoption probe ladder reads statically.

Revision ID: 20261012_101
Revises: 20261012_100
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20261012_101"
down_revision: Union[str, None] = "20261012_100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))


def _nullable_uuid(column: str) -> sa.Column:
    return sa.Column(column, UUID(as_uuid=True), nullable=True)


def _wf_fk(column: str, ondelete: str, name: str) -> sa.ForeignKeyConstraint:
    """Composite ``(company_id, column) -> workflows(company_id, id)``: a row can only
    reference a workflow of its own company, enforced by the database."""
    return sa.ForeignKeyConstraint(
        ["company_id", column], ["workflows.company_id", "workflows.id"], ondelete=ondelete, name=name
    )


def _extend_workflows() -> None:
    op.add_column("workflows", sa.Column("kind", sa.String(20), nullable=False, server_default="workflow"))
    op.add_column("workflows", sa.Column("owner_role_id", UUID(as_uuid=True), nullable=True))
    op.add_column("workflows", sa.Column("trigger_type", sa.String(32), nullable=True))
    op.add_column(
        "workflows", sa.Column("trigger_config", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    )
    op.create_index("ix_workflows_owner_role_id", "workflows", ["owner_role_id"])
    op.create_unique_constraint("uq_workflows_company_id_id", "workflows", ["company_id", "id"])
    op.create_check_constraint("ck_workflows_kind", "workflows", "kind IN ('workflow', 'meta_skill')")
    op.create_check_constraint(
        "ck_workflows_meta_skill_unowned",
        "workflows",
        "kind <> 'meta_skill' OR (owner_role_id IS NULL AND trigger_type IS NULL)",
    )


def _create_processes() -> None:
    op.create_table(
        "llc_processes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("process_key", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("owner_role_id", UUID(as_uuid=True), nullable=False),
        sa.Column("required_skills", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        _created_at(),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("company_id", "process_key", name="uq_llc_processes_company_key"),
        sa.UniqueConstraint("company_id", "id", name="uq_llc_processes_company_id_id"),
    )
    op.create_index("ix_llc_processes_company_id", "llc_processes", ["company_id"])
    op.create_index("ix_llc_processes_owner_role_id", "llc_processes", ["owner_role_id"])


def _create_nodes() -> None:
    op.create_table(
        "llc_workflow_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_row_id", UUID(as_uuid=True), nullable=False),
        sa.Column("node_key", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        _nullable_uuid("process_id"),
        _nullable_uuid("meta_skill_row_id"),
        sa.Column("end_outcome", sa.String(16), nullable=True),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        _created_at(),
        sa.UniqueConstraint("workflow_row_id", "node_key", name="uq_llc_workflow_nodes_key"),
        _wf_fk("workflow_row_id", "CASCADE", "fk_llc_workflow_nodes_workflow_row"),
        _wf_fk("meta_skill_row_id", "RESTRICT", "fk_llc_workflow_nodes_meta_skill"),
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
    for column in ("company_id", "workflow_row_id", "process_id", "meta_skill_row_id"):
        op.create_index(f"ix_llc_workflow_nodes_{column}", "llc_workflow_nodes", [column])


def _create_transitions() -> None:
    op.create_table(
        "llc_workflow_transitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_row_id", UUID(as_uuid=True), nullable=False),
        sa.Column("from_node_key", sa.String(64), nullable=False),
        sa.Column("to_node_key", sa.String(64), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("retry_max", sa.Integer, nullable=True),
        sa.Column("condition", sa.Text, nullable=True),
        sa.Column("timeout_seconds", sa.Integer, nullable=True),
        _nullable_uuid("handoff_row_id"),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        _created_at(),
        _wf_fk("workflow_row_id", "CASCADE", "fk_llc_workflow_transitions_workflow_row"),
        _wf_fk("handoff_row_id", "RESTRICT", "fk_llc_workflow_transitions_handoff"),
        sa.CheckConstraint("(kind = 'handoff') = (handoff_row_id IS NOT NULL)", name="ck_llc_transitions_handoff"),
        sa.CheckConstraint("(kind = 'handoff') = (to_node_key IS NULL)", name="ck_llc_transitions_target"),
    )
    for column in ("company_id", "workflow_row_id", "handoff_row_id"):
        op.create_index(f"ix_llc_workflow_transitions_{column}", "llc_workflow_transitions", [column])


def _create_role_skills() -> None:
    op.create_table(
        "llc_role_skills",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", UUID(as_uuid=True), nullable=False),
        sa.Column("skill_name", sa.String(255), nullable=True),
        _nullable_uuid("meta_skill_row_id"),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        _created_at(),
        _wf_fk("meta_skill_row_id", "RESTRICT", "fk_llc_role_skills_meta_skill"),
        sa.UniqueConstraint("role_id", "skill_name", name="uq_llc_role_skills_name"),
        sa.UniqueConstraint("role_id", "meta_skill_row_id", name="uq_llc_role_skills_meta"),
        sa.CheckConstraint("(skill_name IS NULL) <> (meta_skill_row_id IS NULL)", name="ck_llc_role_skills_one_of"),
    )
    for column in ("company_id", "role_id", "meta_skill_row_id"):
        op.create_index(f"ix_llc_role_skills_{column}", "llc_role_skills", [column])


def upgrade() -> None:
    _extend_workflows()
    _create_processes()
    _create_nodes()
    _create_transitions()
    _create_role_skills()


_POPULATED_SQL = (
    "SELECT (SELECT COUNT(*) FROM llc_processes) + (SELECT COUNT(*) FROM llc_workflow_nodes) "
    "+ (SELECT COUNT(*) FROM llc_workflow_transitions) + (SELECT COUNT(*) FROM llc_role_skills) "
    "+ (SELECT COUNT(*) FROM workflows WHERE kind <> 'workflow' OR owner_role_id IS NOT NULL "
    "OR trigger_type IS NOT NULL OR trigger_config <> '{}'::jsonb)"
)


def downgrade() -> None:
    # Everything Company OS wrote is dropped by this downgrade, and a meta skill would
    # survive only as a plain workflow, so refuse once any of it exists (no data loss on
    # update). An empty model downgrades; otherwise export the rows and reverse by hand.
    populated = op.get_bind().execute(sa.text(_POPULATED_SQL)).scalar()
    if populated:
        raise NotImplementedError(
            f"20261012_101 downgrade is refused: {populated} Company OS row(s) exist (processes, workflow "
            "nodes, transitions, role skills, or workflows carrying a kind other than 'workflow', an owner "
            "role or a trigger). Dropping them would discard that data. Export and remove them first."
        )
    for table in ("llc_role_skills", "llc_workflow_transitions", "llc_workflow_nodes", "llc_processes"):
        op.drop_table(table)
    op.drop_constraint("uq_workflows_company_id_id", "workflows", type_="unique")
    op.drop_constraint("ck_workflows_meta_skill_unowned", "workflows", type_="check")
    op.drop_constraint("ck_workflows_kind", "workflows", type_="check")
    op.drop_index("ix_workflows_owner_role_id", table_name="workflows")
    for column in ("trigger_config", "trigger_type", "owner_role_id", "kind"):
        op.drop_column("workflows", column)
