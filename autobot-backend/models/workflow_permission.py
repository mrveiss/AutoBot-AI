# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
WorkflowPermission Model (#2152)

Per-workflow access control: tracks which users have which roles on a given workflow.
Roles: owner, editor, viewer, runner.
"""

import uuid

from sqlalchemy import Column, DateTime, String, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.types import Uuid

from user_management.models.base import Base


class WorkflowPermission(Base):
    """
    Per-workflow permission entry (#2152).

    Associates a user with a role on a specific workflow.
    One row per (workflow_id, user_id) pair.
    """

    __tablename__ = "workflow_permissions"

    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workflow_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    # owner | editor | viewer | runner
    role = Column(String(50), nullable=False)
    granted_by = Column(String(255), nullable=True)
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

    __table_args__ = (UniqueConstraint("workflow_id", "user_id", name="uq_workflow_permission"),)

    def __repr__(self) -> str:
        return f"<WorkflowPermission workflow={self.workflow_id} " f"user={self.user_id} role={self.role}>"
