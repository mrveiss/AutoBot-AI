# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Keep the SLM's copy of a linked person in step with the main app (#10200, maintainer decision).

After the link the main app is the record for password and active state. A change is pushed when it
commits, and a periodic pass pushes every linked person, which heals a missed push and any write
that bypassed the ORM. The SLM writes only what differs, so that pass changes nothing when in step.

A failed push is recorded on the link and shown to admins. A person deactivated during a failure
keeps SLM access until a push succeeds, so the failure must not be silent.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import event, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.http_egress_guard import assert_egress_policy
from autobot_shared.logging_manager import get_logger
from autobot_shared.node_proxy import internal_api_key
from user_management.models import User
from user_management.models.person_link import PersonLink

logger = get_logger(__name__)

PERSON_COPY_COMPARE_INTERVAL_S = env_int_clamped("AUTOBOT_PERSON_COPY_COMPARE_INTERVAL_S", 300, min_v=30)

_COPY_PATH = "/api/internal/person-copy"
_WATCHED_FIELDS = ("password_hash", "is_active", "deleted_at")
_CHANGED_KEY = "person_copy_changed_user_ids"
_background: set[asyncio.Task] = set()
_loop_task: asyncio.Task | None = None


async def _post_copy(slm_user_id: uuid.UUID, user: User) -> None:
    from services.slm_client import get_slm_client

    client = get_slm_client()
    if client is None:
        raise RuntimeError("SLM control link is not initialised")
    session = await client._get_session()
    url = client._rest_url(_COPY_PATH)
    await assert_egress_policy(url)
    payload = {
        "slm_user_id": str(slm_user_id),
        "password_hash": user.password_hash,
        "is_active": bool(user.is_active and user.deleted_at is None),
    }
    headers = {"X-Internal-API-Key": internal_api_key() or ""}
    async with session.post(url, json=payload, headers=headers, allow_redirects=False) as response:
        response.raise_for_status()


async def _push_link(link: PersonLink, user: User) -> None:
    """Push one person and record the outcome on their link. Only the error's type is kept."""
    try:
        await _post_copy(link.slm_user_id, user)
    except Exception as exc:
        logger.warning("Could not push %s's copy to the SLM: %s", user.username, type(exc).__name__)
        link.push_failed_at = link.push_failed_at or datetime.now(timezone.utc)
        link.push_error = type(exc).__name__
        return
    link.push_failed_at = None
    link.push_error = None


async def push_people(session: AsyncSession, user_ids: Iterable[uuid.UUID] | None = None) -> None:
    """Push the given linked people, or everyone linked. Commits the recorded outcomes."""
    query = select(PersonLink, User).join(User, User.id == PersonLink.user_id)
    if user_ids is not None:
        query = query.where(PersonLink.user_id.in_(list(user_ids)))
    for link, user in (await session.execute(query)).all():
        await _push_link(link, user)
    await session.commit()


async def _push_in_own_session(user_ids: Iterable[uuid.UUID] | None) -> None:
    from user_management.database import get_async_session_factory

    async with get_async_session_factory()() as session:
        await push_people(session, user_ids)


def changed_user_ids(objects: Iterable[object]) -> set[uuid.UUID]:
    """Ids of the users among *objects* whose password or active state changed in this flush."""
    changed = set()
    for obj in objects:
        if isinstance(obj, User) and any(inspect(obj).attrs[field].history.has_changes() for field in _WATCHED_FIELDS):
            changed.add(obj.id)
    return changed


def _remember_changes(session: Session, _flush_context) -> None:
    session.info.setdefault(_CHANGED_KEY, set()).update(changed_user_ids(session.dirty))


def _forget_changes(session: Session) -> None:
    session.info.pop(_CHANGED_KEY, None)


def _push_committed_changes(session: Session) -> None:
    changed = session.info.pop(_CHANGED_KEY, None)
    if not changed:
        return
    try:
        task = asyncio.get_running_loop().create_task(_push_in_own_session(changed))
    except RuntimeError:  # no loop in this process: the periodic pass picks it up
        logger.info("No event loop for an immediate push; the periodic pass will carry it")
        return
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _compare_loop() -> None:
    while True:
        await asyncio.sleep(PERSON_COPY_COMPARE_INTERVAL_S)
        try:
            await _push_in_own_session(None)
        except Exception as exc:
            logger.warning("Periodic push of people to the SLM failed: %s", type(exc).__name__)


def start_person_copy_sync() -> None:
    """Watch commits and start the periodic pass, once per process."""
    global _loop_task
    if not event.contains(Session, "after_flush", _remember_changes):
        event.listen(Session, "after_flush", _remember_changes)
        event.listen(Session, "after_rollback", _forget_changes)
        event.listen(Session, "after_commit", _push_committed_changes)
    if _loop_task is None or _loop_task.done():
        _loop_task = asyncio.create_task(_compare_loop(), name="person-copy-compare")
