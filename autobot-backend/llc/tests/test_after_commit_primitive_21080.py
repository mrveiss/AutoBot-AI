# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""``defer_until_commit``: runs once on commit, dropped by an outer or SAVEPOINT rollback (#21080)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from llc.services.after_commit import after_commit_tasks, defer_until_commit
from testkit.fake_async_session import FakeAsyncSession


@pytest.fixture
def session():  # noqa: ANN201
    engine = create_engine("sqlite://")  # canonical: ignore py-adhoc-db-engine (test-local engine)
    sync = Session(engine)
    sync.execute(text("SELECT 1"))  # opens the transaction, as the SELECT before a write does
    yield SimpleNamespace(sync_session=sync)
    sync.close()
    engine.dispose()


def test_commit_runs_the_callback_once(session) -> None:  # noqa: ANN001
    callback = MagicMock()
    defer_until_commit(session, callback)
    callback.assert_not_called()
    session.sync_session.commit()
    session.sync_session.execute(text("SELECT 1"))
    session.sync_session.commit()
    callback.assert_called_once()


def test_outer_rollback_drops_the_callback(session) -> None:  # noqa: ANN001
    callback = MagicMock()
    defer_until_commit(session, callback)
    session.sync_session.rollback()
    session.sync_session.commit()
    callback.assert_not_called()


def test_savepoint_rollback_drops_only_its_own_callbacks(session) -> None:  # noqa: ANN001
    outer, inner = MagicMock(), MagicMock()
    defer_until_commit(session, outer)
    nested = session.sync_session.begin_nested()
    defer_until_commit(session, inner)
    nested.rollback()
    session.sync_session.commit()
    outer.assert_called_once()
    inner.assert_not_called()


def test_a_released_savepoint_waits_for_the_outer_commit(session) -> None:  # noqa: ANN001
    callback = MagicMock()
    nested = session.sync_session.begin_nested()
    defer_until_commit(session, callback)
    nested.commit()
    callback.assert_not_called()
    session.sync_session.commit()
    callback.assert_called_once()


def test_a_failing_callback_is_logged_not_raised(session, caplog) -> None:  # noqa: ANN001
    defer_until_commit(session, MagicMock(side_effect=RuntimeError("boom")), "the probe")
    session.sync_session.commit()
    assert "the probe failed" in caplog.text


async def test_a_coroutine_callback_runs_as_a_task_after_commit(session) -> None:  # noqa: ANN001
    ran = []

    async def callback() -> None:
        ran.append(1)

    defer_until_commit(session, callback)
    assert ran == []
    session.sync_session.commit()
    await asyncio.gather(*after_commit_tasks)
    assert ran == [1]


async def test_a_non_real_session_runs_the_callback_at_once() -> None:
    ran = []

    async def callback() -> None:
        ran.append(1)

    task = defer_until_commit(FakeAsyncSession(), callback)
    await task
    sync_ran = MagicMock()
    assert defer_until_commit(FakeAsyncSession(), sync_ran) is None
    assert ran == [1]
    sync_ran.assert_called_once()


def test_a_plain_callback_has_run_when_commit_returns(session) -> None:  # noqa: ANN001
    """A sync callback runs inside the hook (no task), so the work has started once ``commit()`` returns (#21107)."""
    ran: list[int] = []
    defer_until_commit(session, lambda: ran.append(1))
    session.sync_session.commit()
    assert ran == [1]


def test_still_valid_false_at_commit_skips_the_callback(session) -> None:  # noqa: ANN001
    alive = {"yes": True}
    kept, skipped = MagicMock(), MagicMock()
    defer_until_commit(session, kept, still_valid=lambda: True)
    defer_until_commit(session, skipped, still_valid=lambda: alive["yes"])
    alive["yes"] = False
    session.sync_session.commit()
    kept.assert_called_once()
    skipped.assert_not_called()


def test_still_valid_false_at_a_savepoint_rollback_drops_an_outer_callback(session) -> None:  # noqa: ANN001
    """The SAVEPOINT rollback does not undo the outer callback, so only ``still_valid`` can drop it."""
    alive = {"yes": True}
    callback = MagicMock()
    defer_until_commit(session, callback, still_valid=lambda: alive["yes"])
    nested = session.sync_session.begin_nested()
    alive["yes"] = False
    nested.rollback()
    alive["yes"] = True
    session.sync_session.commit()
    callback.assert_not_called()


def test_a_raising_still_valid_is_logged_and_the_other_callbacks_still_run(session, caplog) -> None:  # noqa: ANN001
    after = MagicMock()
    defer_until_commit(session, MagicMock(), "the probe", still_valid=MagicMock(side_effect=RuntimeError("boom")))
    defer_until_commit(session, after)
    session.sync_session.commit()
    after.assert_called_once()
    assert "still_valid check for the probe failed" in caplog.text


def test_a_callback_queued_before_the_first_statement_is_dropped_by_the_rollback() -> None:
    engine = create_engine("sqlite://")  # canonical: ignore py-adhoc-db-engine (test-local engine)
    sync = Session(engine)
    fresh = SimpleNamespace(sync_session=sync)
    callback = MagicMock()
    defer_until_commit(fresh, callback)  # no transaction has begun yet
    sync.execute(text("SELECT 1"))
    sync.rollback()
    sync.execute(text("SELECT 1"))
    sync.commit()
    callback.assert_not_called()
    sync.close()
    engine.dispose()
