# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Knowledge audit views over the canonical audit trail (#679, #17225 D2).

Replaces ``knowledge/audit_log.py``, which kept its own ``audit:user:<id>``,
``audit:fact:<id>`` and ``audit:org:<id>`` index zsets plus a ``setex`` body per
event -- and was subclassed by the canonical service, so every knowledge event
was written twice. Knowledge events are now KNOWLEDGE-category ``AuditEvent``
records: a fact is ``resource_type="fact"``/``resource_id=<fact_id>`` and the
organisation is ``metadata["organization_id"]``. The read methods keep the
response shape ``api/knowledge_audit.py`` has always returned.

The old index zsets are no longer written or read; they expire by their own TTL.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from services.audit.audit import emit_knowledge, query_filtered
from services.audit.taxonomy import AuditCategory, AuditEventType, AuditFilter

_ORG_KEY = "organization_id"
_FACT = "fact"
_PERMISSION_EVENTS = frozenset(
    t.value
    for t in (
        AuditEventType.SHARE,
        AuditEventType.UNSHARE,
        AuditEventType.CHANGE_VISIBILITY,
        AuditEventType.CHANGE_OWNER,
    )
)
_MODIFICATION_EVENTS = frozenset(t.value for t in (AuditEventType.CREATE, AuditEventType.UPDATE, AuditEventType.DELETE))
#: Page size when a caller gives none -- the API's own default.
_DEFAULT_LIMIT = 100
#: The organisation log's default page, unchanged from knowledge/audit_log.py.
_ORG_DEFAULT_LIMIT = 1000
_REPORT_PERMISSION_EVENTS = (AuditEventType.SHARE, AuditEventType.UNSHARE, AuditEventType.CHANGE_VISIBILITY)


def to_knowledge_view(event: Dict[str, Any]) -> Dict[str, Any]:
    """One canonical event in the shape the knowledge audit API returns."""
    meta = dict(event.get("metadata") or {})
    org = meta.pop(_ORG_KEY, None)
    is_fact = event.get("resource_type") == _FACT
    return {
        "id": event.get("id"),
        "type": event.get("action"),
        "user_id": event.get("actor_id"),
        "fact_id": event.get("resource_id") if is_fact else None,
        "organization_id": org,
        "details": meta,
        "ip_address": event.get("ip_address"),
        "timestamp": datetime.fromtimestamp(event.get("occurred_at", 0), tz=timezone.utc).isoformat(),
    }


async def _view(flt: AuditFilter, limit: int, offset: int = 0) -> List[Dict[str, Any]]:
    return [to_knowledge_view(e) for e in await query_filtered(flt, limit=limit, offset=offset)]


class KnowledgeAuditLog:
    """Knowledge audit trail, recorded and read through the canonical service."""

    def __init__(self, redis_client: Any = None) -> None:
        # The client is accepted for the constructor callers already make; the
        # canonical service owns its own connection.
        self.redis_client = redis_client

    async def log_event(
        self,
        event_type: AuditEventType,
        user_id: str,
        fact_id: str | None = None,
        organization_id: str | None = None,
        details: Dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Record one knowledge event as a KNOWLEDGE ``AuditEvent``."""
        metadata = dict(details or {})
        if organization_id:
            metadata[_ORG_KEY] = organization_id
        await emit_knowledge(
            event_type,
            user_id,
            resource_type=_FACT if fact_id else "knowledge",
            resource_id=fact_id or organization_id,
            metadata=metadata,
            ip_address=ip_address,
        )

    async def get_user_activity(self, user_id: str, limit: int = _DEFAULT_LIMIT, offset: int = 0) -> List[Dict]:
        """Knowledge events performed by *user_id*, newest first."""
        return await _view(AuditFilter(category=AuditCategory.KNOWLEDGE, actor_id=user_id), limit, offset)

    async def get_fact_access_log(self, fact_id: str, limit: int = _DEFAULT_LIMIT) -> List[Dict]:
        """Knowledge events on one fact, newest first."""
        flt = AuditFilter(category=AuditCategory.KNOWLEDGE, resource_type=_FACT, resource_id=fact_id)
        return await _view(flt, limit)

    async def get_organization_audit_log(
        self, organization_id: str, limit: int = _ORG_DEFAULT_LIMIT, offset: int = 0
    ) -> List[Dict]:
        """Knowledge events in one organisation, newest first."""
        flt = AuditFilter(category=AuditCategory.KNOWLEDGE, metadata=((_ORG_KEY, organization_id),))
        return await _view(flt, limit, offset)

    async def get_permission_changes(
        self, fact_id: str | None = None, user_id: str | None = None, limit: int = _DEFAULT_LIMIT
    ) -> List[Dict]:
        """Share/unshare/visibility/owner changes for a fact or by a user; [] with neither."""
        if not fact_id and not user_id:
            return []
        flt = AuditFilter(
            category=AuditCategory.KNOWLEDGE,
            actions=_PERMISSION_EVENTS,
            actor_id=None if fact_id else user_id,
            resource_type=_FACT if fact_id else None,
            resource_id=fact_id,
        )
        return await _view(flt, limit)

    async def generate_compliance_report(self, organization_id: str, start_date: datetime, end_date: datetime) -> Dict:
        """Event, user and modification counts for one organisation in a window."""
        flt = AuditFilter(
            category=AuditCategory.KNOWLEDGE,
            metadata=((_ORG_KEY, organization_id),),
            from_ts=start_date.timestamp(),
            to_ts=end_date.timestamp(),
        )
        events = await _view(flt, limit=_REPORT_SCAN_LIMIT)
        return _report(organization_id, start_date, end_date, events)


#: A compliance report counts every event in its window, up to the query scan cap.
_REPORT_SCAN_LIMIT = 10_000


def _compliance_stats(events: List[Dict]) -> Tuple[Dict, Dict, set]:
    counts: Dict[str, int] = {}
    users: Dict[str, int] = {}
    modified: set = set()
    for ev in events:
        etype = ev.get("type")
        counts[etype] = counts.get(etype, 0) + 1
        if ev.get("user_id"):
            users[ev["user_id"]] = users.get(ev["user_id"], 0) + 1
        if ev.get("fact_id") and etype in _MODIFICATION_EVENTS:
            modified.add(ev["fact_id"])
    return counts, users, modified


def _report(org: str, start: datetime, end: datetime, events: List[Dict]) -> Dict:
    counts, users, modified = _compliance_stats(events)
    top = sorted(({"user_id": u, "count": c} for u, c in users.items()), key=lambda x: x["count"], reverse=True)
    return {
        "organization_id": org,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "total_events": len(events),
        "event_counts": counts,
        "unique_users": len(users),
        "most_active_users": top[:10],
        "facts_modified": len(modified),
        "permission_changes": sum(counts.get(t.value, 0) for t in _REPORT_PERMISSION_EVENTS),
    }
