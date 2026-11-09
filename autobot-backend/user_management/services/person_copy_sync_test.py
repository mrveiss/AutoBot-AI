# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#10200: a change reaches the SLM copy, and a failed delivery is visible and retried."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from testkit.fake_async_session import FakeAsyncSession, FakeResult
from user_management.models.person_link import PersonLink
from user_management.services import person_copy_sync as sync

_USER_ID = uuid.UUID(int=1)


def _pair(failed=None):
    link = SimpleNamespace(slm_user_id=uuid.UUID(int=3), push_failed_at=failed, push_error="Old" if failed else None)
    user = SimpleNamespace(username="root", password_hash="h", is_active=True, deleted_at=None)
    return link, user


def _session_with(pairs: list) -> FakeAsyncSession:
    """One queued ``(link, user)`` row per ``_read_pair`` the push will make."""
    return FakeAsyncSession(results=[FakeResult([pair]) for pair in pairs], strict=True)


def _no_lock():
    return patch.object(sync, "_person_lock", MagicMock(return_value=_Unlocked()))


class _Unlocked:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


async def test_a_successful_push_clears_an_earlier_failure() -> None:
    pair = _pair(failed=datetime.now(timezone.utc))
    with _no_lock(), patch.object(sync, "_post_copy", AsyncMock()):
        await sync._push_person(_session_with([pair]), _USER_ID)
    assert pair[0].push_failed_at is None and pair[0].push_error is None


async def test_a_failed_push_is_recorded_for_admins_without_the_message() -> None:
    pair = _pair()
    session = _session_with([pair, pair])
    with _no_lock(), patch.object(sync, "_post_copy", AsyncMock(side_effect=ConnectionError("host detail"))):
        await sync._push_person(session, _USER_ID)
    assert pair[0].push_failed_at is not None and pair[0].push_error == "ConnectionError"
    assert session.commits == 1


async def test_a_retry_keeps_when_the_failure_began() -> None:
    began = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pair = _pair(failed=began)
    with _no_lock(), patch.object(sync, "_post_copy", AsyncMock(side_effect=ConnectionError())):
        await sync._push_person(_session_with([pair, pair]), _USER_ID)
    assert pair[0].push_failed_at == began


async def test_one_failure_does_not_stop_the_others() -> None:
    first, second = _pair(), _pair()
    post = AsyncMock(side_effect=[ConnectionError(), None])
    session = _session_with([first, first, second])
    with _no_lock(), patch.object(sync, "_post_copy", post):
        await sync.push_people(session, [_USER_ID, uuid.UUID(int=2)])
    assert post.await_count == 2
    assert first[0].push_error == "ConnectionError" and first[0].push_failed_at is not None
    assert second[0].push_error is None and second[0].push_failed_at is None


def test_the_post_timeout_is_below_the_lock_ttl() -> None:
    assert 0 < sync._POST_TIMEOUT_S < sync._LOCK_TTL_S


async def test_a_busy_lock_is_recorded_as_a_failure_and_sends_nothing() -> None:
    pair = _pair()
    redis = MagicMock(set=AsyncMock(return_value=None))
    with (
        patch.object(sync, "get_async_redis_client", AsyncMock(return_value=redis)),
        patch.object(sync, "_LOCK_WAIT_S", 0),
        patch.object(sync, "_post_copy", AsyncMock()) as post,
    ):
        await sync._push_person(_session_with([pair]), _USER_ID)
    post.assert_not_awaited()
    assert pair[0].push_error == "TimeoutError"


async def test_a_deleted_user_reaches_the_slm_as_inactive() -> None:
    link, user = _pair()
    user.deleted_at = datetime.now(timezone.utc)
    response = MagicMock(raise_for_status=MagicMock())
    context = MagicMock(__aenter__=AsyncMock(return_value=response), __aexit__=AsyncMock(return_value=False))
    http = MagicMock(post=MagicMock(return_value=context))
    client = MagicMock(_get_session=AsyncMock(return_value=http), _rest_url=lambda path: f"http://slm{path}")
    with (
        patch("services.slm_client.get_slm_client", return_value=client),
        patch.object(sync, "assert_egress_policy", AsyncMock()),
        patch("user_management.services.person_link_service.internal_api_key", return_value="k"),
    ):
        await sync._post_copy(link.slm_user_id, user)
    assert http.post.call_args.kwargs["json"]["is_active"] is False
    assert http.post.call_args.kwargs["headers"] == {"X-Internal-API-Key": "k"}


async def test_an_unset_internal_key_sends_nothing_and_is_recorded_as_a_failure(caplog) -> None:
    pair = _pair()
    http = MagicMock(post=MagicMock())
    client = MagicMock(_get_session=AsyncMock(return_value=http), _rest_url=lambda path: f"http://slm{path}")
    with (
        _no_lock(),
        patch("services.slm_client.get_slm_client", return_value=client),
        patch.object(sync, "assert_egress_policy", AsyncMock()),
        patch("user_management.services.person_link_service.internal_api_key", return_value=""),
        caplog.at_level("ERROR"),
    ):
        await sync._push_person(_session_with([pair, pair]), _USER_ID)
    http.post.assert_not_called()
    assert pair[0].push_error == "FirstAdminLinkError"
    assert any(r.levelname == "ERROR" and "no internal API key" in r.message for r in caplog.records)


