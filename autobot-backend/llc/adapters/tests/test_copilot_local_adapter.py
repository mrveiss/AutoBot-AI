# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for CopilotLocalAdapter (GH#9008)."""

import json
import os
import signal
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.adapters.base import LLCAdapter
from llc.adapters.copilot_local_adapter import (
    CopilotLocalAdapter,
    _state_path,
)
from llc.models.enums import LLCRunStatus

# A dummy auth value that won't match secret-scanner patterns.
_AUTH_STUB = "dummy-auth-fixture-xyz"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_cfg(agent_id: str = "agent-1", output_dir: str | None = None, **kwargs) -> dict:
    cfg: dict = {"agent_id": agent_id, "adapter_config": {**kwargs}}
    if output_dir:
        cfg["adapter_config"]["output_dir"] = output_dir
    return cfg


def _make_fake_proc(pid: int = 12345) -> MagicMock:
    proc = MagicMock()
    proc.pid = pid
    return proc


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_llc_adapter_protocol(self) -> None:
        assert isinstance(CopilotLocalAdapter(), LLCAdapter)


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def _prompt(self, context: dict) -> str:
        return CopilotLocalAdapter()._build_prompt(context)

    def test_includes_rag_brief_and_task_id(self) -> None:
        p = self._prompt({"rag_brief": "# Policy\nDo X.", "task_id": "t1"})
        assert "# Policy" in p
        assert "Task ID: t1" in p

    def test_task_and_api_base(self) -> None:
        p = self._prompt({"task_id": "t2", "api_base_url": "http://api"})
        assert "Task ID: t2" in p
        assert "API base URL: http://api" in p

    def test_empty_context_falls_back_to_json(self) -> None:
        p = self._prompt({})
        assert p

    def test_unknown_keys_serialised_as_json(self) -> None:
        p = self._prompt({"foo": "bar"})
        assert "bar" in p


