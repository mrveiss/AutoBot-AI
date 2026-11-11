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
