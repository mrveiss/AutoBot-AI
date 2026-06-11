# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for rate-limit detection + backoff recovery for registry adapters (GH#9773).

Covers:
  1. is_rate_limit_output detects known rate-limit markers.
  2. is_rate_limit_output is conservative — plain failures are NOT classified.
  3. ClaudeCodeAdapter._status returns RATE_LIMITED when output contains markers.
  4. ClaudeCodeAdapter._status returns COMPLETED when output is clean.
  5. _dispatch_registry_adapter raises ProviderRateLimited on RATE_LIMITED status.
  6. _dispatch_registry_adapter raises AdapterRunFailed on plain FAILED status.
  7. _run_adapter applies backoff when ProviderRateLimited is raised by a registry
     adapter (end-to-end: RATE_LIMITED status -> ProviderRateLimited -> backoff).
"""

import json
import os
import tempfile
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.adapters.base import AdapterRunStatus
from llc.adapters.subprocess_support import is_rate_limit_output
from llc.exceptions import AdapterRunFailed, ProviderRateLimited
from llc.models.enums import LLCRunStatus
from llc.scheduler.heartbeat_scheduler import (
    HeartbeatScheduler,
    _dispatch_registry_adapter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMPANY_UUID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_AGENT_ID = "agent-rl-registry-test"
_RUN_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def _make_agent(**kwargs):
    defaults = {
        "agent_id": _AGENT_ID,
        "company_id": _COMPANY_UUID,
        "name": "Registry RL Test Agent",
        "heartbeat_cron": "*/5 * * * *",
        "heartbeat_enabled": True,
        "adapter_type": "claude_code",
        "adapter_config": {"output_dir": "/tmp"},
        "context_mode": "thin",
    }
    defaults.update(kwargs)
    return defaults


def _make_adapter_returning(status: LLCRunStatus) -> MagicMock:
    """Return a mock LLCAdapter whose status() immediately returns *status* (terminal)."""
    adapter = MagicMock()
    adapter.invoke = AsyncMock(return_value="fake-run-id")
    adapter.status = AsyncMock(
        return_value=AdapterRunStatus(status=status, error="test" if status == LLCRunStatus.FAILED else None)
    )
    adapter.cancel = AsyncMock()
    return adapter


def _make_redis():
    redis = AsyncMock()
    redis.zadd = AsyncMock(return_value=1)
    redis.zscore = AsyncMock(return_value=None)
    return redis


# ---------------------------------------------------------------------------
# 1–2. is_rate_limit_output detection
# ---------------------------------------------------------------------------


class TestIsRateLimitOutput:
    def test_detects_rate_limit_error(self):
        assert is_rate_limit_output("Error: rate_limit_error — too many tokens")

    def test_detects_429(self):
        assert is_rate_limit_output('{"type": "error", "error": {"status": 429}}')

    def test_detects_overloaded(self):
        assert is_rate_limit_output("API is overloaded, please retry later")

    def test_detects_quota(self):
        assert is_rate_limit_output("Monthly quota exceeded for this account")

    def test_detects_too_many_requests(self):
        assert is_rate_limit_output("Too many requests — slow down")

    def test_detects_529(self):
        assert is_rate_limit_output("HTTP 529 returned by API")

    def test_does_not_classify_clean_success(self):
        assert not is_rate_limit_output('{"type": "result", "result": "Task completed successfully."}')

    def test_does_not_classify_generic_error(self):
        assert not is_rate_limit_output("subprocess exited with code 1: unknown error")

    def test_none_input_returns_false(self):
        assert not is_rate_limit_output(None)

    def test_empty_string_returns_false(self):
        assert not is_rate_limit_output("")

    def test_case_insensitive(self):
        assert is_rate_limit_output("RATE LIMIT EXCEEDED")
        assert is_rate_limit_output("Rate_Limit_Error")


# ---------------------------------------------------------------------------
# 3–4. ClaudeCodeAdapter._status rate-limit detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestClaudeCodeAdapterStatusRateLimit:
    async def test_returns_rate_limited_when_output_has_markers(self):
        import time as _time

        from llc.adapters.claude_code_adapter import ClaudeCodeAdapter, _state_path

        adapter = ClaudeCodeAdapter()

        with tempfile.TemporaryDirectory() as td:
            run_id = "1234/session-rl"
            output_file = os.path.join(td, f"llc_agent_agent-1_{run_id.replace('/', '_')}.jsonl")

            # Write rate-limit content to output file
            with open(output_file, "w", encoding="utf-8") as fh:
                fh.write('{"type": "error", "error": {"message": "rate_limit_error"}}\n')

            # Write state file referencing output_file; started_at is recent so
            # the base _status() does not trigger the timeout path before probe_pid.
            state = {
                "pid": 1234,
                "session_id": "session-rl",
                "agent_id": "agent-1",
                "output_file": output_file,
                "started_at": _time.time(),
                "timeout_seconds": 3600,
            }
            with open(_state_path(td, run_id), "w", encoding="utf-8") as fh:
                json.dump(state, fh)

            cfg = {"agent_id": "agent-1", "adapter_config": {"output_dir": td}}

            with patch("os.kill", side_effect=ProcessLookupError()):
                result = await adapter._status(cfg, run_id)

        assert result.status == LLCRunStatus.RATE_LIMITED
        assert result.error is not None
        assert "rate-limited" in result.error

    async def test_returns_completed_when_output_is_clean(self):
        import time as _time

        from llc.adapters.claude_code_adapter import ClaudeCodeAdapter, _state_path

        adapter = ClaudeCodeAdapter()

        with tempfile.TemporaryDirectory() as td:
            run_id = "5678/session-ok"
            output_file = os.path.join(td, f"llc_agent_agent-2_{run_id.replace('/', '_')}.jsonl")

            with open(output_file, "w", encoding="utf-8") as fh:
                fh.write('{"type": "result", "subtype": "success"}\n')

            state = {
                "pid": 5678,
                "session_id": "session-ok",
                "agent_id": "agent-2",
                "output_file": output_file,
                "started_at": _time.time(),
                "timeout_seconds": 3600,
            }
            with open(_state_path(td, run_id), "w", encoding="utf-8") as fh:
                json.dump(state, fh)

            cfg = {"agent_id": "agent-2", "adapter_config": {"output_dir": td}}

            with patch("os.kill", side_effect=ProcessLookupError()):
                result = await adapter._status(cfg, run_id)

        assert result.status == LLCRunStatus.COMPLETED

    async def test_running_pid_not_reclassified(self):
        from llc.adapters.claude_code_adapter import ClaudeCodeAdapter

        adapter = ClaudeCodeAdapter()
        cfg = {"agent_id": "agent-3", "adapter_config": {}}

        with patch("os.kill", return_value=None):  # PID alive
            result = await adapter._status(cfg, "9999/session-run")

        assert result.status == LLCRunStatus.RUNNING


# ---------------------------------------------------------------------------
# 5–6. _dispatch_registry_adapter: RATE_LIMITED → ProviderRateLimited
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDispatchRegistryAdapterRateLimitTranslation:
    async def test_rate_limited_status_raises_provider_rate_limited(self):
        """RATE_LIMITED terminal status must raise ProviderRateLimited (not AdapterRunFailed)."""
        agent = _make_agent()
        adapter = _make_adapter_returning(LLCRunStatus.RATE_LIMITED)

        with (
            patch("llc.scheduler.heartbeat_scheduler._issue_run_key", AsyncMock(return_value=(None, None))),
            patch("llc.scheduler.heartbeat_scheduler._revoke_run_key", AsyncMock()),
        ):
            with pytest.raises(ProviderRateLimited):
                await _dispatch_registry_adapter(adapter, agent, {})

    async def test_failed_status_raises_adapter_run_failed(self):
        """Plain FAILED terminal status must raise AdapterRunFailed (regression guard)."""
        agent = _make_agent()
        adapter = _make_adapter_returning(LLCRunStatus.FAILED)

        with (
            patch("llc.scheduler.heartbeat_scheduler._issue_run_key", AsyncMock(return_value=(None, None))),
            patch("llc.scheduler.heartbeat_scheduler._revoke_run_key", AsyncMock()),
        ):
            with pytest.raises(AdapterRunFailed):
                await _dispatch_registry_adapter(adapter, agent, {})

    async def test_completed_status_does_not_raise(self):
        """COMPLETED terminal status must return without raising."""
        agent = _make_agent()
        adapter = _make_adapter_returning(LLCRunStatus.COMPLETED)

        with (
            patch("llc.scheduler.heartbeat_scheduler._issue_run_key", AsyncMock(return_value=(None, None))),
            patch("llc.scheduler.heartbeat_scheduler._revoke_run_key", AsyncMock()),
        ):
            await _dispatch_registry_adapter(adapter, agent, {})  # must not raise


# ---------------------------------------------------------------------------
# 7. End-to-end: RATE_LIMITED status -> ProviderRateLimited -> backoff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_adapter_applies_backoff_for_registry_rate_limit():
    """_run_adapter must apply the GH#8204 backoff path when a registry adapter
    signals RATE_LIMITED (i.e. when _dispatch_registry_adapter raises ProviderRateLimited).
    """
    scheduler = HeartbeatScheduler()
    agent = _make_agent()
    redis = _make_redis()

    session_mock = AsyncMock()
    # First execute call: SELECT retry_count + UPDATE to RUNNING.
    retry_count_result = MagicMock()
    retry_count_result.scalar_one_or_none.return_value = 0
    session_mock.execute = AsyncMock(side_effect=[retry_count_result, None])
    session_mock.commit = AsyncMock()
    ctx_mgr_running = MagicMock()
    ctx_mgr_running.__aenter__ = AsyncMock(return_value=session_mock)
    ctx_mgr_running.__aexit__ = AsyncMock(return_value=False)

    # Second session: _handle_rate_limited writes RATE_LIMITED status.
    rl_session_mock = AsyncMock()
    rl_session_mock.execute = AsyncMock()
    rl_session_mock.commit = AsyncMock()
    ctx_mgr_rl = MagicMock()
    ctx_mgr_rl.__aenter__ = AsyncMock(return_value=rl_session_mock)
    ctx_mgr_rl.__aexit__ = AsyncMock(return_value=False)

    call_count = 0

    def _session_factory():
        nonlocal call_count
        call_count += 1
        return ctx_mgr_running if call_count == 1 else ctx_mgr_rl

    with (
        patch(
            "llc.scheduler.heartbeat_scheduler.get_async_session_factory",
            return_value=_session_factory,
        ),
        patch(
            "llc.scheduler.heartbeat_scheduler.get_async_redis_client",
            AsyncMock(return_value=redis),
        ),
        patch(
            "llc.scheduler.heartbeat_scheduler._dispatch_adapter",
            AsyncMock(side_effect=ProviderRateLimited(provider="anthropic")),
        ),
    ):
        await scheduler._run_adapter(agent, _RUN_ID, {})

    # RATE_LIMITED status must have been written (not FAILED).
    rl_compiled = str(
        rl_session_mock.execute.call_args[0][0].compile(compile_kwargs={"literal_binds": True})
    )
    assert LLCRunStatus.RATE_LIMITED.value in rl_compiled
    # Agent must have been re-queued in Redis.
    redis.zadd.assert_called_once()
