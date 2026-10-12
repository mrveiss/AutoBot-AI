# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one constructor of an ``audit_logs`` row (#17225 D1).

``audit_logs`` is the audit trail's system of record. Every writer builds its
row here -- the backend's canonical audit service and the shared RBAC, org and
team writers alike -- so there is one schema and one mapping onto it, whichever
process writes. The writers that run inside an ORM session (an org change and
its audit row commit together) keep that session; only the row's shape is
shared.

Mapping rules, fixed here and nowhere else:

* ``actor`` is always set: the caller's actor string, else the user UUID, else
  ``"system"``. ``user_id`` (a foreign key to ``users``) is set only by a caller
  that has a real user row.
* ``resource_ref`` always carries the resource as text; ``resource_id`` (a UUID
  column) is filled too when the text is a UUID.
* ``action`` is capped at the column width; the full value is kept in
  ``details[ACTION_FULL_KEY]`` rather than lost.
"""

from __future__ import annotations

import uuid
from typing import Any

from autobot_shared.user_management.models.audit import AuditLog

#: Recorded when no actor is known.
SYSTEM_ACTOR = "system"
#: Where an action longer than the column is kept whole.
ACTION_FULL_KEY = "action_full"
#: ``resource_type`` is NOT NULL in the original schema.
UNSPECIFIED_RESOURCE = "unspecified"
_TABLE = AuditLog.__table__
_ACTION_WIDTH = _TABLE.c.action.type.length


def _as_uuid(value: Any) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _fit(value: str | None, column: str) -> str | None:
    """Cap free text at its column width so an over-long value cannot cost the whole row."""
    width = _TABLE.c[column].type.length
    return value if value is None or len(value) <= width else value[:width]


def _capped_action(action: str, details: dict) -> tuple[str, dict]:
    if len(action) <= _ACTION_WIDTH:
        return action, details
    return action[:_ACTION_WIDTH], {**details, ACTION_FULL_KEY: action}


def _context_columns(context: dict) -> dict[str, Any]:
    """The request-context columns, each capped at its width, plus the row id and time."""
    columns: dict[str, Any] = {
        name: _fit(context.get(name), name) for name in ("ip_address", "user_agent", "session_id")
    }
    columns["id"] = _as_uuid(context.get("event_id")) or uuid.uuid4()
    if context.get("occurred_at") is not None:
        columns["created_at"] = context["occurred_at"]
    return columns


def audit_row(
    *,
    action: str,
    resource_type: str | None,
    resource: Any = None,
    actor: str | None = None,
    user_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    category: str = "security",
    outcome: str = "success",
    details: dict | None = None,
    **context: Any,
) -> AuditLog:
    """One ``audit_logs`` row.

    *context*: ``ip_address``, ``user_agent``, ``session_id``, ``event_id``, ``occurred_at``.
    """
    stored_action, stored_details = _capped_action(action, dict(details or {}))
    return AuditLog(
        category=category,
        actor=_fit(actor or (str(user_id) if user_id else SYSTEM_ACTOR), "actor"),
        user_id=user_id,
        org_id=org_id,
        action=stored_action,
        resource_type=_fit(resource_type or UNSPECIFIED_RESOURCE, "resource_type"),
        resource_ref=_fit(None if resource is None else str(resource), "resource_ref"),
        resource_id=_as_uuid(resource),
        outcome=outcome,
        details=stored_details,
        **_context_columns(context),
    )
