# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The audit trail's system of record: Postgres ``audit_logs`` (#17225 D1).

The owner chose to extend the existing table rather than add a second one, so
the rows the shared RBAC/org/team writers already put there and the rows the
canonical service records are one trail, answered by one query. Rows are built
by ``autobot_shared.user_management.audit_rows.audit_row`` -- the one mapping
onto this schema. The Redis keys in ``projection.py`` are a projection of this
table and :func:`rebuild_projection` reconstructs them from it.

Retention does not delete from here: this table is documented as immutable,
and removing compliance records is an owner decision (#17038), not a policy
this module applies on its own.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import func, select

from autobot_shared.store_authority import system_of_record
from autobot_shared.user_management.audit_rows import ACTION_FULL_KEY, audit_row
from autobot_shared.user_management.models.audit import AuditLog
from services.audit.taxonomy import AuditEvent, AuditFilter
from user_management.database import db_session_context

# Declares Postgres audit_logs as the audit trail's system of record (#17225 D1).
SYSTEM_OF_RECORD = system_of_record("audit_trail")


def _row_for(event: AuditEvent) -> AuditLog:
    return audit_row(
        category=event.category.value,
        actor=event.actor_id,
        action=event.action,
        resource_type=event.resource_type,
        resource=event.resource_id,
        outcome=event.outcome,
        details=event.metadata,
        ip_address=event.ip_address,
        session_id=event.session_id,
        event_id=event.id,
        occurred_at=datetime.fromtimestamp(event.occurred_at, tz=timezone.utc),
    )


async def insert_event(event: AuditEvent) -> None:
    """Persist one event as an ``audit_logs`` row; raises if the database refuses it."""
    async with db_session_context() as session:
        session.add(_row_for(event))


def _column_filters(flt: AuditFilter) -> list:
    pairs = (
        (AuditLog.actor, flt.actor_id),
        (AuditLog.action, flt.action),
        (AuditLog.session_id, flt.session_id),
        (AuditLog.outcome, flt.outcome),
        (AuditLog.resource_type, flt.resource_type),
        (AuditLog.resource_ref, flt.resource_id),
        (AuditLog.category, flt.category.value if flt.category else None),
    )
    return [column == value for column, value in pairs if value is not None]


def where_clauses(flt: AuditFilter) -> list:
    """*flt* as SQL predicates on ``audit_logs`` (ANDed)."""
    clauses = _column_filters(flt)
    if flt.actions is not None:
        clauses.append(AuditLog.action.in_(sorted(flt.actions)))
    clauses.extend(AuditLog.details[key].astext == value for key, value in flt.metadata)
    if flt.from_ts is not None:
        clauses.append(AuditLog.created_at >= datetime.fromtimestamp(flt.from_ts, tz=timezone.utc))
    if flt.to_ts is not None:
        clauses.append(AuditLog.created_at <= datetime.fromtimestamp(flt.to_ts, tz=timezone.utc))
    return clauses


def row_to_event(row: AuditLog) -> Dict[str, Any]:
    """One row in the canonical event shape (``AuditEvent.to_dict``)."""
    details = dict(row.details or {})
    return {
        "id": str(row.id),
        "category": row.category,
        "action": details.pop(ACTION_FULL_KEY, row.action),
        "actor_id": row.actor or (str(row.user_id) if row.user_id else None),
        "resource_type": row.resource_type,
        "resource_id": row.resource_ref or (str(row.resource_id) if row.resource_id else None),
        "metadata": details,
        "occurred_at": row.created_at.timestamp(),
        "ip_address": row.ip_address,
        "session_id": row.session_id,
        "outcome": row.outcome,
    }


async def select_events(flt: AuditFilter, limit: int, offset: int) -> List[Dict[str, Any]]:
    """Events matching *flt*, newest first."""
    stmt = select(AuditLog).where(*where_clauses(flt)).order_by(AuditLog.created_at.desc())
    async with db_session_context() as session:
        rows = (await session.execute(stmt.offset(offset).limit(limit))).scalars().all()
    return [row_to_event(r) for r in rows]


async def count_events(from_ts: float) -> int:
    """Rows recorded at or after *from_ts*."""
    since = datetime.fromtimestamp(from_ts, tz=timezone.utc)
    async with db_session_context() as session:
        stmt = select(func.count()).select_from(AuditLog).where(AuditLog.created_at >= since)
        return int((await session.execute(stmt)).scalar_one())
