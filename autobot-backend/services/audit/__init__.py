# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The canonical audit service (#17225); see ``services/audit/audit.py``.

Usage::

    from services.audit import AuditAction, audit_record, query

    # Fire-and-forget (sync, safe from any async context)
    audit_record(user_id="alice", action=AuditAction.SESSION_CREATE,
                 resource_type="session", resource_id="s-123")

    # Async query: everything recorded for one user in a window
    events = await query(actor_id="alice", from_ts=t0, to_ts=t1)
"""

from services.audit.audit import (
    AuditAction,
    AuditCategory,
    AuditEvent,
    audit_record,
    emit,
    query,
    record,
)

__all__ = [
    "AuditAction",
    "AuditCategory",
    "AuditEvent",
    "audit_record",
    "emit",
    "query",
    "record",
]
