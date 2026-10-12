# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The audit record and every action vocabulary that names one (#17225).

One home for the types, so the canonical service (``services.audit.audit``)
and the retired modules that still re-export them import from here rather than
from each other. Before #17225 the canonical service imported its enums from the
three modules it replaced, which is why those modules could not be retired.

The three legacy enums are vocabularies, not stores: ``AuditAction`` (security
actions, was ``services/audit/audit_log.py``), ``EventType`` (compliance events,
was ``services/event_log.py``) and ``AuditEventType`` (knowledge events, was
``knowledge/audit_log.py``). Every one of them is recorded as an ``AuditEvent``.
"""

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict


class AuditCategory(str, Enum):
    """Top-level audit taxonomy; each category has its own retention (retention.py)."""

    SECURITY = "security"  # session, api_key, user, config, operation audit
    COMPLIANCE = "compliance"  # login/logout, agent invoke
    KNOWLEDGE = "knowledge"  # view, search, share
    GOVERNANCE = "governance"  # skill approval, budget breach, agent pause


@dataclass
class AuditEvent:
    """One audit record: who did what to which resource, when, with what outcome."""

    category: AuditCategory
    action: str
    actor_id: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    resource_type: str | None = None
    resource_id: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    occurred_at: float = field(default_factory=time.time)
    ip_address: str | None = None
    session_id: str | None = None
    outcome: str = "success"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        return d


class AuditAction(str, Enum):
    """Security actions (was ``services.audit.audit_log.AuditAction``)."""

    SESSION_CREATE = "session.create"
    SESSION_DELETE = "session.delete"
    SESSION_EXPORT = "session.export"
    KNOWLEDGE_ADD = "knowledge.add"
    KNOWLEDGE_REMOVE = "knowledge.remove"
    API_KEY_CREATE = "api_key.create"  # pragma: allowlist secret -- an action name, not a key
    API_KEY_REVOKE = "api_key.revoke"  # pragma: allowlist secret -- an action name, not a key
    USER_CREATE = "user.create"
    USER_DELETE = "user.delete"
    CONFIG_CHANGE = "config.change"
    ADMIN_ACTION = "admin.action"
    RUN_JWT_MINT = "run_jwt.mint"
    RUN_JWT_REVOKE = "run_jwt.revoke"
    RUN_JWT_REFRESH = "run_jwt.refresh"
    DEVICE_JWT_MINT = "device_jwt.mint"  # GH#9493


class EventType(str, Enum):
    """Compliance events (was ``services.event_log.EventType``)."""

    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_CREATED = "user.created"
    USER_ROLE_CHANGED = "user.role_changed"
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_DELETED = "document.deleted"
    AGENT_INVOKED = "agent.invoked"
    CONFIG_CHANGED = "config.changed"
    API_KEY_CREATED = "api_key.created"  # pragma: allowlist secret -- an action name, not a key
    API_KEY_DELETED = "api_key.deleted"  # pragma: allowlist secret -- an action name, not a key


class AuditEventType(str, Enum):
    """Knowledge events (was ``knowledge.audit_log.AuditEventType``)."""

    VIEW = "view"
    SEARCH = "search"
    DOWNLOAD = "download"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SHARE = "share"
    UNSHARE = "unshare"
    CHANGE_VISIBILITY = "change_visibility"
    CHANGE_OWNER = "change_owner"
    POLICY_UPDATE = "policy_update"
    BULK_DELETE = "bulk_delete"
    EXPORT = "export"


def event_from_dict(data: Dict[str, Any]) -> AuditEvent:
    """The inverse of :meth:`AuditEvent.to_dict`."""
    return AuditEvent(
        category=AuditCategory(data["category"]),
        action=data["action"],
        actor_id=data.get("actor_id") or "system",
        id=data["id"],
        resource_type=data.get("resource_type"),
        resource_id=data.get("resource_id"),
        metadata=dict(data.get("metadata") or {}),
        occurred_at=float(data["occurred_at"]),
        ip_address=data.get("ip_address"),
        session_id=data.get("session_id"),
        outcome=data.get("outcome") or "success",
    )


def action_name(action: Any) -> str:
    """The stored action string for an enum member or a plain string."""
    return action.value if isinstance(action, Enum) else str(action)


@dataclass(frozen=True)
class AuditFilter:
    """One question asked of the audit trail; every field is optional and ANDed.

    ``actions`` matches any of a set (the knowledge permission-change view);
    ``metadata`` matches by key equality (``organization_id``, ``vm_name``).
    """

    category: AuditCategory | None = None
    actor_id: str | None = None
    action: str | None = None
    actions: frozenset[str] | None = None
    session_id: str | None = None
    outcome: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()
    from_ts: float | None = None
    to_ts: float | None = None

    def _column_values(self) -> Dict[str, Any]:
        cols = ("actor_id", "action", "session_id", "outcome", "resource_type", "resource_id")
        return {c: getattr(self, c) for c in cols if getattr(self, c) is not None}

    def matches(self, event: Dict[str, Any]) -> bool:
        """True when a stored event dict satisfies every set field."""
        if self.category is not None and event.get("category") != self.category.value:
            return False
        if any(event.get(col) != want for col, want in self._column_values().items()):
            return False
        if self.actions is not None and event.get("action") not in self.actions:
            return False
        meta = event.get("metadata") or {}
        if any(str(meta.get(k)) != v for k, v in self.metadata):
            return False
        ts = event.get("occurred_at", 0)
        return (self.from_ts is None or ts >= self.from_ts) and (self.to_ts is None or ts <= self.to_ts)
