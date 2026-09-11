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

import asyncio
import json
import os
import signal
import tempfile
import time
from unittest.mock import AsyncMock, patch

import psutil
import pytest

from autobot_shared.eventually import eventually
from llc.adapters.subprocess_base import (
    ADAPTER_TIMEOUT_SECONDS,
    FIRST_OUTPUT_DEADLINE_SECONDS,
    SIGTERM_GRACE_SECONDS,
    STALL_DEADLINE_SECONDS,
    SubprocessLifecycleAdapter,
    resolve_cli_binary,
    resolve_first_output_deadline,
    resolve_stall_deadline,
    resolve_timeout,
)
from llc.models.enums import LLCRunStatus

# ---------------------------------------------------------------------------
# Minimal concrete adapter for exercising base-class paths
# ---------------------------------------------------------------------------


def _state_path(output_dir: str, run_id: str) -> str:
    return os.path.join(output_dir, f"base_state_{run_id.replace('/', '_')}.json")


_PSUTIL_PROCESS = "llc.adapters.subprocess_support.psutil.Process"


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


# ---------------------------------------------------------------------------
# resolve_first_output_deadline / resolve_stall_deadline — same 3-tier shape (GH#13099)
# ---------------------------------------------------------------------------


class TestResolveFirstOutputDeadline:
    def test_per_agent_override(self, monkeypatch) -> None:
        monkeypatch.setenv("AUTOBOT_LLC_FIRST_OUTPUT_DEADLINE_SECONDS", "9")
        assert resolve_first_output_deadline({"first_output_deadline_seconds": 3}) == 3

    def test_global_env(self, monkeypatch) -> None:
        monkeypatch.setenv("AUTOBOT_LLC_FIRST_OUTPUT_DEADLINE_SECONDS", "7")
        assert resolve_first_output_deadline({}) == 7

    def test_adapter_default(self, monkeypatch) -> None:
        monkeypatch.delenv("AUTOBOT_LLC_FIRST_OUTPUT_DEADLINE_SECONDS", raising=False)
        assert resolve_first_output_deadline({}) == FIRST_OUTPUT_DEADLINE_SECONDS == 120


class TestResolveStallDeadline:
    def test_per_agent_override(self, monkeypatch) -> None:
        monkeypatch.setenv("AUTOBOT_LLC_STALL_DEADLINE_SECONDS", "45")
        assert resolve_stall_deadline({"stall_deadline_seconds": 5}) == 5

    def test_global_env(self, monkeypatch) -> None:
        monkeypatch.setenv("AUTOBOT_LLC_STALL_DEADLINE_SECONDS", "30")
        assert resolve_stall_deadline({}) == 30

    def test_adapter_default(self, monkeypatch) -> None:
        monkeypatch.delenv("AUTOBOT_LLC_STALL_DEADLINE_SECONDS", raising=False)
        assert resolve_stall_deadline({}) == STALL_DEADLINE_SECONDS == 600


# ---------------------------------------------------------------------------
# resolve_cli_binary — configured path > PATH > common install dirs > None (GH#12478)
# ---------------------------------------------------------------------------


