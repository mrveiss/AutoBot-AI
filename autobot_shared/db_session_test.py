# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Commit/rollback/callback ordering of the canonical session scopes (#15068)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared import db_session
from autobot_shared.db_session import POST_COMMIT_CALLBACKS, PostCommitCallbackError, async_session_scope, session_scope


def _maker(session: MagicMock) -> MagicMock:
    maker = MagicMock()
    maker.return_value.__aenter__ = AsyncMock(return_value=session)
    maker.return_value.__aexit__ = AsyncMock(return_value=False)
    return maker


def _session() -> MagicMock:
    session = MagicMock()
    session.info = {}
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


async def test_a_failing_callback_neither_rolls_back_nor_stops_the_rest() -> None:
    session, ran = _session(), []

    async def boom() -> None:
        ran.append("first")
        raise ValueError("first failed")

    async def ok() -> None:
        ran.append("second")

    with pytest.raises(PostCommitCallbackError) as caught:
        async with async_session_scope(_maker(session)) as s:
            s.info[POST_COMMIT_CALLBACKS] += [boom, ok]
    assert ran == ["first", "second"]
    session.commit.assert_awaited_once()
    session.rollback.assert_not_called()
    assert [type(e) for e in caught.value.errors] == [ValueError]


async def test_a_failing_rollback_does_not_mask_the_original_error() -> None:
    session = _session()
    session.rollback = AsyncMock(side_effect=RuntimeError("rollback failed"))
    with patch.object(db_session, "logger") as log:
        with pytest.raises(ValueError, match="body"):
            async with async_session_scope(_maker(session)):
                raise ValueError("body")
    log.error.assert_called_once()


async def test_a_failed_commit_rolls_back_and_runs_no_callbacks() -> None:
    session, ran = _session(), []
    session.commit = AsyncMock(side_effect=ValueError("commit failed"))

    async def cb() -> None:
        ran.append(1)

    with pytest.raises(ValueError):
        async with async_session_scope(_maker(session)) as s:
            s.info[POST_COMMIT_CALLBACKS].append(cb)
    session.rollback.assert_awaited_once()
    assert ran == []


def test_sync_scope_failing_rollback_does_not_mask_the_original_error() -> None:
    session = MagicMock()
    session.rollback.side_effect = RuntimeError("rollback failed")
    with patch.object(db_session, "logger") as log:
        with pytest.raises(ValueError, match="body"):
            with session_scope(lambda: session):
                raise ValueError("body")
    log.error.assert_called_once()
    session.close.assert_called_once()
