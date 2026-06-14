# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the shared SubprocessLifecycleAdapter base (GH#9834).

Lifecycle behaviour shared by all SubprocessLifecycleAdapter subclasses
(status, cancel, timeout) lives here so that each concrete adapter test file
only carries adapter-specific assertions (command assembly, env, CLI flags).
Duplicate sets removed from test_claude_code_adapter.py and
test_copilot_local_adapter.py as part of GH#9844.
"""

import json
import os
import signal
import tempfile
import time
from unittest.mock import AsyncMock, patch

import pytest

from llc.adapters.subprocess_base import (
    ADAPTER_TIMEOUT_SECONDS,
    SIGTERM_GRACE_SECONDS,
    SubprocessLifecycleAdapter,
    resolve_timeout,
)
from llc.models.enums import LLCRunStatus

# ---------------------------------------------------------------------------
# Minimal concrete adapter for exercising base-class paths
# ---------------------------------------------------------------------------


def _state_path(output_dir: str, run_id: str) -> str:
    return os.path.join(output_dir, f"base_state_{run_id.replace('/', '_')}.json")


class _DummyAdapter(SubprocessLifecycleAdapter):
    _LOG_NAME = "DummyAdapter"
    _state_path = staticmethod(_state_path)

    async def _invoke(self, agent_config, context):  # pragma: no cover - not exercised
        return "1/x"


# ---------------------------------------------------------------------------
# resolve_timeout — 3-tier hierarchy
# ---------------------------------------------------------------------------


class TestResolveTimeout:
    def test_per_agent_override(self, monkeypatch) -> None:
        monkeypatch.setenv("LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS", "250")
        assert resolve_timeout({"timeout_seconds": 500}) == 500

    def test_global_env(self, monkeypatch) -> None:
        monkeypatch.setenv("LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS", "180")
        assert resolve_timeout({}) == 180

    def test_adapter_default(self, monkeypatch) -> None:
        monkeypatch.delenv("LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS", raising=False)
        assert resolve_timeout({}) == ADAPTER_TIMEOUT_SECONDS == 3600

    def test_precedence_order_all_three_tiers(self, monkeypatch) -> None:
        """Verify precedence: per-agent > global env > adapter default."""
        monkeypatch.setenv("LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS", "200")

        assert resolve_timeout({"timeout_seconds": 100}) == 100
        assert resolve_timeout({}) == 200

        monkeypatch.delenv("LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS")
        assert resolve_timeout({}) == 3600


# ---------------------------------------------------------------------------
# _load_state path-traversal guard
# ---------------------------------------------------------------------------


class TestLoadStatePathTraversal:
    def test_rejects_outside_safe_dir(self) -> None:
        # A path escaping safe_dir must be refused (returns None), not read.
        assert SubprocessLifecycleAdapter._load_state("/etc/passwd", "/tmp") is None

    def test_reads_valid_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "s.json")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump({"pid": 1}, fh)
            assert SubprocessLifecycleAdapter._load_state(p, td) == {"pid": 1}


# ---------------------------------------------------------------------------
# Shared status() behaviour (inherited by all SubprocessLifecycleAdapter subclasses)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSharedStatus:
    async def test_running_pid_returns_running(self) -> None:
        with patch("os.kill", return_value=None):
            result = await _DummyAdapter().status({"adapter_config": {}}, "1234/session-abc")
        assert result.status == LLCRunStatus.RUNNING

    async def test_dead_pid_returns_completed(self) -> None:
        with patch("os.kill", side_effect=ProcessLookupError):
            result = await _DummyAdapter().status({"adapter_config": {}}, "9999/session-abc")
        assert result.status == LLCRunStatus.COMPLETED

    async def test_timeout_triggers_cancel_and_returns_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_id = "1111/session-xyz"
            state_file = _state_path(td, run_id)
            state = {
                "pid": 1111,
                "session_id": "session-xyz",
                "agent_id": "a1",
                "started_at": time.time() - 9999,
                "timeout_seconds": 10,
            }
            with open(state_file, "w") as fh:
                json.dump(state, fh)

            cancel_called = []

            adapter = _DummyAdapter()

            async def fake_cancel(agent_config, run_id):
                cancel_called.append(run_id)

            adapter.cancel = fake_cancel  # type: ignore[assignment]
            result = await adapter.status({"adapter_config": {"output_dir": td}}, run_id)

        assert result.status == LLCRunStatus.TIMEOUT
        assert run_id in cancel_called

    async def test_unparseable_run_id_returns_failed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = await _DummyAdapter().status({"adapter_config": {"output_dir": td}}, "not-a-valid-run-id")
        assert result.status == LLCRunStatus.FAILED

    async def test_exception_in_probe_returns_failed(self) -> None:
        with patch("os.kill", side_effect=OSError("unexpected")):
            result = await _DummyAdapter().status({"adapter_config": {}}, "1234/session-abc")
        assert result.status == LLCRunStatus.FAILED

    # The following two tests are retained from the original TestSharedLifecycle class
    # (were already in this file before GH#9844 — preserved verbatim).
    async def test_status_unparseable_run_id(self) -> None:
        # No state file + non-numeric pid → FAILED via the shared base path.
        with tempfile.TemporaryDirectory() as td:
            result = await _DummyAdapter().status({"adapter_config": {"output_dir": td}}, "notapid/x")
        assert result.status == LLCRunStatus.FAILED

    async def test_status_completed_when_pid_gone(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            # No state file; run_id pid is an almost-certainly-dead PID.
            result = await _DummyAdapter().status({"adapter_config": {"output_dir": td}}, "2147483646/x")
        assert result.status in (LLCRunStatus.COMPLETED, LLCRunStatus.RUNNING)


# ---------------------------------------------------------------------------
# Graceful SIGTERM + SIGKILL with 10s grace period
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSharedGracefulTimeout:
    """Tests for base-class cancel() SIGTERM→SIGKILL grace-period logic.

    Both ClaudeCodeAdapter and CopilotLocalAdapter inherit cancel() unchanged
    from SubprocessLifecycleAdapter, so these tests belong here rather than
    being duplicated in each adapter's test file.
    """

    async def test_grace_period_constant_is_10_seconds(self) -> None:
        """SIGTERM_GRACE_SECONDS == 10 (per MVA-2940 ADR)."""
        assert SIGTERM_GRACE_SECONDS == 10

    async def test_cancel_sends_sigterm_then_sigkill_after_grace(self) -> None:
        """cancel() sends SIGTERM, polls 10s, then sends SIGKILL."""
        adapter = _DummyAdapter()
        kill_signals = []

        def fake_kill(pid, sig):
            kill_signals.append((pid, sig))
            if sig == signal.SIGKILL:
                raise ProcessLookupError()

        with tempfile.TemporaryDirectory() as td:
            state_file = _state_path(td, "123/session-x")
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, "w") as f:
                json.dump({"pid": 123, "session_id": "session-x"}, f)

            with (
                patch("os.kill", side_effect=fake_kill),
                patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            ):
                await adapter.cancel({"adapter_config": {"output_dir": td}}, "123/session-x")

        assert kill_signals[0] == (123, signal.SIGTERM)
        assert mock_sleep.await_count == SIGTERM_GRACE_SECONDS * 10
        assert (123, signal.SIGKILL) in kill_signals