# ---------------------------------------------------------------------------
# invoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestInvoke:
    async def test_invoke_returns_pid_slash_session(self) -> None:
        adapter = CopilotLocalAdapter()
        fake_proc = _make_fake_proc(99)

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td)
            with (
                patch("llc.adapters.copilot_local_adapter.shutil.which", return_value="/usr/bin/gh"),
                patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=fake_proc),
                patch("builtins.open", MagicMock(return_value=MagicMock())),
            ):
                run_id = await adapter.invoke(cfg, {"task_id": "t1"})

        parts = run_id.split("/")
        assert parts[0] == "99"
        assert len(parts[1]) == 36  # UUID

    async def test_invoke_raises_when_gh_missing(self) -> None:
        adapter = CopilotLocalAdapter()
        with patch("llc.adapters.copilot_local_adapter.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="gh CLI not found"):
                await adapter.invoke(_agent_cfg(), {})

    async def test_invoke_writes_state_file(self) -> None:
        adapter = CopilotLocalAdapter()
        fake_proc = _make_fake_proc(77)

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td)
            with (
                patch("llc.adapters.copilot_local_adapter.shutil.which", return_value="/usr/bin/gh"),
                patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=fake_proc),
            ):
                run_id = await adapter.invoke(cfg, {"task_id": "t99"})

            state_file = _state_path(td, run_id)
            assert os.path.exists(state_file)
            with open(state_file) as fh:
                state = json.load(fh)
            assert state["pid"] == 77
            assert "session_id" in state

    async def test_invoke_sets_github_auth_env_vars(self) -> None:
        adapter = CopilotLocalAdapter()
        fake_proc = _make_fake_proc(44)
        captured_envs: list[dict] = []

        async def fake_exec(*args, **kwargs):
            captured_envs.append(dict(kwargs.get("env", {})))
            return fake_proc

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td, gh_token=_AUTH_STUB)
            with (
                patch("llc.adapters.copilot_local_adapter.shutil.which", return_value="/usr/bin/gh"),
                patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
                patch("builtins.open", MagicMock(return_value=MagicMock())),
            ):
                await adapter.invoke(cfg, {})

        assert captured_envs[0].get("GITHUB_TOKEN") == _AUTH_STUB
        assert captured_envs[0].get("GH_TOKEN") == _AUTH_STUB

    async def test_invoke_sets_copilot_model_env_var(self) -> None:
        adapter = CopilotLocalAdapter()
        fake_proc = _make_fake_proc(55)
        captured_envs: list[dict] = []

        async def fake_exec(*args, **kwargs):
            captured_envs.append(dict(kwargs.get("env", {})))
            return fake_proc

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td, copilot_model="copilot-4o")
            with (
                patch("llc.adapters.copilot_local_adapter.shutil.which", return_value="/usr/bin/gh"),
                patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
                patch("builtins.open", MagicMock(return_value=MagicMock())),
            ):
                await adapter.invoke(cfg, {})

        assert captured_envs[0].get("GH_COPILOT_MODEL") == "copilot-4o"

    async def test_invoke_default_model_is_copilot_4o(self) -> None:
        adapter = CopilotLocalAdapter()
        fake_proc = _make_fake_proc(56)
        captured_envs: list[dict] = []

        async def fake_exec(*args, **kwargs):
            captured_envs.append(dict(kwargs.get("env", {})))
            return fake_proc

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td)
            with (
                patch("llc.adapters.copilot_local_adapter.shutil.which", return_value="/usr/bin/gh"),
                patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
                patch("builtins.open", MagicMock(return_value=MagicMock())),
            ):
                await adapter.invoke(cfg, {})

        assert captured_envs[0].get("GH_COPILOT_MODEL") == "copilot-4o"

    async def test_invoke_passes_workspace_dir_as_cwd(self) -> None:
        adapter = CopilotLocalAdapter()
        fake_proc = _make_fake_proc(66)
        captured_kwargs: list[dict] = []

        async def fake_exec(*args, **kwargs):
            captured_kwargs.append(kwargs)
            return fake_proc

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td, workspace_dir="/workspace/dir")
            with (
                patch("llc.adapters.copilot_local_adapter.shutil.which", return_value="/usr/bin/gh"),
                patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
                patch("builtins.open", MagicMock(return_value=MagicMock())),
            ):
                await adapter.invoke(cfg, {})

        assert captured_kwargs[0].get("cwd") == "/workspace/dir"

    async def test_fd_closed_when_exec_raises(self) -> None:
        adapter = CopilotLocalAdapter()
        fake_fh = MagicMock()

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td)
            with (
                patch("llc.adapters.copilot_local_adapter.shutil.which", return_value="/usr/bin/gh"),
                patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, side_effect=OSError("boom")),
                patch("builtins.open", MagicMock(return_value=fake_fh)),
            ):
                with pytest.raises(OSError):
                    await adapter.invoke(cfg, {})

        fake_fh.close.assert_called_once()

    async def test_fd_closed_on_success(self) -> None:
        adapter = CopilotLocalAdapter()
        fake_proc = _make_fake_proc(88)
        fake_fh = MagicMock()

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td)
            with (
                patch("llc.adapters.copilot_local_adapter.shutil.which", return_value="/usr/bin/gh"),
                patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=fake_proc),
                patch("builtins.open", MagicMock(return_value=fake_fh)),
            ):
                await adapter.invoke(cfg, {})

        fake_fh.close.assert_called_once()

    async def test_workspace_dir_missing_retries_without_cwd(self) -> None:
        adapter = CopilotLocalAdapter()
        fake_proc = _make_fake_proc(77)
        call_count = 0
        fake_fh = MagicMock()
        captured_kwargs: list[dict] = []

        async def exec_raising_first(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            captured_kwargs.append(dict(kwargs))
            if call_count == 1:
                import errno as _errno

                raise FileNotFoundError(_errno.ENOENT, "No such file or directory", "/deleted/worktree")
            return fake_proc

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td, workspace_dir="/deleted/worktree")
            with (
                patch("llc.adapters.copilot_local_adapter.shutil.which", return_value="/usr/bin/gh"),
                patch("asyncio.create_subprocess_exec", side_effect=exec_raising_first),
                patch("builtins.open", MagicMock(return_value=fake_fh)),
            ):
                run_id = await adapter.invoke(cfg, {"task_id": "t1"})

        assert call_count == 2
        assert run_id.startswith("77/")
        assert captured_kwargs[0].get("cwd") == "/deleted/worktree"
        assert captured_kwargs[1].get("cwd") is None
        fake_fh.close.assert_called_once()


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStatus:
    async def test_running_pid_returns_running(self) -> None:
        adapter = CopilotLocalAdapter()
        with patch("os.kill", return_value=None):
            result = await adapter.status(_agent_cfg(), "1234/session-abc")
        assert result.status == LLCRunStatus.RUNNING

    async def test_dead_pid_returns_completed(self) -> None:
        adapter = CopilotLocalAdapter()

        def fake_kill(pid, sig):
            raise ProcessLookupError

        with patch("os.kill", side_effect=fake_kill):
            result = await adapter.status(_agent_cfg(), "9999/session-abc")
        assert result.status == LLCRunStatus.COMPLETED

    async def test_timeout_triggers_cancel_and_returns_timeout(self) -> None:
        adapter = CopilotLocalAdapter()

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

            async def fake_cancel(agent_config, run_id):
                cancel_called.append(run_id)

            adapter.cancel = fake_cancel  # type: ignore[assignment]
            result = await adapter.status(_agent_cfg(output_dir=td), run_id)

        assert result.status == LLCRunStatus.TIMEOUT
        assert run_id in cancel_called

    async def test_unparseable_run_id_returns_failed(self) -> None:
        adapter = CopilotLocalAdapter()
        result = await adapter.status(_agent_cfg(), "not-a-valid-run-id")
        assert result.status == LLCRunStatus.FAILED

    async def test_exception_in_probe_returns_failed(self) -> None:
        adapter = CopilotLocalAdapter()

        def bad_kill(pid, sig):
            raise OSError("unexpected")

        with patch("os.kill", side_effect=bad_kill):
            result = await adapter.status(_agent_cfg(), "1234/session-abc")
        assert result.status == LLCRunStatus.FAILED


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCancel:
    async def test_cancel_sends_sigterm(self) -> None:
        adapter = CopilotLocalAdapter()
        import signal as sig_mod

        killed: list = []

        def smart_kill(pid, s):
            killed.append((pid, s))
            if s == sig_mod.SIGTERM:
                return
            if s == 0 and any(s2 == sig_mod.SIGTERM for _, s2 in killed):
                raise ProcessLookupError

        with (
            patch("os.kill", side_effect=smart_kill),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            with tempfile.TemporaryDirectory() as td:
                await adapter.cancel(_agent_cfg(agent_id="a1", output_dir=td), "5678/session-q")

        assert any(s == sig_mod.SIGTERM for _, s in killed)

    async def test_cancel_already_dead_does_not_raise(self) -> None:
        adapter = CopilotLocalAdapter()
        with tempfile.TemporaryDirectory() as td:
            with patch("os.kill", side_effect=ProcessLookupError()):
                await adapter.cancel(_agent_cfg(agent_id="a2", output_dir=td), "9999/session-r")

    async def test_cancel_unparseable_run_id_is_noop(self) -> None:
        adapter = CopilotLocalAdapter()
        await adapter.cancel(_agent_cfg(), "bad-run-id")

    async def test_cancel_removes_state_file(self) -> None:
        adapter = CopilotLocalAdapter()

        with tempfile.TemporaryDirectory() as td:
            run_id = "4321/session-del"
            state_file = _state_path(td, run_id)
            with open(state_file, "w") as fh:
                json.dump({"pid": 4321}, fh)

            with patch("os.kill", side_effect=ProcessLookupError()):
                await adapter.cancel(_agent_cfg(output_dir=td), run_id)

            assert not os.path.exists(state_file)


# ---------------------------------------------------------------------------
# Timeout Configuration (3-tier hierarchy)
# ---------------------------------------------------------------------------


class TestTimeoutConfiguration:
    """Test 3-tier timeout configuration per MVA-2940 ADR."""

    def test_per_agent_override_highest_priority(self, monkeypatch) -> None:
        """Tier 1: per-agent timeout_seconds overrides everything."""
        from llc.adapters.copilot_local_adapter import _resolve_timeout

        monkeypatch.setenv("LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS", "250")
        cfg = {"timeout_seconds": 500}
        assert _resolve_timeout(cfg) == 500

    def test_global_env_var_when_no_agent_override(self, monkeypatch) -> None:
        """Tier 2/3: global env var used when per-agent override absent."""
        from llc.adapters.copilot_local_adapter import _resolve_timeout

        monkeypatch.setenv("LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS", "180")
        cfg = {}  # no per-agent override
        assert _resolve_timeout(cfg) == 180

    def test_adapter_default_when_no_env_var(self, monkeypatch) -> None:
        """Fallback: per-adapter default (3600) when env var unset."""
        from llc.adapters.copilot_local_adapter import _resolve_timeout

        monkeypatch.delenv("LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS", raising=False)
        cfg = {}
        assert _resolve_timeout(cfg) == 3600  # _ADAPTER_TIMEOUT_SECONDS

    def test_precedence_order_all_three_tiers(self, monkeypatch) -> None:
        """Verify precedence: per-agent > global env > adapter default."""
        from llc.adapters.copilot_local_adapter import _resolve_timeout

        # Set global env var
        monkeypatch.setenv("LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS", "200")

        # Tier 1: per-agent wins
        assert _resolve_timeout({"timeout_seconds": 100}) == 100

        # Tier 2: global env var when no per-agent
        assert _resolve_timeout({}) == 200

        # Tier 3: adapter default when env var cleared
        monkeypatch.delenv("LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS")
        assert _resolve_timeout({}) == 3600


@pytest.mark.asyncio
class TestGracefulTimeout:
    """Test graceful SIGTERM + SIGKILL with 10s grace period."""

    async def test_grace_period_is_10_seconds(self) -> None:
        """Verify _SIGTERM_GRACE_SECONDS is 10 (per MVA-2940 ADR)."""
        from llc.adapters.copilot_local_adapter import _SIGTERM_GRACE_SECONDS

        assert _SIGTERM_GRACE_SECONDS == 10

    async def test_cancel_sends_sigterm_then_sigkill_after_grace(self) -> None:
        """cancel() sends SIGTERM, waits 10s, then SIGKILL."""
        from llc.adapters.copilot_local_adapter import _SIGTERM_GRACE_SECONDS, CopilotLocalAdapter

        adapter = CopilotLocalAdapter()
        kill_signals = []

        def fake_kill(pid, sig):
            kill_signals.append((pid, sig))
            if sig == signal.SIGKILL:
                raise ProcessLookupError()  # process dies

        with tempfile.TemporaryDirectory() as td:
            state_file = _state_path(td, "123/session-x")
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, "w") as f:
                json.dump({"pid": 123, "session_id": "session-x"}, f)

            with (
                patch("os.kill", side_effect=fake_kill),
                patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            ):
                await adapter.cancel(_agent_cfg(output_dir=td), "123/session-x")

        # Verify SIGTERM sent first
        assert kill_signals[0] == (123, signal.SIGTERM)
        # Verify grace period wait (10s in 0.1s increments = 100 iterations)
        assert mock_sleep.await_count == _SIGTERM_GRACE_SECONDS * 10
        # Verify SIGKILL sent after grace period
        assert (123, signal.SIGKILL) in kill_signals


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_copilot_local_registered(self) -> None:
        from llc.adapters import get_adapter

        adapter = get_adapter("copilot_local")
        assert isinstance(adapter, CopilotLocalAdapter)
