# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20030: an unowned session goes to ONE first writer; user rows are locked by assignment and removal."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql

from security.session_owner_claim import take_or_refresh
from services.chat_session_owner_action import active_user_id


def _validator(set_result, winner=None) -> SimpleNamespace:
    return SimpleNamespace(
        redis=SimpleNamespace(set=AsyncMock(return_value=set_result)),
        get_session_owner=AsyncMock(return_value=winner),
        _get_ownership_key=lambda sid: f"key:{sid}",
        ownership_ttl=60,
    )


async def test_the_first_writer_takes_an_unowned_session_atomically() -> None:
    v = _validator(True)
    assert await take_or_refresh(v, "s1", None, "alice", False) is True
    v.redis.set.assert_awaited_once_with("key:s1", "alice", nx=True, ex=60)


async def test_a_second_writer_that_lost_the_race_is_refused() -> None:
    v = _validator(False, winner="bob")
    assert await take_or_refresh(v, "s1", None, "alice", False) is False
    v.redis.set.assert_awaited_once()


async def test_the_owner_refreshes_and_a_forced_transfer_still_writes() -> None:
    v = _validator(True)
    assert await take_or_refresh(v, "s1", "alice", "alice", False) is True
    assert v.redis.set.await_args.kwargs == {"ex": 60}
    lost = _validator(False, winner="bob")
    assert await take_or_refresh(lost, "s1", None, "alice", True) is True


async def test_a_redis_failure_raises_rather_than_reading_as_free() -> None:
    v = _validator(True)
    v.redis.set = AsyncMock(side_effect=ConnectionError())
    try:
        await take_or_refresh(v, "s1", None, "alice", False)
    except ConnectionError:
        return
    raise AssertionError("a failure to check must not read as free")


async def test_the_assignment_locks_the_user_row_and_the_proposal_does_not() -> None:
    session = MagicMock()
    found = MagicMock()
    found.scalars.return_value.first.return_value = None
    session.execute = AsyncMock(return_value=found)
    await active_user_id(session, "alice", lock=True)
    await active_user_id(session, "alice")
    locked, plain = (str(c.args[0].compile(dialect=postgresql.dialect())) for c in session.execute.await_args_list)
    assert "FOR UPDATE" in locked and "FOR UPDATE" not in plain
