# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A heartbeat/event-sync timeout is an expected failure, not an unhandled error (#19461).

aiohttp's total timeout raises ``TimeoutError``, which is not a ``ClientError``;
it used to escape to the ``run()`` catch-all and read as an agent crash.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from slm.agent import agent as agent_mod
from slm.agent import event_buffer
from slm.agent.agent import SLMAgent


class _Post:
    """Async context manager standing in for ``session.post(...)``."""

    def __init__(self, exc: BaseException | None = None, status: int = 200):
        self._exc, self.status = exc, status

    async def __aenter__(self):
        if self._exc is not None:
            raise self._exc
        return self

    async def __aexit__(self, *_a):
        return False

    async def json(self):
        return {}

    async def text(self):
        return ""


class _Session:
    def __init__(self, exc: BaseException | None = None):
        self.exc, self.calls = exc, 0

    def post(self, *_a, **_k):
        self.calls += 1
        return _Post(self.exc)


def _agent(tmp_path, session) -> SLMAgent:
    agent = SLMAgent.__new__(SLMAgent)
    agent.admin_url, agent.node_id = "http://admin.invalid", "n1"
    agent.buffer_db = str(tmp_path / "events.db")
    agent._reg_backoff_seconds = 0
    agent._internal_api_key = "k"
    agent._session = session
    agent._process_heartbeat_response = lambda _d: None
    agent.buffer_event = lambda t, p: event_buffer.append(agent.buffer_db, t, p)
    event_buffer.initialize(agent.buffer_db)
    return agent


@pytest.mark.asyncio
async def test_heartbeat_timeout_is_a_warning_and_buffers_the_event(tmp_path, caplog):
    agent = _agent(tmp_path, _Session(TimeoutError()))
    with caplog.at_level(logging.DEBUG, logger=agent_mod.logger.name):
        assert await agent._send_heartbeat_request({"x": 1}) is False
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "Failed to send heartbeat" in warnings[0].getMessage()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(event_buffer.read_unsynced(agent.buffer_db)) == 1


@pytest.mark.asyncio
async def test_heartbeat_cancel_propagates(tmp_path):
    agent = _agent(tmp_path, _Session(asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await agent._send_heartbeat_request({"x": 1})
    assert event_buffer.read_unsynced(agent.buffer_db) == []


@pytest.mark.asyncio
async def test_successful_heartbeat_is_unchanged(tmp_path, caplog):
    agent = _agent(tmp_path, _Session())
    with caplog.at_level(logging.DEBUG, logger=agent_mod.logger.name):
        assert await agent._send_heartbeat_request({"x": 1}) is True
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert event_buffer.read_unsynced(agent.buffer_db) == []


@pytest.mark.asyncio
async def test_sync_timeout_is_a_warning_not_an_error(tmp_path, caplog):
    agent = _agent(tmp_path, _Session(TimeoutError()))
    event_buffer.append(agent.buffer_db, "boot", {"n": 1})
    with caplog.at_level(logging.DEBUG, logger=agent_mod.logger.name):
        await agent.sync_buffered_events()
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "Failed to sync events" in warnings[0].getMessage()
    assert len(event_buffer.read_unsynced(agent.buffer_db)) == 1


@pytest.mark.asyncio
async def test_sync_cancel_propagates(tmp_path):
    agent = _agent(tmp_path, _Session(asyncio.CancelledError()))
    event_buffer.append(agent.buffer_db, "boot", {"n": 1})
    with pytest.raises(asyncio.CancelledError):
        await agent.sync_buffered_events()


@pytest.mark.asyncio
async def test_run_loop_continues_after_a_timeout_without_the_catch_all(tmp_path, caplog, monkeypatch):
    session = _Session(TimeoutError())

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_a):
            return False

    monkeypatch.setattr(agent_mod.aiohttp, "ClientSession", lambda **_k: _CM())
    agent = _agent(tmp_path, None)
    agent.heartbeat_interval = 0
    agent.running = False
    agent._role_definitions_loaded = True
    agent.collector = type("C", (), {"collect": lambda self: {}})()
    agent.version_manager = type("V", (), {"get_version": lambda self: "v"})()
    agent.role_detector = None
    monkeypatch.setattr(agent_mod, "build_heartbeat_payload", lambda *a, **k: {"x": 1})
    sleeps = 0

    async def _sleep(_s):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            agent.running = False

    monkeypatch.setattr(agent_mod.asyncio, "sleep", _sleep)
    with caplog.at_level(logging.DEBUG, logger=agent_mod.logger.name):
        await agent.run()
    assert session.calls == 2  # the loop went round again after the timeout
    assert not [r for r in caplog.records if "Unhandled error" in r.getMessage()]
