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


async def test_a_successful_push_clears_an_earlier_failure() -> None:
    link, user = _pair(failed=datetime.now(timezone.utc))
    with patch.object(sync, "_post_copy", AsyncMock()):
        await sync._push_link(link, user)
    assert link.push_failed_at is None and link.push_error is None


async def test_a_failed_push_is_recorded_for_admins_without_the_message() -> None:
    link, user = _pair()
    with patch.object(sync, "_post_copy", AsyncMock(side_effect=ConnectionError("host detail"))):
        await sync._push_link(link, user)
    assert link.push_failed_at is not None and link.push_error == "ConnectionError"


async def test_a_retry_keeps_when_the_failure_began() -> None:
    began = datetime(2026, 1, 1, tzinfo=timezone.utc)
    link, user = _pair(failed=began)
    with patch.object(sync, "_post_copy", AsyncMock(side_effect=ConnectionError())):
        await sync._push_link(link, user)
    assert link.push_failed_at == began


async def test_one_failure_does_not_stop_the_others_and_all_is_committed() -> None:
    first, second = _pair(), _pair()
    session = MagicMock(commit=AsyncMock())
    session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[first, second])))
    with patch.object(sync, "_post_copy", AsyncMock(side_effect=[ConnectionError(), None])) as post:
        await sync.push_people(session)
    assert post.await_count == 2
    assert first[0].push_failed_at is not None and second[0].push_failed_at is None
    session.commit.assert_awaited_once()


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
    ):
        await sync._post_copy(link.slm_user_id, user)
    assert http.post.call_args.kwargs["json"]["is_active"] is False
