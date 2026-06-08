# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
WorkflowAuditLog Model (#2152)

Immutable audit trail for all workflow lifecycle actions:
create, edit, run, approve, delete, view, grant, revoke.
"""

import uuid

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.types import Uuid

from user_management.models.base import Base


class WorkflowAuditLog(Base):
    """
    Immutable audit log entry for a workflow action (#2152).

    Written once; never updated or deleted by the application.
    """

    __tablename__ = "workflow_audit_log"

    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    user_id = Column(String(255), nullable=False, index=True)
    workflow_id = Column(String(255), nullable=False, index=True)
    # create | edit | run | approve | delete | view | grant | revoke
    action = Column(String(50), nullable=False, index=True)
    details = Column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<WorkflowAuditLog workflow={self.workflow_id} " f"user={self.user_id} action={self.action}>"
