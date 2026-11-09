# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Never leave an install with no active platform admin (#21018).

One check, reached by every route that can take the last admin away: demotion
(``set_platform_admin``), deactivation and deletion (``UserService``), and the
SLM person-copy push that flips ``is_active`` directly. It answers 409 with the
stable code :data:`LAST_PLATFORM_ADMIN_CODE`, which a screen maps to its own text.

Race safety: the check locks EVERY active-admin row (``SELECT ... FOR UPDATE``, in
id order so two checks cannot deadlock) and decides on the rows it got back. Two
concurrent changes to the last two admins queue on the same rows; the second one
re-evaluates the predicate after the first commits, no longer sees the first admin
as active, and is refused. The locks are held until the caller commits.
"""

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.user_management.user_service_errors import UserServiceError

logger = get_logger(__name__)

#: Stable machine-readable code of the 409; the frontend keys its translated message on it.
LAST_PLATFORM_ADMIN_CODE = "last_platform_admin"
LAST_PLATFORM_ADMIN_MESSAGE = "This would leave no active platform admin; make another user an active admin first."


class LastPlatformAdminError(UserServiceError):
    """Raised when a change would leave zero active platform admins (#21018)."""

    status_code = 409
    code = LAST_PLATFORM_ADMIN_CODE

    def __init__(self, message: str = LAST_PLATFORM_ADMIN_MESSAGE):
        super().__init__(message)


async def lock_active_platform_admin_ids(session: AsyncSession, user_model: Any) -> list[uuid.UUID]:
    """The ids of the active platform admins, their rows locked until the transaction ends."""
    query = (
        select(user_model.id)
        .where(
            user_model.is_platform_admin.is_(True),
            user_model.is_active.is_(True),
            user_model.deleted_at.is_(None),
        )
        .order_by(user_model.id)
        .with_for_update()
    )
    return list((await session.execute(query)).scalars().all())


async def ensure_not_last_platform_admin(session: AsyncSession, user_model: Any, user_id: uuid.UUID) -> None:
    """Raise :class:`LastPlatformAdminError` if *user_id* is the only active platform admin.

    A user who is not an active admin (judged on the locked rows, not on a possibly stale
    in-memory copy) can be demoted, deactivated or deleted freely.
    """
    admin_ids = await lock_active_platform_admin_ids(session, user_model)
    if user_id in admin_ids and len(admin_ids) == 1:
        raise LastPlatformAdminError()


def last_admin_http_error(exc: LastPlatformAdminError) -> HTTPException:
    """The 409 a route answers: stable ``code`` plus a human message."""
    return HTTPException(status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": str(exc)})


async def refuse_last_platform_admin(session: AsyncSession, exc: LastPlatformAdminError) -> HTTPException:
    """Commit the refusal's audit row (and release the locks), then return the 409 to raise.

    The service wrote the denied audit entry before raising; a route that lets the exception
    roll the session back would lose it, so the route commits it here. Nothing else is pending:
    the guard runs before any change.
    """
    await session.commit()
    logger.warning("Refused: change would leave no active platform admin")
    return last_admin_http_error(exc)
