# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for CopilotLocalAdapter (GH#9008).

Shared lifecycle tests (status / timeout-config / graceful-timeout) live in
test_subprocess_base.py — see GH#9844 for the consolidation rationale.
This file retains only CopilotLocalAdapter-specific assertions: command assembly,
env injection (GITHUB_TOKEN / GH_TOKEN / GH_COPILOT_MODEL), workspace-dir CWD
passing, FD management, and workspace-dir retry logic.
"""

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.adapters.base import LLCAdapter
from llc.adapters.copilot_local_adapter import (
    CopilotLocalAdapter,
    _state_path,
)

from .conftest import agent_cfg as _agent_cfg
from .conftest import make_fake_proc as _make_fake_proc

# A dummy auth value that won't match secret-scanner patterns.
_AUTH_STUB = "dummy-auth-fixture-xyz"


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
        """CopilotLocalAdapter-specific: GITHUB_TOKEN and GH_TOKEN are forwarded."""
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

    async def test_invoke_forwards_llc_api_key_and_redacts_blob(self) -> None:
        # GH#9789: copilot adapter must forward AUTOBOT_LLC_API_KEY and NOT leak
        # the real key into LLC_INVOKE_CONTEXT (regression that #9789 fixes).
        adapter = CopilotLocalAdapter()
        fake_proc = _make_fake_proc(66)
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
                await adapter.invoke(cfg, {"agent_api_key": "llc_realkey", "api_base": "http://api/llc"})

        env = captured_envs[0]
        assert env.get("AUTOBOT_LLC_API_KEY") == "llc_realkey"
        assert env.get("AUTOBOT_LLC_API_BASE") == "http://api/llc"
        assert "llc_realkey" not in env.get("LLC_INVOKE_CONTEXT", "")
        assert "<injected-at-runtime>" in env.get("LLC_INVOKE_CONTEXT", "")

    async def test_invoke_sets_copilot_model_env_var(self) -> None:
        """CopilotLocalAdapter-specific: GH_COPILOT_MODEL env var is forwarded."""
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
        """CopilotLocalAdapter-specific: default model is copilot-4o."""
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
        """CopilotLocalAdapter-specific: workspace_dir is passed as cwd to subprocess."""
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
# cancel — CopilotLocalAdapter-specific: state file removal
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
        """CopilotLocalAdapter: cancel() removes the state file (base _cancel behaviour)."""
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
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_copilot_local_registered(self) -> None:
        from llc.adapters import get_adapter

        adapter = get_adapter("copilot_local")
        assert isinstance(adapter, CopilotLocalAdapter)