class _ReleaseFails(_Unlocked):
    async def __aexit__(self, *exc):
        raise ConnectionError("release")


async def test_a_release_error_after_a_good_push_keeps_the_success(caplog) -> None:
    pair = _pair(failed=datetime.now(timezone.utc))
    session = _session_with([pair])
    with (
        patch.object(sync, "_person_lock", MagicMock(return_value=_ReleaseFails())),
        patch.object(sync, "_post_copy", AsyncMock()),
        caplog.at_level("WARNING"),
    ):
        await sync._push_person(session, _USER_ID)
    assert (pair[0].push_error, pair[0].push_failed_at) == (None, None)
    assert session.rollbacks == 0
    assert any("release" in r.message and "ConnectionError" in r.message for r in caplog.records)


def _response(status: int, body):
    async def json():
        if isinstance(body, Exception):
            raise body
        return body

    return SimpleNamespace(status=status, json=json)


async def test_the_slms_last_admin_refusal_is_recognised() -> None:
    refusal = {"detail": {"code": "last_platform_admin", "message": "m"}}
    with pytest.raises(sync.PersonCopyRefused):
        await sync._raise_if_refused(_response(409, refusal))


async def test_other_409s_and_other_statuses_are_left_to_raise_for_status() -> None:
    await sync._raise_if_refused(_response(409, {"detail": {"code": "something_else"}}))
    await sync._raise_if_refused(_response(409, {"detail": "text"}))
    await sync._raise_if_refused(_response(409, ValueError("not json")))
    await sync._raise_if_refused(_response(500, {"detail": {"code": "last_platform_admin"}}))


async def test_a_refused_push_is_shown_on_the_link_and_stamps_the_attempt() -> None:
    pair = _pair()
    with _no_lock(), patch.object(sync, "_post_copy", AsyncMock(side_effect=sync.PersonCopyRefused("x"))):
        await sync._push_person(_session_with([pair, pair]), _USER_ID)
    assert pair[0].push_error == "PersonCopyRefused" and pair[0].push_failed_at is not None
    assert pair[0].updated_at is not None  # the refused-retry cadence counts from this attempt


async def test_a_refused_link_is_skipped_inside_the_interval_and_retried_after_it(tmp_path) -> None:
    """The real due-query on a real table: only a refused link attempted within the interval is left out."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'links.db'}")  # canonical: ignore py-adhoc-db-engine
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: PersonLink.__table__.create(sync_conn))
    now = datetime.now(timezone.utc)
    interval = sync.PERSON_COPY_REFUSED_RETRY_INTERVAL_S
    rows = {  # name: (push_error, seconds since the last attempt)
        "never_failed": (None, 0),
        "transport_failure": ("ConnectionError", 0),
        "refused_inside_interval": ("PersonCopyRefused", interval - 60),
        "refused_after_interval": ("PersonCopyRefused", interval + 60),
    }
    ids = {name: uuid.uuid4() for name in rows}
    async with AsyncSession(engine) as session:
        for name, (error, age) in rows.items():
            session.add(
                PersonLink(
                    user_id=ids[name],
                    slm_user_id=uuid.uuid4(),
                    push_error=error,
                    updated_at=now - timedelta(seconds=age),
                )
            )
        await session.commit()
        due = set((await session.execute(sync._due_link_ids())).scalars().all())
    await engine.dispose()
    assert {name for name, user_id in ids.items() if user_id in due} == {
        "never_failed",
        "transport_failure",
        "refused_after_interval",
    }


async def test_after_another_admin_exists_the_retry_succeeds_and_clears_the_refusal() -> None:
    pair = _pair()
    pair[0].push_error, pair[0].push_failed_at = "PersonCopyRefused", datetime.now(timezone.utc)
    with _no_lock(), patch.object(sync, "_post_copy", AsyncMock()):
        await sync._push_person(_session_with([pair]), _USER_ID)
    assert pair[0].push_error is None and pair[0].push_failed_at is None


async def test_a_transient_lock_failure_503_is_a_transport_failure_never_a_refusal() -> None:
    import aiohttp

    pair = _pair()
    busy = aiohttp.ClientResponseError(MagicMock(), (), status=503)
    with _no_lock(), patch.object(sync, "_post_copy", AsyncMock(side_effect=busy)):
        await sync._push_person(_session_with([pair, pair]), _USER_ID)
    assert pair[0].push_error == "ClientResponseError"
    await sync._raise_if_refused(_response(503, {"detail": {"code": "last_platform_admin_retry"}}))


async def test_the_periodic_pass_selects_the_due_links() -> None:
    session = FakeAsyncSession(results=[FakeResult([_USER_ID])], strict=False)
    session.execute = AsyncMock(return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [])))
    await sync.push_people(session)
    statement = session.execute.await_args.args[0]
    assert "push_error" in str(statement)
