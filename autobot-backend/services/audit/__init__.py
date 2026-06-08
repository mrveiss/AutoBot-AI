# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Structured audit log service (Issue #4456).

Provides a function-based API for recording and querying security-relevant
mutating operations.  Backed by a Redis sorted set with 90-day TTL.

Usage::

    from services.audit import AuditAction, audit_record, query_audit_log

    # Fire-and-forget (sync, safe from any async context)
    audit_record(user_id="alice", action=AuditAction.SESSION_CREATE,
                 resource_type="session", resource_id="s-123")

    # Async query
    events = await query_audit_log(user_id="alice", limit=50)
"""

from services.audit.audit_log import (
    AuditAction,
    audit_record,
    query_audit_log,
    record_event,
)

__all__ = [
    "AuditAction",
    "audit_record",
    "query_audit_log",
    "record_event",
]
