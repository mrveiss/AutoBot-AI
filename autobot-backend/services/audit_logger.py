# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Operation audit logging -- an adapter onto the canonical audit service (#17225 D3).

Until #17225 this module was its own store: Redis database 10, a daily
``audit:log:<date>`` partition plus five index zsets per entry, its own batching,
retention and a JSONL fallback. It answered the same question as
``services.audit.audit`` -- who did what, when, with what result -- under a
different schema. It now keeps its call surface (``audit_log()``,
``get_audit_logger().log/query``) and stores nothing itself: an ``AuditEntry`` is
recorded as a SECURITY ``AuditEvent`` and read back from the canonical trail, so
operation records and every other audit record answer one query.

Field mapping (entry -> event): ``operation``->``action``, ``user_id``->``actor_id``
(``"system"`` when absent), ``result``->``outcome``, ``resource``->``resource_id``,
``session_id``/``ip_address`` unchanged; ``details``, ``user_role``, ``vm_name``,
``vm_source`` and ``performance_ms`` go to ``metadata``. Entries are sanitised
(OWASP: no passwords, tokens, keys) before they are recorded.

The database-10 keys are no longer written or read; they expire by the TTL they
were written with (D2).
"""

import socket
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal

from autobot_shared.audit_actions import canonical_action
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from constants.network_constants import NetworkConstants
from services.audit import audit as canonical
from services.audit.taxonomy import AuditCategory, AuditEvent, AuditFilter
from type_defs.common import Metadata

logger = get_logger(__name__)

# Bind-all / loopback placeholders that are not routable hosts and must not be
# shown as the backend address in the audit dashboard (#10502 item #11).
_NON_ROUTABLE_HOSTS = frozenset({"0.0.0.0", "::", "127.0.0.1", "::1", "localhost", ""})

AuditResult = Literal["success", "denied", "failed", "error"]

#: Actor recorded when an operation has no user (a system action).
SYSTEM_ACTOR = "system"

#: Default query window when the caller gives no start time.
_DEFAULT_QUERY_WINDOW = timedelta(days=1)

_SENSITIVE_KEYS = frozenset(
    {"password", "token", "secret", "api_key", "private_key", "session_token", "jwt", "authorization", "cookie"}
)
_ENTRY_META_KEYS = ("user_role", "vm_name", "vm_source", "performance_ms")

# Audit operation categories (the dashboard's filter vocabulary). Dotted canonical
# spellings only (#18716): a filter on one also matches the old underscore rows,
# because ``AuditFilter`` expands it through ``autobot_shared.audit_actions``.
OPERATION_CATEGORIES = {
    "auth.login": "Authentication",
    "auth.logout": "Authentication",
    "auth.permission_check": "Authentication",
    "auth.session_create": "Authentication",
    "auth.session_invalidate": "Authentication",
    "file.upload": "File Operations",
    "file.download": "File Operations",
    "file.delete": "File Operations",
    "file.create": "File Operations",
    "file.modify": "File Operations",
    "file.view": "File Operations",
    "elevation.request": "Privilege Escalation",
    "elevation.authorize": "Privilege Escalation",
    "elevation.execute": "Privilege Escalation",
    "session.create": "Session Management",
    "session.delete": "Session Management",
    "session.access": "Session Management",
    "session.update": "Session Management",
    "config.update": "Configuration",
    "config.delete": "Configuration",
    "config.view": "Configuration",
    "terminal.execute": "Terminal Operations",
    "terminal.create": "Terminal Operations",
    "terminal.delete": "Terminal Operations",
    "conversation.create": "Conversation Data",
    "conversation.access": "Conversation Data",
    "conversation.delete": "Conversation Data",
    "conversation.export": "Conversation Data",
}


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class AuditEntry:
    """OWASP/NIST operation audit entry: timestamp, operation, result, user, origin."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=lambda: _now().timestamp())
    date: str = field(default_factory=lambda: _now().strftime("%Y-%m-%d"))
    operation: str = ""
    result: AuditResult = "success"
    user_id: str | None = None
    ip_address: str | None = None
    session_id: str | None = None
    user_role: str | None = None
    resource: str | None = None
    vm_source: str | None = None
    vm_name: str | None = None
    details: Metadata = field(default_factory=dict)
    performance_ms: float | None = None

    def to_response_dict(self) -> Dict[str, Any]:
        """Every field, for the audit API response."""
        return dict(self.__dict__)

    def sanitize(self) -> "AuditEntry":
        """Drop sensitive keys from ``details`` (OWASP: never log secrets)."""
        if self.details:
            self.details = {k: v for k, v in self.details.items() if k.lower() not in _SENSITIVE_KEYS}
        return self

    def to_event(self) -> AuditEvent:
        """This entry as a canonical SECURITY event (field mapping in the module doc)."""
        meta: Dict[str, Any] = {"details": self.details}
        meta.update({k: getattr(self, k) for k in _ENTRY_META_KEYS if getattr(self, k) is not None})
        return AuditEvent(
            category=AuditCategory.SECURITY,
            action=canonical_action(self.operation),
            actor_id=self.user_id or SYSTEM_ACTOR,
            id=self.id,
            resource_id=self.resource,
            metadata=meta,
            occurred_at=self.timestamp,
            ip_address=self.ip_address,
            session_id=self.session_id,
            outcome=self.result,
        )

    @classmethod
    def from_event(cls, event: Dict[str, Any]) -> "AuditEntry":
        """A canonical event of any category, in the operation-entry shape."""
        meta = dict(event.get("metadata") or {})
        extra = {k: meta.pop(k) for k in _ENTRY_META_KEYS if k in meta}
        ts = float(event.get("occurred_at", 0))
        return cls(
            id=event.get("id") or str(uuid.uuid4()),
            timestamp=ts,
            date=datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
            operation=event.get("action", ""),
            result=event.get("outcome", "success"),
            user_id=event.get("actor_id"),
            ip_address=event.get("ip_address"),
            session_id=event.get("session_id"),
            resource=event.get("resource_id"),
            details=meta.pop("details", meta),
            **extra,
        )


