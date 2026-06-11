# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for shared subprocess-adapter helpers (GH#9789, GH#9769, GH#9777, GH#9839)."""

import json
import signal
from unittest.mock import AsyncMock, patch

import pytest

from llc.adapters.subprocess_support import (
    AGENT_API_KEY_PLACEHOLDER,
    inject_agent_credentials,
    probe_pid,
    render_context_markdown,
    serialize_invoke_context,
    terminate_pid,
)
from llc.models.enums import LLCRunStatus


class TestRenderContextMarkdown:
    def test_rag_brief_and_task_id(self) -> None:
        p = render_context_markdown({"rag_brief": "# Policy\nDo X.", "task_id": "t1"})
        assert "# Policy" in p
        assert "Task ID: t1" in p

    def test_fat_context_structured(self) -> None:
        p = render_context_markdown(
            {
                "work_item_detail": {
                    "title": "Fix login",
                    "status": "in_progress",
                    "priority": "high",
                    "acceptance_criteria": "Works.",
                },
                "goal_ancestry": [{"title": "Improve auth"}],
                "company_context": {"chunks": ["Uses OAuth."], "sources": []},
            }
        )
        assert "# Work Item: Fix login" in p
        assert "**Status:** in_progress" in p
        assert "## Goal Ancestry" in p
        assert "Uses OAuth." in p

    def test_never_raw_json(self) -> None:
        p = render_context_markdown({"foo": "bar", "nested": {"a": 1}})
        assert "- foo: bar" in p
        assert '"a": 1' not in p  # dict-valued key not dumped

    def test_empty_context_nonempty(self) -> None:
        assert render_context_markdown({})


class TestSerializeInvokeContext:
    def test_redacts_real_key(self) -> None:
        blob = serialize_invoke_context({"agent_api_key": "llc_real", "x": 1})
        assert "llc_real" not in blob
        assert AGENT_API_KEY_PLACEHOLDER in blob
        assert json.loads(blob)["x"] == 1

    def test_passes_through_placeholder(self) -> None:
        blob = serialize_invoke_context({"agent_api_key": AGENT_API_KEY_PLACEHOLDER})
        assert AGENT_API_KEY_PLACEHOLDER in blob

    def test_no_key_unaffected(self) -> None:
        assert json.loads(serialize_invoke_context({"y": 2}))["y"] == 2


class TestInjectAgentCredentials:
    def test_forwards_real_key(self) -> None:
        env: dict = {}
        inject_agent_credentials(env, {"agent_api_key": "llc_real", "api_base": "http://api"})
        assert env["AUTOBOT_LLC_API_KEY"] == "llc_real"
        assert env["AUTOBOT_LLC_API_BASE"] == "http://api"

    def test_skips_placeholder(self) -> None:
        env: dict = {}
        inject_agent_credentials(env, {"agent_api_key": AGENT_API_KEY_PLACEHOLDER})
        assert "AUTOBOT_LLC_API_KEY" not in env

    def test_skips_empty_key(self) -> None:
        env: dict = {}
        inject_agent_credentials(env, {})
        assert "AUTOBOT_LLC_API_KEY" not in env
        # api_base falls back to the module default
        assert env.get("AUTOBOT_LLC_API_BASE")


# ---------------------------------------------------------------------------
# probe_pid (GH#9839)
# ---------------------------------------------------------------------------


class TestProbePid:
    def test_running_when_kill_succeeds(self) -> None:
        with patch("os.kill", return_value=None):
            result = probe_pid(12345)
        assert result.status is LLCRunStatus.RUNNING

    def test_completed_on_process_lookup_error(self) -> None:
        with patch("os.kill", side_effect=ProcessLookupError):
            result = probe_pid(99999)
        assert result.status is LLCRunStatus.COMPLETED

    def test_running_on_permission_error(self) -> None:
        with patch("os.kill", side_effect=PermissionError):
            result = probe_pid(1)
        assert result.status is LLCRunStatus.RUNNING

    def test_failed_on_oserror(self) -> None:
        with patch("os.kill", side_effect=OSError("bad fd")):
            result = probe_pid(12345)
        assert result.status is LLCRunStatus.FAILED
        assert "bad fd" in (result.error or "")

    def test_uses_signal_zero(self) -> None:
        calls = []

        def capture(pid, sig):
            calls.append((pid, sig))

        with patch("os.kill", side_effect=capture):
            probe_pid(42)

        assert calls == [(42, 0)]


# ---------------------------------------------------------------------------
# terminate_pid (GH#9839)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTerminatePid:
    async def test_returns_true_when_already_gone(self) -> None:
        # SIGTERM immediately raises ProcessLookupError → process was already dead.
        with patch("os.kill", side_effect=ProcessLookupError):
            result = await terminate_pid(99999, grace_seconds=1, log_name="Test")
        assert result is True

    async def test_returns_false_when_process_exits_during_grace(self) -> None:
        # SIGTERM succeeds; first poll raises ProcessLookupError (process gone).
        kill_calls = []

        def smart_kill(pid, sig):
            kill_calls.append(sig)
            if sig == 0:
                raise ProcessLookupError  # gone after SIGTERM

        with patch("os.kill", side_effect=smart_kill):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await terminate_pid(12345, grace_seconds=1, log_name="Test")

        assert result is False
        assert signal.SIGTERM in kill_calls
        assert signal.SIGKILL not in kill_calls

    async def test_sigkill_sent_when_grace_expires(self) -> None:
        # SIGTERM succeeds; signal-0 always succeeds (process never exits).
        kill_calls = []

        def stubborn_kill(pid, sig):
            kill_calls.append(sig)
            # signal 0 always returns (process alive); SIGKILL succeeds too.

        with patch("os.kill", side_effect=stubborn_kill):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await terminate_pid(12345, grace_seconds=1, log_name="Test")

        assert result is False
        assert signal.SIGTERM in kill_calls
        assert signal.SIGKILL in kill_calls

    async def test_sigkill_tolerates_already_gone(self) -> None:
        # SIGTERM succeeds; signal-0 always succeeds (never exits); SIGKILL raises
        # ProcessLookupError — should not propagate.
        sigkill_count = [0]

        def kill_fn(pid, sig):
            if sig == signal.SIGKILL:
                sigkill_count[0] += 1
                raise ProcessLookupError
            # SIGTERM: pass; signal-0: pass (alive)

        with patch("os.kill", side_effect=kill_fn):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await terminate_pid(12345, grace_seconds=1, log_name="Test")

        assert result is False
        assert sigkill_count[0] == 1  # SIGKILL was attempted once
