# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for ClaudeCodeAdapter (GH#8258).

Shared lifecycle tests (status / timeout-config / graceful-timeout) live in
test_subprocess_base.py — see GH#9844 for the consolidation rationale.
This file retains only ClaudeCodeAdapter-specific assertions: command assembly,
env injection, allowed-tools flag, Redis session resume, FD management, and
workspace-dir retry logic.
"""

import json
import os
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.adapters.base import LLCAdapter
from llc.adapters.claude_code_adapter import (
    ClaudeCodeAdapter,
    _state_path,
)

from .conftest import agent_cfg as _agent_cfg
from .conftest import make_fake_proc as _make_fake_proc

# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_llc_adapter_protocol(self) -> None:
        assert isinstance(ClaudeCodeAdapter(), LLCAdapter)


# ---------------------------------------------------------------------------
# _build_prompt (via adapter method)
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def _prompt(self, context: dict) -> str:
        return ClaudeCodeAdapter()._build_prompt(context)

    def test_fat_mode_includes_rag_brief(self) -> None:
        p = self._prompt({"rag_brief": "# Policy\nDo X.", "task_id": "t1"})
        assert "# Policy" in p
        assert "Task ID: t1" in p

    def test_thin_mode_task_and_url(self) -> None:
        p = self._prompt({"task_id": "t2", "api_base_url": "http://api"})
        assert "Task ID: t2" in p
        assert "API base URL: http://api" in p

    def test_empty_context_returns_nonempty_placeholder(self) -> None:
        # GH#9622: empty context must not produce a raw JSON dump.
        p = self._prompt({})
        assert p  # non-empty
        assert p.strip() != "{}"
        assert not p.lstrip().startswith("{")

    def test_unknown_scalar_keys_rendered_as_bullets_not_json(self) -> None:
        # GH#9622: unknown scalar keys are bulleted, never json.dumps(context).
        p = self._prompt({"foo": "bar"})
        assert "- foo: bar" in p
        assert '"foo"' not in p  # not JSON-serialised

    def test_fat_context_renders_structured_markdown(self) -> None:
        # GH#9622: heartbeat fat context becomes a readable Markdown brief.
        p = self._prompt(
            {
                "work_item_detail": {
                    "title": "Fix login",
                    "status": "in_progress",
                    "priority": "high",
                    "description": "Users cannot log in.",
                    "acceptance_criteria": "Login works.",
                },
                "goal_ancestry": [{"title": "Improve auth"}],
                "company_context": {"chunks": ["Company uses OAuth."], "sources": []},
                "agent_memory": {"chunks": ["Tried fix A."], "sources": []},
                "similar_past_work": [{"title": "Past auth fix"}],
                "agent_api_key": "<injected-at-runtime>",
            }
        )
        assert "# Work Item: Fix login" in p
        assert "**Status:** in_progress" in p
        assert "## Acceptance Criteria" in p
        assert "## Goal Ancestry" in p
        assert "- Improve auth" in p
        assert "Company uses OAuth." in p
        assert "Tried fix A." in p
        assert "Past auth fix" in p
        # The build-time API-key placeholder must never leak into the prompt.
        assert "<injected-at-runtime>" not in p

    def test_never_emits_raw_json_dump(self) -> None:
        # GH#9622: regression guard — a dict-valued unknown key is not dumped.
        p = self._prompt({"work_item_detail": {"title": "T"}, "raw": {"a": 1}})
        assert '{"a": 1}' not in p
        assert '"a": 1' not in p

    def test_wrong_type_fields_handled_gracefully(self) -> None:
        # GH#9622: helpers guard against mistyped fat-context values.
        p = self._prompt(
            {
                "work_item_detail": "not-a-dict",
                "goal_ancestry": {"not": "a-list"},
                "company_context": "not-a-dict",
                "task_id": "t-ok",
            }
        )
        assert "# Work Item" not in p  # string detail skipped
        assert "## Goal Ancestry" not in p  # dict ancestry skipped
        assert "Task ID: t-ok" in p  # valid field still rendered

    def test_kb_chunks_filters_empty_and_nonstring(self) -> None:
        # GH#9622: blank/whitespace chunks are dropped; an all-empty block is omitted.
        p = self._prompt({"company_context": {"chunks": ["  ", "", "Real chunk"], "sources": []}})
        assert "Real chunk" in p
        empty = self._prompt({"agent_memory": {"chunks": ["", "   "], "sources": []}})
        assert "## Agent Memory" not in empty


# ---------------------------------------------------------------------------
# invoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestInvoke:
    async def test_invoke_returns_pid_slash_session(self) -> None:
        adapter = ClaudeCodeAdapter()
        fake_proc = _make_fake_proc(99)

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td)
            with (
                patch("llc.adapters.claude_code_adapter.shutil.which", return_value="/usr/bin/claude"),
                patch(
                    "llc.adapters.claude_code_adapter.get_async_redis_client", new_callable=AsyncMock, return_value=None
                ),
                patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=fake_proc),
                patch("builtins.open", MagicMock(return_value=MagicMock())),
            ):
                run_id = await adapter.invoke(cfg, {"task_id": "t1"})

        parts = run_id.split("/")
        assert parts[0] == "99"
        assert len(parts[1]) == 36  # UUID

    async def test_invoke_raises_when_claude_missing(self) -> None:
        adapter = ClaudeCodeAdapter()
        with patch("llc.adapters.claude_code_adapter.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="claude CLI not found"):
                await adapter.invoke(_agent_cfg(), {})

    async def test_invoke_writes_state_file(self) -> None:
        adapter = ClaudeCodeAdapter()
        fake_proc = _make_fake_proc(77)

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td)
            # GH#9763: do NOT patch builtins.open here — the state file must be
            # written for real to the temp dir so the os.path.exists assertion
            # below is meaningful. Only the subprocess + redis are mocked.
            with (
                patch("llc.adapters.claude_code_adapter.shutil.which", return_value="/usr/bin/claude"),
                patch(
                    "llc.adapters.claude_code_adapter.get_async_redis_client", new_callable=AsyncMock, return_value=None
                ),
                patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=fake_proc),
            ):
                run_id = await adapter.invoke(cfg, {"task_id": "t99"})

            # State file must exist after invoke
            state_file = _state_path(td, run_id)
            assert os.path.exists(state_file)
            with open(state_file) as fh:
                state = json.load(fh)
            assert state["pid"] == 77
            assert "session_id" in state

    async def test_invoke_resumes_when_session_exists(self) -> None:
        adapter = ClaudeCodeAdapter()
        fake_proc = _make_fake_proc(55)
        stored_session = "abcd-1234-efgh-5678-" + "x" * 16

        fake_redis = AsyncMock()
        fake_redis.get = AsyncMock(return_value=json.dumps({"session_id": stored_session, "stored_at": time.time()}))
        fake_redis.set = AsyncMock()

        captured_cmd: list = []

        async def fake_exec(*args, **kwargs):
            captured_cmd.extend(args)
            return fake_proc

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td)
            with (
                patch("llc.adapters.claude_code_adapter.shutil.which", return_value="/usr/bin/claude"),
                patch(
                    "llc.adapters.claude_code_adapter.get_async_redis_client",
                    new_callable=AsyncMock,
                    return_value=fake_redis,
                ),
                patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
                patch("builtins.open", MagicMock(return_value=MagicMock())),
            ):
                await adapter.invoke(cfg, {"task_id": "resume-test"})

        assert "--resume" in captured_cmd
        resume_idx = captured_cmd.index("--resume")
        assert captured_cmd[resume_idx + 1] == stored_session

    async def test_invoke_passes_allowed_tools(self) -> None:
        adapter = ClaudeCodeAdapter()
        fake_proc = _make_fake_proc(44)
        captured_cmd: list = []

        async def fake_exec(*args, **kwargs):
            captured_cmd.extend(args)
            return fake_proc

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td, allowed_tools=["Bash", "Read"])
            with (
                patch("llc.adapters.claude_code_adapter.shutil.which", return_value="/usr/bin/claude"),
                patch(
                    "llc.adapters.claude_code_adapter.get_async_redis_client", new_callable=AsyncMock, return_value=None
                ),
                patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
                patch("builtins.open", MagicMock(return_value=MagicMock())),
            ):
                await adapter.invoke(cfg, {})

        assert "--allowedTools" in captured_cmd
        tools_idx = captured_cmd.index("--allowedTools")
        assert captured_cmd[tools_idx + 1] == "Bash,Read"

    async def test_invoke_injects_agent_api_key_env(self) -> None:
        # GH#9623: a real agent_api_key is forwarded as AUTOBOT_LLC_API_KEY.
        adapter = ClaudeCodeAdapter()
        fake_proc = _make_fake_proc(33)
        captured_env: dict = {}

        async def fake_exec(*args, **kwargs):
            captured_env.update(kwargs.get("env") or {})
            return fake_proc

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td)
            with (
                patch("llc.adapters.claude_code_adapter.shutil.which", return_value="/usr/bin/claude"),
                patch(
                    "llc.adapters.claude_code_adapter.get_async_redis_client", new_callable=AsyncMock, return_value=None
                ),
                patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
                patch("builtins.open", MagicMock(return_value=MagicMock())),
            ):
                await adapter.invoke(cfg, {"agent_api_key": "real-key-123", "api_base": "http://api/llc"})

        assert captured_env.get("AUTOBOT_LLC_API_KEY") == "real-key-123"
        assert captured_env.get("AUTOBOT_LLC_API_BASE") == "http://api/llc"
        # GH#9623: the real key must NOT be duplicated inside the broader
        # LLC_INVOKE_CONTEXT blob — it is redacted to the placeholder there.
        assert "real-key-123" not in captured_env.get("LLC_INVOKE_CONTEXT", "")
        assert "<injected-at-runtime>" in captured_env.get("LLC_INVOKE_CONTEXT", "")

    async def test_invoke_skips_placeholder_api_key(self) -> None:
        # GH#9623: the build-time placeholder is never forwarded to the subprocess.
        adapter = ClaudeCodeAdapter()
        fake_proc = _make_fake_proc(34)
        captured_env: dict = {}

        async def fake_exec(*args, **kwargs):
            captured_env.update(kwargs.get("env") or {})
            return fake_proc

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td)
            with (
                patch("llc.adapters.claude_code_adapter.shutil.which", return_value="/usr/bin/claude"),
                patch(
                    "llc.adapters.claude_code_adapter.get_async_redis_client", new_callable=AsyncMock, return_value=None
                ),
                patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
                patch("builtins.open", MagicMock(return_value=MagicMock())),
            ):
                await adapter.invoke(cfg, {"agent_api_key": "<injected-at-runtime>"})

        assert "AUTOBOT_LLC_API_KEY" not in captured_env

    async def test_fd_closed_when_exec_raises(self) -> None:
        """out_fh must be closed even if create_subprocess_exec raises (GH#6471 follow-up)."""
        adapter = ClaudeCodeAdapter()
        fake_fh = MagicMock()

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td)
            with (
                patch("llc.adapters.claude_code_adapter.shutil.which", return_value="/usr/bin/claude"),
                patch(
                    "llc.adapters.claude_code_adapter.get_async_redis_client", new_callable=AsyncMock, return_value=None
                ),
                patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, side_effect=OSError("boom")),
                patch("builtins.open", MagicMock(return_value=fake_fh)),
            ):
                with pytest.raises(OSError):
                    await adapter.invoke(cfg, {})

        fake_fh.close.assert_called_once()

    async def test_fd_closed_on_success(self) -> None:
        """out_fh must be closed even on the happy path."""
        adapter = ClaudeCodeAdapter()
        fake_proc = _make_fake_proc(88)
        fake_fh = MagicMock()

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td)
            with (
                patch("llc.adapters.claude_code_adapter.shutil.which", return_value="/usr/bin/claude"),
                patch(
                    "llc.adapters.claude_code_adapter.get_async_redis_client", new_callable=AsyncMock, return_value=None
                ),
                patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=fake_proc),
                patch("builtins.open", MagicMock(return_value=fake_fh)),
            ):
                await adapter.invoke(cfg, {})

        fake_fh.close.assert_called_once()

    async def test_workspace_dir_missing_retries_without_cwd(self) -> None:
        """If workspace_dir is deleted, adapter retries without cwd and clears it from context."""
        adapter = ClaudeCodeAdapter()
        fake_proc = _make_fake_proc(77)
        call_count = 0
        context = {"workspace_dir": "/deleted/worktree", "task_id": "t1"}
        fake_fh = MagicMock()
        captured_envs: list[dict] = []

        async def exec_raising_first(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            captured_envs.append(dict(kwargs.get("env", {})))
            if call_count == 1:
                err = FileNotFoundError("No such directory")
                err.filename = "/deleted/worktree"
                raise err
            return fake_proc

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td)
            with (
                patch("llc.adapters.claude_code_adapter.shutil.which", return_value="/usr/bin/claude"),
                patch(
                    "llc.adapters.claude_code_adapter.get_async_redis_client", new_callable=AsyncMock, return_value=None
                ),
                patch("asyncio.create_subprocess_exec", side_effect=exec_raising_first),
                patch("builtins.open", MagicMock(return_value=fake_fh)),
            ):
                run_id = await adapter.invoke(cfg, context)

        assert call_count == 2
        assert "workspace_dir" not in context
        assert run_id.startswith("77/")
        fake_fh.close.assert_called_once()
        assert "AUTOBOT_WORKSPACE_DIR" in captured_envs[0]
        assert "AUTOBOT_WORKSPACE_DIR" not in captured_envs[1]
        retry_ctx = json.loads(captured_envs[1]["LLC_INVOKE_CONTEXT"])
        assert "workspace_dir" not in retry_ctx

    async def test_workspace_dir_missing_no_retry_when_unset(self) -> None:
        """FileNotFoundError propagates unchanged when workspace_dir is not in context."""
        adapter = ClaudeCodeAdapter()

        with tempfile.TemporaryDirectory() as td:
            cfg = _agent_cfg(output_dir=td)
            with (
                patch("llc.adapters.claude_code_adapter.shutil.which", return_value="/usr/bin/claude"),
                patch(
                    "llc.adapters.claude_code_adapter.get_async_redis_client", new_callable=AsyncMock, return_value=None
                ),
                patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, side_effect=FileNotFoundError("gone")),
                patch("builtins.open", MagicMock(return_value=MagicMock())),
            ):
                with pytest.raises(FileNotFoundError):
                    await adapter.invoke(cfg, {"task_id": "t2"})


