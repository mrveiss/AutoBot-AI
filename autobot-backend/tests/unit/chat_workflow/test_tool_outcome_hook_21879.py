# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The AFTER_TOOL_EXECUTE hook carries the measured duration and the real outcome (#21879)."""

from __future__ import annotations

import asyncio
import logging

import pytest

from chat_workflow import llm_handler
from middleware.base import HookContext
from middleware.builtin.logging_extension import LoggingExtension

SESSION = "session-for-the-log-test"


class _RecordingManager:
    """Stands in for the extension manager; keeps the HookContext the AFTER hook received."""

    def __init__(self) -> None:
        self.after_ctx: HookContext | None = None

    async def invoke_hook(self, _point, _ctx):
        return []

    async def invoke_with_transform(self, _point, ctx, _key):
        self.after_ctx = ctx
        return None


@pytest.fixture
def manager(monkeypatch):
    fake = _RecordingManager()
    monkeypatch.setattr(llm_handler, "get_extension_manager", lambda: fake)
    return fake


async def _run_tool(manager, *, seconds: float, success: bool | None = True):
    assert await llm_handler._emit_before_tool_execute("web_search", {}, SESSION, tool_permission="x")
    await asyncio.sleep(seconds)
    await llm_handler._emit_after_tool_execute("web_search", "out", SESSION, {}, success=success)
    return manager.after_ctx


@pytest.mark.asyncio
async def test_a_slow_tool_reports_a_non_zero_measured_duration(manager):
    ctx = await _run_tool(manager, seconds=0.05)
    assert ctx.get("execution_time") >= 0.05
    assert ctx.get("success") is True


@pytest.mark.asyncio
async def test_a_call_with_no_start_mark_carries_no_duration(manager):
    await llm_handler._emit_after_tool_execute("never_started", "out", SESSION, {})
    assert manager.after_ctx.get("execution_time") is None
    assert manager.after_ctx.get("success") is None


def _log_line(caplog, ctx):
    ext = LoggingExtension()
    caplog.clear()
    with caplog.at_level(logging.INFO):
        asyncio.run(ext.on_after_tool_execute(ctx))
    return next(r.getMessage() for r in caplog.records if "Tool " in r.getMessage())


def test_the_log_line_shows_the_real_duration(caplog):
    line = _log_line(
        caplog, HookContext(session_id=SESSION, data={"tool_name": "t", "success": True, "execution_time": 20.7})
    )
    assert "SUCCESS (20.70s)" in line


def test_a_failing_tool_is_logged_as_failed(caplog):
    line = _log_line(
        caplog, HookContext(session_id=SESSION, data={"tool_name": "t", "success": False, "execution_time": 1.5})
    )
    assert "FAILED (1.50s)" in line


def test_a_missing_outcome_and_duration_say_so(caplog):
    line = _log_line(caplog, HookContext(session_id=SESSION, data={"tool_name": "t"}))
    assert "UNKNOWN (duration unknown)" in line
    assert "SUCCESS" not in line and "0.00s" not in line


class _LoggingManager(_RecordingManager):
    """An extension manager that runs the real LoggingExtension on the AFTER hook, as the registered one does."""

    async def invoke_with_transform(self, _point, ctx, _key):
        await LoggingExtension().on_after_tool_execute(ctx)
        return None


@pytest.fixture
def logging_manager(monkeypatch):
    fake = _LoggingManager()
    monkeypatch.setattr(llm_handler, "get_extension_manager", lambda: fake)
    return fake


def _tool_line(caplog) -> str:
    return next(r.getMessage() for r in caplog.records if "Tool web_search:" in r.getMessage())


@pytest.mark.asyncio
async def test_end_to_end_a_tool_with_a_known_duration_logs_a_non_zero_duration(logging_manager, caplog):
    with caplog.at_level(logging.INFO):
        await _run_tool(logging_manager, seconds=0.12, success=True)
    line = _tool_line(caplog)
    duration = float(line.rsplit("(", 1)[1].rstrip("s)"))
    assert "SUCCESS" in line and duration >= 0.12


@pytest.mark.asyncio
async def test_end_to_end_a_failing_tool_is_logged_as_failed(logging_manager, caplog):
    with caplog.at_level(logging.INFO):
        await _run_tool(logging_manager, seconds=0.02, success=False)
    line = _tool_line(caplog)
    duration = float(line.rsplit("(", 1)[1].rstrip("s)"))
    assert "FAILED" in line and "SUCCESS" not in line and duration > 0
