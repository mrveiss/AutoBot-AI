# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Never leave an install with no active platform admin (#21018).

One check, reached by every route that can take the last admin away: demotion
(``set_platform_admin``), deactivation and deletion (``UserService``), and the
SLM person-copy push that flips ``is_active`` directly. It answers 409 with the
stable code :data:`LAST_PLATFORM_ADMIN_CODE`, which a screen maps to its own text.

Race safety: lock order is ONE everywhere. The check locks, in one ``SELECT ... FOR UPDATE`` ordered
by id, EVERY active-admin row plus the target row (an admin or not: a target that looks like a non-admin may be
promoted concurrently, and the target lock is what holds that promotion off until this change commits), and
decides on the rows it got back. Every
caller takes this lock before it locks the target on its own, so two concurrent changes to the last two
admins queue on the same rows in the same order and cannot deadlock; the second re-evaluates after the
first commits, no longer sees the first admin as active, and is refused. A deadlock or serialization
failure that still happens is rolled back and answered as a RETRY (:class:`LastPlatformAdminRetry`, 503 with
Retry-After), never as the refusal: the change was not judged, so the caller retries. Locks are held until commit.
"""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.user_management.user_service_errors import UserServiceError

logger = get_logger(__name__)

#: PostgreSQL deadlock_detected and serialization_failure.
_RETRYABLE_SQLSTATES = frozenset({"40P01", "40001"})

#: Stable machine-readable code of the 409; the frontend keys its translated message on it.
LAST_PLATFORM_ADMIN_CODE = "last_platform_admin"
LAST_PLATFORM_ADMIN_MESSAGE = "This would leave no active platform admin; make another user an active admin first."
#: Code of the 503 answered for a transient lock failure, and the Retry-After (seconds) sent with it.
LAST_PLATFORM_ADMIN_RETRY_CODE = "last_platform_admin_retry"
LAST_PLATFORM_ADMIN_RETRY_MESSAGE = "Another admin change was in progress; nothing was changed, retry shortly."
LAST_ADMIN_RETRY_AFTER_S = env_int_clamped("AUTOBOT_LAST_ADMIN_RETRY_AFTER_S", 1, min_v=1, max_v=30)


class LastPlatformAdminError(UserServiceError):
    """Raised when a change would leave zero active platform admins (#21018)."""

    status_code = 409
    code = LAST_PLATFORM_ADMIN_CODE

    def __init__(self, message: str = LAST_PLATFORM_ADMIN_MESSAGE):
        super().__init__(message)


class LastPlatformAdminRetry(LastPlatformAdminError):
    """A deadlock or serialization failure while judging the change: it was rolled back, not refused (#21018)."""

    status_code = 503
    code = LAST_PLATFORM_ADMIN_RETRY_CODE

    def __init__(self, message: str = LAST_PLATFORM_ADMIN_RETRY_MESSAGE):
        super().__init__(message)


def _is_active_admin(row: Any) -> bool:
    return bool(row.is_platform_admin and row.is_active and row.deleted_at is None)


async def lock_platform_admin_rows(session: AsyncSession, user_model: Any, user_id: uuid.UUID) -> list[Any]:
    """The active platform admins plus the target, locked in id order until the transaction ends."""
    query = (
        select(user_model.id, user_model.is_platform_admin, user_model.is_active, user_model.deleted_at)
        .where(
            or_(
                user_model.id == user_id,
                and_(
                    user_model.is_platform_admin.is_(True),
                    user_model.is_active.is_(True),
                    user_model.deleted_at.is_(None),
                ),
            )
        )
        .order_by(user_model.id)
        .with_for_update()
    )
    return list((await session.execute(query)).all())


def _is_serialization_failure(exc: DBAPIError) -> bool:
    state = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
    return state in _RETRYABLE_SQLSTATES


async def ensure_not_last_platform_admin(session: AsyncSession, user_model: Any, user_id: uuid.UUID) -> None:
    """Raise :class:`LastPlatformAdminError` if *user_id* is the only active platform admin.

    Always takes the id-ordered lock (active admins plus the target) and judges the locked rows, never a
    stale copy; a target that is not an active admin is simply not among the admins and passes.
    """
    try:
        rows = await lock_platform_admin_rows(session, user_model, user_id)
    except DBAPIError as exc:
        if not _is_serialization_failure(exc):
            raise
        await session.rollback()  # the transaction is aborted: nothing of it stands, the change was not judged
        raise LastPlatformAdminRetry() from exc
    admins = {row.id for row in rows if _is_active_admin(row)}
    if user_id in admins and len(admins) == 1:
        raise LastPlatformAdminError()


def last_admin_http_error(exc: LastPlatformAdminError) -> HTTPException:
    """The answer a route gives: the 409 refusal, or the 503 + Retry-After for a retryable lock failure."""
    headers = {"Retry-After": str(LAST_ADMIN_RETRY_AFTER_S)} if isinstance(exc, LastPlatformAdminRetry) else None
    return HTTPException(exc.status_code, detail={"code": exc.code, "message": str(exc)}, headers=headers)


async def refuse_last_platform_admin(session: AsyncSession, exc: LastPlatformAdminError) -> HTTPException:
    """Commit the refusal's audit row (and release the locks), then return the 409 (or retry 503) to raise.

    The service wrote the denied audit entry before raising; a route that lets the exception
    roll the session back would lose it, so the route commits it here. The caller MUST run the
    guard before it applies any other change in the request, so the audit row is all that commits.
    """
    await session.commit()
    verdict = "Retry" if isinstance(exc, LastPlatformAdminRetry) else "Refused"
    logger.warning("%s: change to the last platform admin", verdict)
    return last_admin_http_error(exc)
