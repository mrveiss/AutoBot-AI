# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for skills_session_context() — GH#7441 session lifecycle standardization.

Verifies that the canonical context manager:
- commits on clean exit
- rolls back on exception without leaking the transaction
- always closes the session
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    """Session factory whose context manager yields mock_session."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_session)
    cm.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=cm)
    return factory


@pytest.mark.asyncio
async def test_commits_on_success(mock_session, mock_session_factory):
    with patch("skills.db._manager") as mock_manager:
        mock_manager.get_session_factory.return_value = mock_session_factory

        from skills.db import skills_session_context

        async with skills_session_context() as session:
            assert session is mock_session

        mock_session.commit.assert_awaited_once()
        mock_session.rollback.assert_not_awaited()
        mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_rolls_back_on_exception(mock_session, mock_session_factory):
    with patch("skills.db._manager") as mock_manager:
        mock_manager.get_session_factory.return_value = mock_session_factory

        from skills.db import skills_session_context

        with pytest.raises(ValueError, match="boom"):
            async with skills_session_context() as session:
                raise ValueError("boom")

        mock_session.commit.assert_not_awaited()
        mock_session.rollback.assert_awaited_once()
        mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_called_even_when_commit_raises(mock_session, mock_session_factory):
    mock_session.commit.side_effect = RuntimeError("commit failed")

    with patch("skills.db._manager") as mock_manager:
        mock_manager.get_session_factory.return_value = mock_session_factory

        from skills.db import skills_session_context

        with pytest.raises(RuntimeError, match="commit failed"):
            async with skills_session_context():
                pass

        mock_session.close.assert_awaited_once()