class TestResolveCliBinary:
    def test_configured_path_wins_over_which(self, tmp_path) -> None:
        """An existing, executable configured_path is used even if PATH also resolves it."""
        configured = tmp_path / "claude"
        configured.write_text("#!/bin/sh\n")
        configured.chmod(0o755)

        with patch("llc.adapters.subprocess_base.shutil.which", return_value="/usr/bin/claude"):
            resolved = resolve_cli_binary("claude", configured_path=str(configured))

        assert resolved == str(configured)

    def test_configured_path_missing_falls_back_to_which(self, tmp_path) -> None:
        """A configured_path that doesn't exist logs a warning and falls back."""
        missing = tmp_path / "does-not-exist" / "claude"

        with patch("llc.adapters.subprocess_base.shutil.which", return_value="/usr/bin/claude"):
            resolved = resolve_cli_binary("claude", configured_path=str(missing))

        assert resolved == "/usr/bin/claude"

    def test_which_wins_over_common_dirs(self, tmp_path) -> None:
        """A bare PATH hit is used before common install dirs are even checked."""
        common_dir = tmp_path / "common"
        common_dir.mkdir()
        (common_dir / "claude").write_text("#!/bin/sh\n")
        (common_dir / "claude").chmod(0o755)

        with patch("llc.adapters.subprocess_base.shutil.which", return_value="/usr/bin/claude"):
            resolved = resolve_cli_binary("claude", common_dirs=[str(common_dir)])

        assert resolved == "/usr/bin/claude"

    def test_falls_back_to_common_install_dir_when_which_misses(self, tmp_path) -> None:
        """PATH miss (which() -> None) falls through to a common install dir hit."""
        common_dir = tmp_path / "local-bin"
        common_dir.mkdir()
        binary = common_dir / "claude"
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)

        with patch("llc.adapters.subprocess_base.shutil.which", return_value=None):
            resolved = resolve_cli_binary("claude", common_dirs=[str(common_dir)])

        assert resolved == str(binary)

    def test_common_dirs_checked_in_order(self, tmp_path) -> None:
        """The first common dir containing the binary wins."""
        first_dir = tmp_path / "first"
        second_dir = tmp_path / "second"
        first_dir.mkdir()
        second_dir.mkdir()
        for d in (first_dir, second_dir):
            binary = d / "claude"
            binary.write_text("#!/bin/sh\n")
            binary.chmod(0o755)

        with patch("llc.adapters.subprocess_base.shutil.which", return_value=None):
            resolved = resolve_cli_binary("claude", common_dirs=[str(first_dir), str(second_dir)])

        assert resolved == str(first_dir / "claude")

    def test_non_executable_common_dir_file_skipped(self, tmp_path) -> None:
        """A file that exists but isn't executable is not treated as a resolution hit."""
        common_dir = tmp_path / "local-bin"
        common_dir.mkdir()
        (common_dir / "claude").write_text("not executable")
        (common_dir / "claude").chmod(0o644)

        with patch("llc.adapters.subprocess_base.shutil.which", return_value=None):
            resolved = resolve_cli_binary("claude", common_dirs=[str(common_dir)])

        assert resolved is None

    def test_returns_none_when_nowhere_found(self, tmp_path) -> None:
        """Genuinely absent everywhere: no configured path, no PATH hit, no common dir hit."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with patch("llc.adapters.subprocess_base.shutil.which", return_value=None):
            resolved = resolve_cli_binary("claude", common_dirs=[str(empty_dir)])

        assert resolved is None

    def test_default_common_dirs_include_local_bin_and_npm_global(self) -> None:
        """The default search list covers the documented per-user install locations."""
        with patch("llc.adapters.subprocess_base.shutil.which", return_value=None):
            # No filesystem hits expected (real home dir unlikely to have a
            # binary named this) — this just exercises the default-dirs path
            # without raising, proving the default list is well-formed.
            resolved = resolve_cli_binary("autobot-nonexistent-cli-gh12478")

        assert resolved is None


# ---------------------------------------------------------------------------
# CLI availability gate hooks — is_cli_available / cli_not_found_message (GH#12478)
# ---------------------------------------------------------------------------


class _CliRequiringAdapter(SubprocessLifecycleAdapter):
    _LOG_NAME = "CliRequiringAdapter"
    _state_path = staticmethod(_state_path)
    _required_cli = "claude"

    async def _invoke(self, agent_config, context):  # pragma: no cover - not exercised
        return "1/x"


class TestCliAvailabilityHooks:
    def test_no_required_cli_always_available(self) -> None:
        assert _DummyAdapter().is_cli_available() is True

    def test_available_when_which_resolves(self) -> None:
        adapter = _CliRequiringAdapter()
        with patch("llc.adapters.subprocess_base.shutil.which", return_value="/usr/bin/claude"):
            assert adapter.is_cli_available() is True

    def test_unavailable_when_nowhere_found(self, monkeypatch) -> None:
        adapter = _CliRequiringAdapter()
        with (
            patch("llc.adapters.subprocess_base.shutil.which", return_value=None),
            patch(
                "llc.adapters.subprocess_base._common_cli_search_dirs",
                return_value=["/nonexistent/gh12478/dir"],
            ),
        ):
            assert adapter.is_cli_available() is False

    def test_configured_path_used_by_availability_gate(self, tmp_path) -> None:
        """A subclass-provided _configured_cli_path() is honored by is_cli_available()."""
        configured = tmp_path / "claude"
        configured.write_text("#!/bin/sh\n")
        configured.chmod(0o755)

        class _ConfiguredAdapter(_CliRequiringAdapter):
            def _configured_cli_path(self):
                return str(configured)

        with patch("llc.adapters.subprocess_base.shutil.which", return_value=None):
            assert _ConfiguredAdapter().is_cli_available() is True

    def test_default_message_is_actionable(self) -> None:
        message = _CliRequiringAdapter().cli_not_found_message()
        assert "claude" in message
        assert "PATH" in message
        assert "install" in message.lower()

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
            with open(state_file, "w", encoding="utf-8") as fh:
                json.dump(state, fh)

            cancel_called = []

            adapter = _DummyAdapter()

            async def fake_cancel(agent_config, run_id):
                cancel_called.append(run_id)

            adapter.cancel = fake_cancel  # type: ignore[assignment]
            # PR#16284 review: _status() now probes liveness FIRST. No
            # create_time is recorded here, so probe_pid_identity falls back
            # to a plain liveness probe — force it alive so the test reaches
            # the timeout check deterministically, not by luck of a real PID.
            with patch("os.kill", return_value=None):
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
            # PR#16284 review: _cancel() now loads the state file and passes
            # its create_time to terminate_pid, which never signals without
            # it verifying — record one a mocked psutil.Process will confirm.
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump({"pid": 123, "session_id": "session-x", "create_time": 100.0}, f)

            # GH#13097: force the single-PID fallback so this test stays about the
            # SIGTERM/SIGKILL sequence, not process-group resolution (covered separately).
            with (
                patch("os.getpgid", side_effect=ProcessLookupError),
                patch("os.kill", side_effect=fake_kill),
                patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
                patch(_PSUTIL_PROCESS) as mock_psutil_cls,
            ):
                mock_psutil_cls.return_value.create_time.return_value = 100.0
                await adapter.cancel({"adapter_config": {"output_dir": td}}, "123/session-x")

        assert kill_signals[0] == (123, signal.SIGTERM)
        assert mock_sleep.await_count == SIGTERM_GRACE_SECONDS * 10
        assert (123, signal.SIGKILL) in kill_signals


# ---------------------------------------------------------------------------
# A dead process is judged by its exit, never as stalled (PR#16284 review,
# MEDIUM) — the stall/timeout checks apply only to a live, identity-verified
# process. Real processes: POSIX has no useful mock for "genuinely exited".
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDeadRunNeverReportsStalled:
    async def test_finished_run_polled_after_stall_deadline_is_completed(self) -> None:
        """A run that completed normally, polled long after its last write
        (e.g. after a backend outage), reports COMPLETED, not "stalled"."""
        proc = await asyncio.create_subprocess_exec("true", start_new_session=True)
        create_time = psutil.Process(proc.pid).create_time()
        await proc.wait()
        await eventually(lambda: not psutil.pid_exists(proc.pid))

        with tempfile.TemporaryDirectory() as td:
            output_file = os.path.join(td, "out.jsonl")
            with open(output_file, "w", encoding="utf-8") as fh:
                fh.write("hello\n")
            run_id = f"{proc.pid}/session-late"
            state = {
                "pid": proc.pid,
                "output_file": output_file,
                "started_at": time.time() - 9999,  # e.g. an outage-delayed poll
                "create_time": create_time,
                "timeout_seconds": 3600,
                "first_output_deadline_seconds": 1,
                "stall_deadline_seconds": 1,  # long expired relative to the write above
            }
            with open(_state_path(td, run_id), "w", encoding="utf-8") as fh:
                json.dump(state, fh)

            result = await _DummyAdapter().status({"adapter_config": {"output_dir": td}}, run_id)

        assert result.status == LLCRunStatus.COMPLETED

    async def test_reused_pid_is_also_judged_completed_not_stalled(self) -> None:
        """The same reorder covers PID reuse: a live process under a
        DIFFERENT identity is not this run -- reported COMPLETED, and never
        reaches the stall check that would otherwise try to signal it."""
        with tempfile.TemporaryDirectory() as td:
            output_file = os.path.join(td, "out.jsonl")
            with open(output_file, "w", encoding="utf-8") as fh:
                fh.write("hello\n")
            run_id = "424242/session-reused"
            state = {
                "pid": 424242,
                "output_file": output_file,
                "started_at": time.time() - 9999,
                "create_time": 100.0,
                "timeout_seconds": 3600,
                "first_output_deadline_seconds": 1,
                "stall_deadline_seconds": 1,
            }
            with open(_state_path(td, run_id), "w", encoding="utf-8") as fh:
                json.dump(state, fh)

            with patch(_PSUTIL_PROCESS) as mock_cls:
                mock_cls.return_value.create_time.return_value = 200.0  # different process
                result = await _DummyAdapter().status({"adapter_config": {"output_dir": td}}, run_id)

        assert result.status == LLCRunStatus.COMPLETED
