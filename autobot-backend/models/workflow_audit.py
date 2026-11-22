# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
WorkflowAuditLog Model (#2152)

Audit trail for all workflow lifecycle actions:
create, edit, run, approve, delete, view, grant, revoke.

Written once by convention. The database does not enforce it and the rows are not hash-chained
(the chain covers ``audit_logs``; this table joins it when it is recorded through the canonical
service, #18284).
"""

import uuid

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.types import Uuid

from user_management.models.base import Base


class WorkflowAuditLog(Base):
    """
    Audit log entry for a workflow action (#2152).

    Written once by convention: the application never updates or deletes it, but nothing in the
    database prevents either, and the row is not chained (#18284).
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
