# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Task Delegation Model (#1753)

Tracks tasks delegated from manager agents to their direct reports,
including escalation state.
"""

import uuid
from enum import Enum

from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import Uuid

from user_management.models.base import Base


class DelegationStatus(str, Enum):
    """Lifecycle states for a delegated task (#1753)."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"


class TaskDelegation(Base):
    """
    A task assigned from a manager to a direct report (#1753).

    The delegator_id must be a manager/coordinator in agent_org_nodes.
    The assignee_id must be a direct report of delegator_id.
    """

    __tablename__ = "task_delegations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delegator_id = Column(String(255), nullable=False, index=True)
    assignee_id = Column(String(255), nullable=False, index=True)
    task_description = Column(Text, nullable=False)
    context = Column(JSONB, nullable=True)
    status = Column(
        String(20),
        nullable=False,
        default=DelegationStatus.PENDING.value,
        index=True,
    )
    escalated_to = Column(String(255), nullable=True)
    result = Column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<TaskDelegation {self.delegator_id}->{self.assignee_id} " f"status={self.status!r}>"
