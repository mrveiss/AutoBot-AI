# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Keep the SLM's copy of a linked person in step with the main app (#10200, maintainer decision).

After the link the main app is the record for password and active state. A change is pushed when it
commits, and a periodic pass pushes every linked person, which heals a missed push and any write
that bypassed the ORM. The SLM writes only what differs, so that pass changes nothing when in step.

The main app is the record, so an SLM-side change to a linked person's password or active state is
undone by the next pass, within the compare interval.

A failed push is recorded on the link and shown to admins. A person deactivated during a failure
keeps SLM access until a push succeeds, so the failure must not be silent.
"""

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Iterable

from aiohttp import ClientTimeout
from sqlalchemy import event, inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.http_egress_guard import assert_egress_policy
from autobot_shared.leader_lease import LeaderLease
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_utils import delete_if_value
from autobot_shared.user_management.last_platform_admin import LAST_PLATFORM_ADMIN_CODE
from autobot_shared.user_management.login_eligibility import login_refusal
from user_management.models import User
from user_management.models.person_link import PersonLink
from user_management.services.person_link_service import require_internal_key

logger = get_logger(__name__)

PERSON_COPY_COMPARE_INTERVAL_S = env_int_clamped("AUTOBOT_PERSON_COPY_COMPARE_INTERVAL_S", 300, min_v=30)

#: A link the SLM refused (last platform admin) is tried again only after this long since its last attempt: the
#: SLM may have gained another admin meanwhile, but a refusal is not worth a push every compare pass.
PERSON_COPY_REFUSED_RETRY_INTERVAL_S = env_int_clamped(
    "AUTOBOT_PERSON_COPY_REFUSED_RETRY_INTERVAL_S", 3600, min_v=60, max_v=7 * 24 * 3600
)

_COPY_PATH = "/api/internal/person-copy"
_LOCK_TTL_S = env_int_clamped("AUTOBOT_PERSON_COPY_LOCK_TTL_S", 60, min_v=10, max_v=600)
_LOCK_WAIT_S = env_int_clamped("AUTOBOT_PERSON_COPY_LOCK_WAIT_S", 15, min_v=1, max_v=120)
_LOCK_POLL_S = env_int_clamped("AUTOBOT_PERSON_COPY_LOCK_POLL_MS", 200, min_v=20, max_v=5000) / 1000
# The POST must end before the lock expires, or a second worker pushes while this one still sends.
_POST_TIMEOUT_S = max(1, _LOCK_TTL_S - max(5, _LOCK_TTL_S // 4))
_WATCHED_FIELDS = ("password_hash", "is_active", "deleted_at")
_CHANGED_KEY = "person_copy_changed_user_ids"
_background: set[asyncio.Task] = set()
_loop_task: asyncio.Task | None = None


class PersonCopyRefused(Exception):
    """The SLM refused the push: it would leave the SLM with no active platform admin (#21018).

    Not a transport failure, so the periodic pass repeats it only on the slow cadence of
    :data:`PERSON_COPY_REFUSED_RETRY_INTERVAL_S` (:func:`_due_link_ids`); the type name is the error shown on the
    link, which is how an admin sees why the SLM copy is still active. A transient lock failure on the SLM is a 503,
    not this: it is a transport failure and is retried every pass.
    """


async def _raise_if_refused(response) -> None:
    """Turn the SLM's last-platform-admin 409 into :class:`PersonCopyRefused`; other statuses are left alone."""
    if response.status != 409:
        return
    try:
        detail = (await response.json()).get("detail")
    except (ValueError, AttributeError):
        return
    if isinstance(detail, dict) and detail.get("code") == LAST_PLATFORM_ADMIN_CODE:
        raise PersonCopyRefused(LAST_PLATFORM_ADMIN_CODE)


async def _post_copy(slm_user_id: uuid.UUID, user: User) -> None:
    from services.slm_client import get_slm_client

    client = get_slm_client()
    if client is None:
        raise RuntimeError("SLM control link is not initialised")
    key = require_internal_key("a person's copy cannot be pushed to the SLM")
    session = await client._get_session()
    url = client._rest_url(_COPY_PATH)
    await assert_egress_policy(url)
    payload = {
        "slm_user_id": str(slm_user_id),
        "password_hash": user.password_hash,
        "is_active": login_refusal(user) is None,
    }
    headers = {"X-Internal-API-Key": key}
    async with session.post(
        url, json=payload, headers=headers, allow_redirects=False, timeout=ClientTimeout(total=_POST_TIMEOUT_S)
    ) as response:
        await _raise_if_refused(response)
        response.raise_for_status()


@asynccontextmanager
async def _person_lock(user_id: uuid.UUID) -> AsyncIterator[None]:
    """One push per person at a time, across workers. Raises TimeoutError if it can't be had.

    The row is read inside the lock, so a slower worker can't send an older hash over a newer one.
    """
    redis = await get_async_redis_client(database="main")
    if redis is None:
        raise TimeoutError("Redis is unavailable")
    key, token = f"person-copy:push:{user_id}", uuid.uuid4().hex
    deadline = time.monotonic() + _LOCK_WAIT_S
    while not await redis.set(key, token, nx=True, ex=_LOCK_TTL_S):
        if time.monotonic() >= deadline:
            raise TimeoutError("another push is still running")
        await asyncio.sleep(_LOCK_POLL_S)
    try:
        yield
    finally:
        await delete_if_value(redis, key, token)


async def _read_pair(session: AsyncSession, user_id: uuid.UUID) -> tuple[PersonLink, User] | None:
    query = (
        select(PersonLink, User)
        .join(User, User.id == PersonLink.user_id)
        .where(PersonLink.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    return (await session.execute(query)).first()


def _record(link: PersonLink, error: str | None) -> None:
    link.push_error = error
    now = datetime.now(timezone.utc)
    link.push_failed_at = (link.push_failed_at or now) if error else None
    if error == PersonCopyRefused.__name__:
        link.updated_at = now  # the time of this attempt: the refused-retry cadence counts from it


async def _push_person(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Push one person and record the outcome on their link. Only the error's type is kept."""
    settled = False  # the outcome is decided inside the lock; leaving it can't change it
    try:
        async with _person_lock(user_id):
            pair = await _read_pair(session, user_id)
            if pair is None:
                settled = True
                return
            await _post_copy(pair[0].slm_user_id, pair[1])
            _record(pair[0], None)
            await session.commit()  # inside the lock: the next pusher sees this outcome
            settled = True
        return
    except Exception as exc:
        if settled:  # the push and its record are done; only releasing the lock failed
            logger.warning("Could not release a person's push lock after a good push: %s", type(exc).__name__)
            return
        await session.rollback()
        logger.warning("Could not push a person's copy to the SLM: %s", type(exc).__name__)
        error = type(exc).__name__
    pair = await _read_pair(session, user_id)
    if pair is not None:
        _record(pair[0], error)
        await session.commit()


def _due_link_ids():
    """Linked people due a push: every link except one the SLM refused as last-platform-admin within the retry
    interval. A refused link is tried again once its last attempt is older than the interval, and a success clears
    the error (an explicit push after the person's own change always goes)."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=PERSON_COPY_REFUSED_RETRY_INTERVAL_S)
    return select(PersonLink.user_id).where(
        or_(
            PersonLink.push_error.is_(None),
            PersonLink.push_error != PersonCopyRefused.__name__,
            PersonLink.updated_at.is_(None),
            PersonLink.updated_at <= cutoff,
        )
    )


async def push_people(session: AsyncSession, user_ids: Iterable[uuid.UUID] | None = None) -> None:
    """Push the given linked people, or everyone linked (a refused link only after the retry interval)."""
    if user_ids is None:
        user_ids = (await session.execute(_due_link_ids())).scalars().all()
    for user_id in list(user_ids):
        await _push_person(session, user_id)


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
    # Longer than a pass's gap, so the worker holding it keeps it between passes.
    lease = LeaderLease("person-copy:compare", ttl_ms=PERSON_COPY_COMPARE_INTERVAL_S * 3000)
    while True:
        await asyncio.sleep(PERSON_COPY_COMPARE_INTERVAL_S)
        try:
            if await lease.update_leadership():  # one worker per pass
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
