# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for shared subprocess-adapter helpers (GH#9789, GH#9769, GH#9777, GH#9839)."""

import json
import signal
from unittest.mock import AsyncMock, patch

import psutil
import pytest

from llc.adapters.subprocess_support import (
    AGENT_API_KEY_PLACEHOLDER,
    _identity_verified,
    _process_group_id,
    extract_usage,
    inject_agent_credentials,
    probe_pid,
    probe_pid_identity,
    render_context_markdown,
    serialize_invoke_context,
    terminate_pid,
)
from llc.models.enums import LLCRunStatus

_PSUTIL_PROCESS = "llc.adapters.subprocess_support.psutil.Process"


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
    """Identity (PR#16284 review) is verified via a mocked psutil.Process.create_time()
    matching *expected_create_time* — everything here is otherwise the original
    SIGTERM/grace/SIGKILL sequence, unaffected by the identity check once it passes.
    """

    async def test_returns_true_when_already_gone(self) -> None:
        # Identity verifies; SIGTERM itself then raises ProcessLookupError.
        with patch(_PSUTIL_PROCESS) as mock_cls, patch("os.kill", side_effect=ProcessLookupError):
            mock_cls.return_value.create_time.return_value = 100.0
            result = await terminate_pid(99999, grace_seconds=1, log_name="Test", expected_create_time=100.0)
        assert result is True

    async def test_returns_false_when_process_exits_during_grace(self) -> None:
        # SIGTERM succeeds; first poll raises ProcessLookupError (process gone).
        kill_calls = []

        def smart_kill(pid, sig):
            kill_calls.append(sig)
            if sig == 0:
                raise ProcessLookupError  # gone after SIGTERM

        with (
            patch(_PSUTIL_PROCESS) as mock_cls,
            patch("os.kill", side_effect=smart_kill),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_cls.return_value.create_time.return_value = 100.0
            result = await terminate_pid(12345, grace_seconds=1, log_name="Test", expected_create_time=100.0)

        assert result is False
        assert signal.SIGTERM in kill_calls
        assert signal.SIGKILL not in kill_calls

    async def test_sigkill_sent_when_grace_expires(self) -> None:
        # SIGTERM succeeds; signal-0 always succeeds (process never exits).
        kill_calls = []

        def stubborn_kill(pid, sig):
            kill_calls.append(sig)
            # signal 0 always returns (process alive); SIGKILL succeeds too.

        with (
            patch(_PSUTIL_PROCESS) as mock_cls,
            patch("os.kill", side_effect=stubborn_kill),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_cls.return_value.create_time.return_value = 100.0
            result = await terminate_pid(12345, grace_seconds=1, log_name="Test", expected_create_time=100.0)

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

        with (
            patch(_PSUTIL_PROCESS) as mock_cls,
            patch("os.kill", side_effect=kill_fn),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_cls.return_value.create_time.return_value = 100.0
            result = await terminate_pid(12345, grace_seconds=1, log_name="Test", expected_create_time=100.0)

        assert result is False
        assert sigkill_count[0] == 1  # SIGKILL was attempted once


# ---------------------------------------------------------------------------
# terminate_pid identity guards (PR#16284 review) — never signal a process
# the run no longer owns.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTerminatePidIdentityGuards:
    async def test_no_recorded_create_time_never_signals(self) -> None:
        """An old state file (no create_time recorded) probes only, never signals."""
        with patch("os.kill") as mock_kill, patch("os.killpg") as mock_killpg:
            result = await terminate_pid(12345, grace_seconds=1, log_name="Test", expected_create_time=None)
        assert result is True
        mock_kill.assert_not_called()
        mock_killpg.assert_not_called()

    async def test_mismatched_create_time_never_signals(self) -> None:
        """A live pid under a DIFFERENT identity (reused) is never signalled."""
        with (
            patch(_PSUTIL_PROCESS) as mock_cls,
            patch("os.kill") as mock_kill,
            patch("os.killpg") as mock_killpg,
        ):
            mock_cls.return_value.create_time.return_value = 200.0  # not the recorded 100.0
            result = await terminate_pid(12345, grace_seconds=1, log_name="Test", expected_create_time=100.0)
        assert result is True
        mock_kill.assert_not_called()
        mock_killpg.assert_not_called()

    @pytest.mark.parametrize("protected_pid", [1, 0, -5])
    async def test_pid_le_1_refused_even_with_matching_identity(self, protected_pid: int) -> None:
        """pid<=1 is refused outright, even when identity would otherwise verify."""
        with (
            patch(_PSUTIL_PROCESS) as mock_cls,
            patch("os.kill") as mock_kill,
            patch("os.killpg") as mock_killpg,
        ):
            mock_cls.return_value.create_time.return_value = 100.0
            result = await terminate_pid(protected_pid, grace_seconds=1, log_name="Test", expected_create_time=100.0)
        assert result is True
        mock_kill.assert_not_called()
        mock_killpg.assert_not_called()


# ---------------------------------------------------------------------------
# probe_pid_identity (PR#16284 review)
# ---------------------------------------------------------------------------


class TestProbePidIdentity:
    def test_no_expected_create_time_falls_back_to_probe_pid(self) -> None:
        with patch("os.kill", return_value=None):
            result = probe_pid_identity(12345, None)
        assert result.status is LLCRunStatus.RUNNING

    def test_matching_create_time_is_running(self) -> None:
        with patch(_PSUTIL_PROCESS) as mock_cls:
            mock_cls.return_value.create_time.return_value = 100.0
            result = probe_pid_identity(12345, 100.0)
        assert result.status is LLCRunStatus.RUNNING

    def test_mismatched_create_time_is_completed(self) -> None:
        """A pid alive under a DIFFERENT identity means THIS run is over."""
        with patch(_PSUTIL_PROCESS) as mock_cls:
            mock_cls.return_value.create_time.return_value = 200.0
            result = probe_pid_identity(12345, 100.0)
        assert result.status is LLCRunStatus.COMPLETED

    def test_no_such_process_is_completed(self) -> None:
        with patch(_PSUTIL_PROCESS, side_effect=psutil.NoSuchProcess(12345)):
            result = probe_pid_identity(12345, 100.0)
        assert result.status is LLCRunStatus.COMPLETED

    def test_access_denied_falls_back_to_probe_pid(self) -> None:
        with (
            patch(_PSUTIL_PROCESS, side_effect=psutil.AccessDenied(12345)),
            patch("os.kill", return_value=None),
        ):
            result = probe_pid_identity(12345, 100.0)
        assert result.status is LLCRunStatus.RUNNING


# ---------------------------------------------------------------------------
# _identity_verified (PR#16284 review)
# ---------------------------------------------------------------------------


class TestIdentityVerified:
    def test_none_is_never_verified(self) -> None:
        assert _identity_verified(12345, None) is False

    def test_matching_create_time_verified(self) -> None:
        with patch(_PSUTIL_PROCESS) as mock_cls:
            mock_cls.return_value.create_time.return_value = 100.0
            assert _identity_verified(12345, 100.0) is True

    def test_mismatched_create_time_not_verified(self) -> None:
        with patch(_PSUTIL_PROCESS) as mock_cls:
            mock_cls.return_value.create_time.return_value = 200.0
            assert _identity_verified(12345, 100.0) is False

    def test_psutil_error_not_verified(self) -> None:
        with patch(_PSUTIL_PROCESS, side_effect=psutil.NoSuchProcess(12345)):
            assert _identity_verified(12345, 100.0) is False


# ---------------------------------------------------------------------------
# _process_group_id — killpg ONLY when getpgid(pid) == pid (PR#16284 review)
# ---------------------------------------------------------------------------


class TestProcessGroupId:
    def test_leader_returns_its_own_pid(self) -> None:
        with patch("os.getpgid", return_value=555):
            assert _process_group_id(555) == 555

    def test_non_leader_returns_none(self) -> None:
        """Covers BOTH a foreign group's leader and our own — same guard either way."""
        with patch("os.getpgid", return_value=1):
            assert _process_group_id(555) is None

    def test_process_lookup_error_returns_none(self) -> None:
        with patch("os.getpgid", side_effect=ProcessLookupError):
            assert _process_group_id(555) is None

    def test_permission_error_returns_none(self) -> None:
        with patch("os.getpgid", side_effect=PermissionError):
            assert _process_group_id(555) is None


class TestExtractUsage:
    """Token-usage parsing from the stream-json result event (GH#10220)."""

    def test_sums_input_plus_cache(self) -> None:
        ev = {
            "type": "result",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 20,
                "cache_creation_input_tokens": 5,
            },
        }
        assert extract_usage(ev) == (125, 50)

    def test_basic_input_output(self) -> None:
        assert extract_usage({"usage": {"input_tokens": 10, "output_tokens": 3}}) == (10, 3)

    def test_missing_usage_returns_none(self) -> None:
        assert extract_usage({"type": "result"}) == (None, None)
        assert extract_usage({}) == (None, None)
        assert extract_usage(None) == (None, None)

    def test_all_zero_returns_none(self) -> None:
        assert extract_usage({"usage": {"input_tokens": 0, "output_tokens": 0}}) == (None, None)

    def test_non_int_values_ignored(self) -> None:
        # input_tokens "x" is non-int → counted as 0; output 7 still recorded.
        assert extract_usage({"usage": {"input_tokens": "x", "output_tokens": 7}}) == (0, 7)
