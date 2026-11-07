# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#10200: a change reaches the SLM copy, and a failed delivery is visible and retried."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from user_management.services import person_copy_sync as sync


def _pair(failed=None):
    link = SimpleNamespace(slm_user_id=uuid.uuid4(), push_failed_at=failed, push_error="Old" if failed else None)
    user = SimpleNamespace(username="root", password_hash="h", is_active=True, deleted_at=None)
    return link, user


def _session_with(pairs: list) -> MagicMock:
    session = MagicMock(commit=AsyncMock(), rollback=AsyncMock())
    session.execute = AsyncMock(return_value=MagicMock(first=MagicMock(side_effect=pairs)))
    return session


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
        await sync._push_person(_session_with([pair]), uuid.uuid4())
    assert pair[0].push_failed_at is None and pair[0].push_error is None


async def test_a_failed_push_is_recorded_for_admins_without_the_message() -> None:
    pair = _pair()
    session = _session_with([pair, pair])
    with _no_lock(), patch.object(sync, "_post_copy", AsyncMock(side_effect=ConnectionError("host detail"))):
        await sync._push_person(session, uuid.uuid4())
    assert pair[0].push_failed_at is not None and pair[0].push_error == "ConnectionError"
    session.commit.assert_awaited_once()


async def test_a_retry_keeps_when_the_failure_began() -> None:
    began = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pair = _pair(failed=began)
    with _no_lock(), patch.object(sync, "_post_copy", AsyncMock(side_effect=ConnectionError())):
        await sync._push_person(_session_with([pair, pair]), uuid.uuid4())
    assert pair[0].push_failed_at == began


async def test_one_failure_does_not_stop_the_others() -> None:
    first, second = uuid.uuid4(), uuid.uuid4()
    push = AsyncMock()
    with patch.object(sync, "_push_person", push):
        await sync.push_people(MagicMock(), [first, second])
    assert [call.args[1] for call in push.await_args_list] == [first, second]


async def test_a_busy_lock_is_recorded_as_a_failure_and_sends_nothing() -> None:
    pair = _pair()
    redis = MagicMock(set=AsyncMock(return_value=None))
    with (
        patch.object(sync, "get_async_redis_client", AsyncMock(return_value=redis)),
        patch.object(sync, "_LOCK_WAIT_S", 0),
        patch.object(sync, "_post_copy", AsyncMock()) as post,
    ):
        await sync._push_person(_session_with([pair]), uuid.uuid4())
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
        await sync._push_person(_session_with([pair, pair]), uuid.uuid4())
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
        await sync._push_person(session, uuid.uuid4())
    assert (pair[0].push_error, pair[0].push_failed_at) == (None, None)
    session.rollback.assert_not_awaited()
    assert any("release" in r.message and "ConnectionError" in r.message for r in caplog.records)
