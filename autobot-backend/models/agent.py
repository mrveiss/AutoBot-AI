# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Registry Model (#1754)

Central SQL agents table — single source of truth for which agents exist.
Other agent-related tables (agent_org_nodes, agent_runtime_state,
heartbeat_runs) reference agent_id strings that should correspond to
rows in this table.
"""

import uuid
from enum import Enum

from sqlalchemy import Column, String, Text
from sqlalchemy.types import Uuid

from user_management.models.base import Base, TimestampMixin


class AgentStatus(str, Enum):
    """Lifecycle states for an agent (#1754)."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class Agent(Base, TimestampMixin):
    """
    Central agent registry row (#1754).

    Every logical agent in the system should have a row here.
    agent_id is the canonical string identifier used across all
    agent-related tables and config files.
    """

    __tablename__ = "agents"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    agent_type = Column(String(50), nullable=False, default="worker")
    status = Column(
        String(20), nullable=False, default=AgentStatus.ACTIVE.value, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<Agent agent_id={self.agent_id!r} name={self.name!r} "
            f"status={self.status!r}>"
        )
