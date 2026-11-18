# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared audit emitter for the retention Celery tasks (GH#17856).

Chat, file and knowledge retention all record a ``retention_purge`` event
that differs only by resource type and audit category.
"""

from typing import Any, Dict

from services.audit.audit import AuditCategory, AuditEvent
from services.audit.audit import emit as audit_emit


def emit_deletion_audit(
    resource_id: str,
    resource_type: str,
    extra: Dict[str, Any],
    category: AuditCategory = AuditCategory.SECURITY,
) -> None:
    """Fire-and-forget audit event for a retention deletion."""
    audit_emit(
        AuditEvent(
            category=category,
            action="retention_purge",
            actor_id="system:retention_worker",
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=extra,
        )
    )
