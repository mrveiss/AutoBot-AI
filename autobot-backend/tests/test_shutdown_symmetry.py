# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shutdown-symmetry unit tests (#11638).

Pins the new lifespan cleanup helpers: PostgreSQL engine disposal and
autonomous-loop task cancellation. Startup created these resources but
shutdown never released them.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest


class TestCloseDatabase:
    @pytest.mark.asyncio
    async def test_dispose_called_and_state_reset(self, monkeypatch):
        import user_management.database as db

        fake_engine = AsyncMock()
        monkeypatch.setattr(db, "_async_engine", fake_engine)
        monkeypatch.setattr(db, "_async_session_factory", object())

        await db.close_database()

        fake_engine.dispose.assert_awaited_once()
        assert db._async_engine is None
        assert db._async_session_factory is None

    @pytest.mark.asyncio
    async def test_noop_when_engine_never_created(self, monkeypatch):
        import user_management.database as db

        monkeypatch.setattr(db, "_async_engine", None)
        monkeypatch.setattr(db, "_async_session_factory", None)

        await db.close_database()  # must not raise

        assert db._async_engine is None


class TestStopAutonomousLoop:
    @pytest.mark.asyncio
    async def test_cancels_running_task(self, monkeypatch):
        import workflow_scheduler as ws

        async def _forever():
            while True:
                await asyncio.sleep(3600)

        task = asyncio.create_task(_forever())
        monkeypatch.setattr(ws, "_autonomous_loop_task", task)

        await ws.stop_autonomous_loop()

        assert task.cancelled()
        assert ws._autonomous_loop_task is None

    @pytest.mark.asyncio
    async def test_noop_when_never_started(self, monkeypatch):
        import workflow_scheduler as ws

        monkeypatch.setattr(ws, "_autonomous_loop_task", None)

        await ws.stop_autonomous_loop()  # must not raise

        assert ws._autonomous_loop_task is None