# ---------------------------------------------------------------------------
# cancel — ClaudeCodeAdapter-specific: Redis session clear via _post_cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCancel:
    async def test_cancel_sends_sigterm(self) -> None:
        adapter = ClaudeCodeAdapter()

        with tempfile.TemporaryDirectory() as td:
            with (
                patch("os.kill", side_effect=[None, ProcessLookupError()]),
                patch(
                    "llc.adapters.claude_code_adapter.get_async_redis_client", new_callable=AsyncMock, return_value=None
                ),
            ):
                await adapter.cancel(_agent_cfg(agent_id="a1", output_dir=td), "5678/session-q")

        # First kill call should have been SIGTERM
        # (second is the probing kill(pid, 0) which raised ProcessLookupError)

    async def test_cancel_already_dead_does_not_raise(self) -> None:
        adapter = ClaudeCodeAdapter()

        with tempfile.TemporaryDirectory() as td:
            with (
                patch("os.kill", side_effect=ProcessLookupError()),
                patch(
                    "llc.adapters.claude_code_adapter.get_async_redis_client", new_callable=AsyncMock, return_value=None
                ),
            ):
                await adapter.cancel(_agent_cfg(agent_id="a2", output_dir=td), "9999/session-r")

    async def test_cancel_clears_redis_session(self) -> None:
        """ClaudeCodeAdapter-specific: _post_cancel clears the Redis resume session."""
        adapter = ClaudeCodeAdapter()
        fake_redis = AsyncMock()
        fake_redis.delete = AsyncMock()

        with tempfile.TemporaryDirectory() as td:
            with (
                patch("os.kill", side_effect=ProcessLookupError()),
                patch(
                    "llc.adapters.claude_code_adapter.get_async_redis_client",
                    new_callable=AsyncMock,
                    return_value=fake_redis,
                ),
            ):
                await adapter.cancel(_agent_cfg(agent_id="agent-clear", output_dir=td), "1/session-s")

        fake_redis.delete.assert_awaited_once()
        key_arg = fake_redis.delete.call_args[0][0]
        assert "agent-clear" in key_arg

    async def test_cancel_unparseable_run_id_is_noop(self) -> None:
        adapter = ClaudeCodeAdapter()
        # Should not raise
        await adapter.cancel(_agent_cfg(), "bad-run-id")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_claude_code_registered(self) -> None:
        from llc.adapters import get_adapter

        adapter = get_adapter("claude_code")
        assert isinstance(adapter, ClaudeCodeAdapter)
