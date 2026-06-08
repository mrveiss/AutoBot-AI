# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Org Node Model (#1405)

SQLAlchemy model for agent organizational hierarchy.
Table: agent_org_nodes
"""

import uuid
from enum import Enum

from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import UUID
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

    def __repr__(self) -> str:
        return f"<AgentOrgNode agent={self.agent_id!r} role={self.org_role!r} " f"reports_to={self.reports_to!r}>"
