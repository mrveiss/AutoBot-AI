# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Workflow model — a durable, company-scoped identity for a workflow (#14210).

Sibling of ``models/workflow_permission.py`` (permissions *for* a workflow)
and ``models/workflow_audit.py`` (an audit trail *of* a workflow) — those two
existed with no ``workflows`` table behind them (#13939/#13963 audit).
Workflows themselves lived only in Redis (``api/workflow_state.py``,
crash-recoverable but with no relational identity and no company attribution)
or, for the legacy chat-triggered path, in a plain in-memory dict
(``api/workflow.py``'s ``active_workflows`` — erased on every process
restart). Neither carried a ``company_id``: a workflow did not know which
company it belonged to.

This is the FOUNDATION only (per owner direction on #14210): a real table
with a company-scoped identity that a future process node (#13963) can
reference and expect to still resolve tomorrow. It does not build process
nodes, canvas UI, or reconcile the Redis/in-memory stores onto this table —
that is the explicitly deferred "step 2" in #14210's proposed order.

``company_id`` is nullable at the schema level to hold legacy rows backfilled
from Redis by ``services/workflow_redis_backfill.py`` — those pre-existing
workflows carry no company attribution in their source data and cannot be
guessed at (see that module's docstring). Every NEW workflow created through
``llc.services.workflow.WorkflowService.create`` is required (at the service/
route layer, not the DB) to supply a ``company_id`` — a future process node
must only ever reference a company-attributed row.

No FK to an ``organizations`` table — mirrors ``LLCContact`` /
``LLCCompanyMembership`` / ``LLCSecret`` (see ``llc/models/contact.py``
docstring): companies inside one AutoBot installation are organisational
units of a single installation, not a foreign-keyed tenant boundary.
"""

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.types import Uuid

from user_management.models.base import Base

# Provenance of a row — lets a reconciliation pass (and any report run
# against this table) tell a workflow created through the new company-scoped
# API apart from one recovered from a pre-existing, unattributed store.
SOURCE_CREATED = "created"
SOURCE_LEGACY_REDIS = "legacy_redis_unattributed"


class Workflow(Base):
    """A workflow's durable, (optionally company-scoped) identity.

    ``workflow_id`` is the primary key and a plain string — matching the id
    shape every existing producer already uses (``str(uuid.uuid4())`` in
    ``api/workflow.py``'s ``_execute_complex_workflow``, and the same in
    ``api/workflow_state.py``'s ``WorkflowStateMachine``) so a backfilled row
    keeps its original identity rather than being reminted under a new one.

    ``definition`` holds the workflow's descriptive payload (goal/steps/
    classification/etc.) as an opaque JSON blob — this table's job is to give
    a workflow a durable, queryable, company-scoped identity, not to
    normalize every field of every workflow shape the platform has produced
    over time (Redis ``WorkflowState``, the legacy in-memory dict, and future
    company-scoped creates all differ slightly).
    """

    __tablename__ = "workflows"

    workflow_id = Column(String(255), primary_key=True)
    company_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    name = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="planned")
    # created | legacy_redis_unattributed — see module constants above.
    source = Column(String(50), nullable=False, default=SOURCE_CREATED)
    definition = Column(JSONB, nullable=False, default=dict)
    created_by = Column(Uuid(as_uuid=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Workflow id={self.workflow_id} company={self.company_id} status={self.status}>"


__all__ = ["Workflow", "SOURCE_CREATED", "SOURCE_LEGACY_REDIS"]
