# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Org Node Model (#1405)

SQLAlchemy model for agent organizational hierarchy.
Table: agent_org_nodes
"""

import uuid
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.types import Uuid

from user_management.models.base import Base


class OrgRole(str, Enum):
    """Valid org roles for agents (#1405)."""

    MANAGER = "manager"
    COORDINATOR = "coordinator"
    SPECIALIST = "specialist"
    WORKER = "worker"


class AgentOrgNode(Base):
    """
    Organizational hierarchy node for an agent (#1405).

    agent_id is a String FK to the logical agent registry (no SQL agents table).
    reports_to is a self-referencing String pointing to another agent_id.

    DUAL-KEYSPACE CONVENTION (#10032) — two columns identify an agent; using the
    wrong one in a join compiles fine and silently returns 0 rows in Postgres
    (and is masked in SQLite tests that seed ``agent_id = str(uuid4())``):

    * ``id``       — UUID PK. FK target for *work-item* assignment:
                     ``llc_work_items.assignee_agent_id`` (and routines) hold THIS.
                     Join: ``AgentOrgNode.id == LLCWorkItem.assignee_agent_id``.
    * ``agent_id`` — String(255) logical slug (hire flow mints e.g.
                     ``assistant-...-<hex8>``). The keyspace for everything keyed
                     by the *logical* agent: ``llc_agent_budgets.agent_id``,
                     ``llc_heartbeat_runs.agent_id``, ``llc_api_keys.agent_id``,
                     scheduler dispatch, and controls pause/resume.

    Crossing the two requires an explicit resolve: load the node by ``id`` from a
    work-item assignee, then use its ``agent_id`` slug for any heartbeat/budget/
    controls lookup (see comment_wake_service / controls_service).
    """

    __tablename__ = "agent_org_nodes"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    reports_to = Column(String(255), nullable=True, index=True)
    org_role = Column(String(50), nullable=False, default=OrgRole.WORKER.value, index=True)
    title = Column(String(255), nullable=True)
    capabilities = Column(Text, nullable=True)
    company_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Heartbeat scheduler fields — migration 20260523_036 (GH#8225, #9899)
    heartbeat_cron = Column(Text, nullable=True)
    heartbeat_enabled = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    adapter_type = Column(Text, nullable=True)
    adapter_config = Column(JSONB, nullable=True)
    context_mode = Column(String(16), nullable=False, default="thin", server_default=text("'thin'"))

    # Pause/resume state — migration 20260525_039 (GH#8256, #9899)
    pre_pause_status = Column(String(32), nullable=True)

    # Model tier + instructions — migration 20260525_042 (GH#8486, #9899)
    model = Column(String(255), nullable=True)
    instructions_file_path = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<AgentOrgNode agent={self.agent_id!r} role={self.org_role!r} " f"reports_to={self.reports_to!r}>"