def _entry_filter(start: datetime, end: datetime, **filters: Any) -> AuditFilter:
    vm_name = filters.pop("vm_name", None)
    return AuditFilter(
        actor_id=filters.get("user_id"),
        action=filters.get("operation"),
        session_id=filters.get("session_id"),
        outcome=filters.get("result"),
        metadata=(("vm_name", vm_name),) if vm_name else (),
        from_ts=start.timestamp(),
        to_ts=end.timestamp(),
    )


class AuditLogger:
    """Operation audit trail, recorded and read through ``services.audit.audit``."""

    def __init__(self) -> None:
        self.vm_source = config.vm.main
        self.vm_name = self._get_vm_name()
        self._total_logged = 0
        self._total_failed = 0

    def _get_vm_name(self) -> str:
        """Determine VM name from IP address."""
        vm_mapping = {
            NetworkConstants.MAIN_MACHINE_IP: "backend",
            NetworkConstants.FRONTEND_VM_IP: "frontend",
            NetworkConstants.NPU_WORKER_VM_IP: "npu-worker",
            NetworkConstants.REDIS_VM_IP: "redis",
            NetworkConstants.AI_STACK_VM_IP: "ai-stack",
            NetworkConstants.BROWSER_VM_IP: "browser",
        }
        return vm_mapping.get(self.vm_source, socket.gethostname())

    @property
    def display_host(self) -> str:
        """Routable host label for UIs (#10502 item #11): never a bind-all or loopback address."""
        source = (self.vm_source or "").strip()
        if source.lower() in _NON_ROUTABLE_HOSTS:
            return socket.getfqdn() or socket.gethostname()
        return source

    def _entry(self, operation: str, result: AuditResult, **fields: Any) -> AuditEntry:
        details = fields.pop("details", None) or {}
        entry = AuditEntry(
            operation=operation,
            result=result,
            vm_source=self.vm_source,
            vm_name=self.vm_name,
            details=details,
            **fields,
        )
        return entry.sanitize()

    async def log(
        self,
        operation: str,
        result: AuditResult = "success",
        user_id: str | None = None,
        session_id: str | None = None,
        ip_address: str | None = None,
        resource: str | None = None,
        user_role: str | None = None,
        details: Metadata | None = None,
        performance_ms: float | None = None,
        durable: bool = False,
    ) -> bool:
        """Record one operation. Non-blocking: the write is scheduled, never awaited (#1088).

        With ``durable`` the write is awaited and the result is whether the ``audit_logs`` row was
        committed, for a caller that must not act without one (#19860, as #20026).
        """
        fields = dict(user_id=user_id, session_id=session_id, ip_address=ip_address, resource=resource)
        fields.update(user_role=user_role, details=details, performance_ms=performance_ms)
        try:
            event = self._entry(operation, result, **fields).to_event()
            if durable:
                written = await canonical.record_committed(event)
                self._total_logged += int(written)
                self._total_failed += int(not written)
                return written
            canonical.emit(event)
        except Exception as exc:  # noqa: BLE001 -- an audit failure must not fail the operation
            self._total_failed += 1
            logger.error("Audit logging failed for %s: %s", operation, type(exc).__name__)
            return False
        self._total_logged += 1
        return True

    async def query(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
        **filters: Any,
    ) -> List[AuditEntry]:
        """Entries matching ``operation``/``user_id``/``session_id``/``vm_name``/``result``, newest first."""
        end = end_time or _now()
        start = start_time or end - _DEFAULT_QUERY_WINDOW
        flt = _entry_filter(start, end, **{k: v for k, v in filters.items() if v is not None})
        events = await canonical.query_filtered(flt, limit=limit, offset=offset)
        return [AuditEntry.from_event(e) for e in events]

    async def get_statistics(self) -> Metadata:
        """Process counters plus the number of audit records in the last 24 hours."""
        recent = await canonical.count_since((_now() - timedelta(days=1)).timestamp())
        stats: Metadata = {
            "total_logged": self._total_logged,
            "total_failed": self._total_failed,
            "redis_available": recent is not None,
        }
        if recent is not None:
            stats["entries_last_24h"] = recent
        return stats

    async def cleanup_old_logs(self, days_to_keep: int | None = None) -> None:
        """Apply retention now; ``days_to_keep`` caps every category's period from the policy table."""
        result = await canonical.apply_retention(cap_days=days_to_keep)
        logger.info("Audit cleanup complete: %d records removed, %d errors", result.deleted, result.errors)

    async def flush(self) -> None:
        """Nothing is buffered here any more; kept for the shutdown hook's call."""

    async def close(self) -> None:
        """Log the counters at shutdown."""
        logger.info("Audit logger shutdown: %d entries logged, %d failed", self._total_logged, self._total_failed)


_audit_logger: AuditLogger | None = None


async def get_audit_logger() -> AuditLogger:
    """The process-wide audit logger."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


async def close_audit_logger() -> None:
    """Close and forget the process-wide audit logger."""
    global _audit_logger
    if _audit_logger is not None:
        await _audit_logger.close()
        _audit_logger = None


async def audit_log(operation: str, result: AuditResult = "success", **kwargs: Any) -> bool:
    """Record one operation: ``await audit_log("auth.login", user_id="admin", ip_address=ip)``."""
    return await (await get_audit_logger()).log(operation, result, **kwargs)
