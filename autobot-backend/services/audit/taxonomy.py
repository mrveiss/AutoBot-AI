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
actions, was ``services/audit/audit_log.py``), ``ComplianceEventType`` (compliance events,
was ``services/event_log.py``) and ``AuditEventType`` (knowledge events, was
``knowledge/audit_log.py``). Every one of them is recorded as an ``AuditEvent``.
"""

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict

from autobot_shared.audit_actions import canonical_action, spellings_of


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
    KNOWLEDGE_QUARANTINE_READ = "knowledge.quarantine.read"  # #19163: an opt-out read of the research quarantine
    KNOWLEDGE_ADMIN_READ = "kb.admin_read"  # #16665: an admin's read of any fact through an explicit read API
    API_KEY_CREATE = "api_key.create"  # pragma: allowlist secret -- an action name, not a key
    API_KEY_REVOKE = "api_key.revoke"  # pragma: allowlist secret -- an action name, not a key
    USER_CREATE = "user.create"
    USER_DELETE = "user.delete"
    USER_UPDATE = "user.update"  # #18716
    ROLE_ASSIGN = "role.assign"  # #18716
    ROLE_REVOKE = "role.revoke"  # #18716
    ROLE_CHANGE = "role.change"  # #18716
    PASSWORD_CHANGE = "password.change"  # nosec B105  # pragma: allowlist secret -- an action name (#18716)
    # auth.login / auth.logout (#18716): the outcome column says success or failure. One backend login
    # writes up to three rows, each a different fact, kept on purpose:
    #   1. middleware/audit_middleware.py path map -- the HTTP *attempt* (every status, no actor yet);
    #   2. shared UserService.authenticate via audit_row -- the credential *verdict* with user/org id and
    #      the failure reason (the only record of a failure the SLM also writes);
    #   3. api/auth.py emit_compliance -- the *session issued* record that feeds the admin event-log view.
    # auth_middleware.authenticate_user rows (a legacy file-user path with no production caller) use the same
    # spelling. A logout writes rows 1 and 3 only.
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_PERMISSION_CHECK = "auth.permission_check"  # #18716
    FILE_UPLOAD = "file.upload"  # #18716
    FILE_DOWNLOAD = "file.download"  # #18716
    FILE_CREATE = "file.create"  # #18716
    FILE_DELETE = "file.delete"  # #18716
    ELEVATION_REQUEST = "elevation.request"  # #18716
    ELEVATION_AUTHORIZE = "elevation.authorize"  # #18716
    ELEVATION_EXECUTE = "elevation.execute"  # #18716
    CONFIG_UPDATE = "config.update"  # #18716: was config.change; the writers and the dashboard say update
    ADMIN_ACTION = "admin.action"
    RUN_JWT_MINT = "run_jwt.mint"
    RUN_JWT_REVOKE = "run_jwt.revoke"
    RUN_JWT_REFRESH = "run_jwt.refresh"
    DEVICE_JWT_MINT = "device_jwt.mint"  # GH#9493
    SECRET_ACCESS = "secret.access"  # nosec B105  # pragma: allowlist secret -- an action name (#18811)
    CLAIMS_CREDENTIAL_MINT = "claims_credential.mint"  # #18811
    CLAIMS_CREDENTIAL_REVOKE = "claims_credential.revoke"  # #18811
    CLAIMS_CREDENTIAL_CHECK_FAILURES = "claims_credential.check_failures"  # #18811: one per source per window
    # #19241: a provider sign-in disconnect (user / org system) or a superadmin's shared-token revoke.
    PROVIDER_SIGNIN_REVOKE = "provider_signin.revoke"
    # identity vocabulary (#19035); IdentityAuditAction spellings map here through audit_actions.ACTION_ALIASES.
    # auth.mfa carries verified / failed / backup-code in the outcome column, like auth.login.
    AUTH_MFA = "auth.mfa"
    AUTH_LOCKOUT = "auth.lockout"
    AUTH_UNLOCK = "auth.unlock"
    MFA_ENABLE = "mfa.enable"
    MFA_DISABLE = "mfa.disable"
    ACCESS_DENIED = "access.denied"
    PASSWORD_RESET_REQUEST = "password.reset_request"  # nosec B105  # pragma: allowlist secret -- an action name
    PASSWORD_RESET = "password.reset"  # nosec B105  # pragma: allowlist secret -- an action name
    SSO_LINK = "sso.link"
    SSO_UNLINK = "sso.unlink"
    USER_ACTIVATE = "user.activate"
    USER_DEACTIVATE = "user.deactivate"
    TEAM_CREATE = "team.create"
    TEAM_UPDATE = "team.update"
    TEAM_DELETE = "team.delete"
    TEAM_MEMBER_ADD = "team.member_add"
    TEAM_MEMBER_REMOVE = "team.member_remove"
    TEAM_MEMBER_ROLE_CHANGE = "team.member_role_change"
    ORG_CREATE = "org.create"
    ORG_UPDATE = "org.update"
    ORG_DELETE = "org.delete"
    ORG_SUBSCRIPTION_TIER_DROP = "org.subscription_tier.drop"
    CLEANUP_ENV_COPIES = "cleanup.env_copies"  # #20567: old .env.*~ copies removed after approval
    CLEANUP_INFRASTRUCTURE_DIR = "cleanup.infrastructure_dir"  # #20567: stale install directory removed after approval
    ROLE_CREATE = "role.create"
    ROLE_UPDATE = "role.update"
    ROLE_DELETE = "role.delete"
    API_KEY_USE = "api_key.use"  # pragma: allowlist secret -- an action name, not a key
    SECURITY_SUSPICIOUS_ACTIVITY = "security.suspicious_activity"


class ComplianceEventType(str, Enum):
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
    """The stored action string for an enum member or a plain string, in its canonical spelling (#18716)."""
    return canonical_action(action)


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
        cols = ("actor_id", "session_id", "outcome", "resource_type", "resource_id")
        return {c: getattr(self, c) for c in cols if getattr(self, c) is not None}

    def action_set(self) -> frozenset[str] | None:
        """Every stored spelling ``action`` / ``actions`` accept, aliases of old rows included (#18716).

        The alias half shrinks once the approved data migration has rewritten the stored rows.
        """
        sets = [spellings_of(self.action)] if self.action is not None else []
        if self.actions is not None:
            sets.append(frozenset().union(*(spellings_of(a) for a in self.actions)))
        return frozenset.intersection(*sets) if sets else None

    def matches(self, event: Dict[str, Any]) -> bool:
        """True when a stored event dict satisfies every set field."""
        if self.category is not None and event.get("category") != self.category.value:
            return False
        if any(event.get(col) != want for col, want in self._column_values().items()):
            return False
        accepted = self.action_set()
        if accepted is not None and event.get("action") not in accepted:
            return False
        meta = event.get("metadata") or {}
        if any(str(meta.get(k)) != v for k, v in self.metadata):
            return False
        ts = event.get("occurred_at", 0)
        return (self.from_ts is None or ts >= self.from_ts) and (self.to_ts is None or ts <= self.to_ts)
