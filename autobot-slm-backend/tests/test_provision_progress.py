# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for provision_progress module (Issue #3033).

Covers:
- format_elapsed: boundary formatting (seconds, minutes, hours)
- _get_slow_task_hint: pattern matching and None for unknown tasks
- TaskProgressTracker: heartbeat timing, elapsed property, lifecycle
"""

import asyncio
import sys
from pathlib import Path

import pytest

# Ensure autobot-slm-backend is on sys.path for direct test runs.
_slm_root = Path(__file__).parent.parent
if str(_slm_root) not in sys.path:
    sys.path.insert(0, str(_slm_root))

from services.provision_progress import (
    TaskProgressTracker,
    _get_slow_task_hint,
    format_elapsed,
)

# ---------------------------------------------------------------------------
# format_elapsed
# ---------------------------------------------------------------------------


class TestFormatElapsed:
    def test_zero_seconds(self):
        assert format_elapsed(0) == "0s"

    def test_under_one_minute(self):
        assert format_elapsed(45) == "45s"

    def test_exactly_one_minute(self):
        assert format_elapsed(60) == "1m 0s"

    def test_minutes_and_seconds(self):
        assert format_elapsed(90) == "1m 30s"

    def test_exactly_one_hour(self):
        assert format_elapsed(3600) == "1h 0m 0s"

    def test_hours_minutes_seconds(self):
        assert format_elapsed(3665) == "1h 1m 5s"

    def test_fractional_seconds_truncated(self):
        # Fractional part is truncated via int(), not rounded
        assert format_elapsed(59.9) == "59s"


# ---------------------------------------------------------------------------
# _get_slow_task_hint
# ---------------------------------------------------------------------------


class TestGetSlowTaskHint:
    def test_ollama_pull_matches(self):
        hint = _get_slow_task_hint("ollama pull llama3")
        assert hint is not None
        assert "min" in hint

    def test_npm_install_matches(self):
        hint = _get_slow_task_hint("Run npm install for frontend")
        assert hint is not None

    def test_npm_ci_matches(self):
        hint = _get_slow_task_hint("npm ci --production")
        assert hint is not None

    def test_pip_install_matches(self):
        hint = _get_slow_task_hint("pip install -r requirements.txt")
        assert hint is not None

    def test_pip3_install_matches(self):
        hint = _get_slow_task_hint("pip3 install torch")
        assert hint is not None

    def test_vite_build_matches(self):
        hint = _get_slow_task_hint("Run vite build")
        assert hint is not None

    def test_apt_install_matches(self):
        hint = _get_slow_task_hint("apt-get install -y nginx")
        assert hint is not None

    def test_docker_pull_matches(self):
        hint = _get_slow_task_hint("docker pull ubuntu:22.04")
        assert hint is not None

    def test_git_clone_matches(self):
        hint = _get_slow_task_hint("git clone https://github.com/example/repo")
        assert hint is not None

    def test_case_insensitive(self):
        hint = _get_slow_task_hint("Ollama Pull MyModel")
        assert hint is not None

    def test_unknown_task_returns_none(self):
        assert _get_slow_task_hint("Restart autobot-backend service") is None

    def test_empty_string_returns_none(self):
        assert _get_slow_task_hint("") is None


# ---------------------------------------------------------------------------
# TaskProgressTracker
# ---------------------------------------------------------------------------


class TestTaskProgressTracker:
    @pytest.mark.asyncio
    async def test_heartbeat_is_sent_after_interval(self):
        """Tracker fires callback within 2x the interval."""
        received: list[dict] = []

        async def callback(progress: dict) -> None:
            received.append(progress)

        tracker = TaskProgressTracker("npm install", callback, heartbeat_interval=1)
        async with tracker:
            await asyncio.sleep(1.5)  # Wait slightly longer than interval

        assert received, "No heartbeat received"
        assert received[0]["stage"] == "heartbeat"
        assert "Still running" in received[0]["message"]

    @pytest.mark.asyncio
    async def test_heartbeat_message_includes_elapsed(self):
        """Heartbeat message contains elapsed time."""
        received: list[dict] = []

        async def callback(progress: dict) -> None:
            received.append(progress)

        tracker = TaskProgressTracker("pip install", callback, heartbeat_interval=1)
        async with tracker:
            await asyncio.sleep(1.5)

        assert received
        msg = received[0]["message"]
        assert "elapsed" in msg

    @pytest.mark.asyncio
    async def test_heartbeat_includes_slow_task_hint(self):
        """Heartbeat for a known slow task includes its duration estimate."""
        received: list[dict] = []

        async def callback(progress: dict) -> None:
            received.append(progress)

        tracker = TaskProgressTracker("ollama pull llama3", callback, heartbeat_interval=1)
        async with tracker:
            await asyncio.sleep(1.5)

        assert received
        msg = received[0]["message"]
        assert "min" in msg  # The ollama hint mentions minutes

    @pytest.mark.asyncio
    async def test_no_hint_for_unknown_task(self):
        """Heartbeat for unknown task shows task name but no 'est.' estimate."""
        received: list[dict] = []

        async def callback(progress: dict) -> None:
            received.append(progress)

        tracker = TaskProgressTracker("Restart nginx", callback, heartbeat_interval=1)
        async with tracker:
            await asyncio.sleep(1.5)

        assert received
        msg = received[0]["message"]
        # Task name always shown; no "est." hint for tasks not in SLOW_TASK_HINTS
        assert "Restart nginx" in msg
        assert "est." not in msg

    @pytest.mark.asyncio
    async def test_no_heartbeat_when_no_callback(self):
        """Tracker with callback=None does not raise and produces no output."""
        tracker = TaskProgressTracker("npm install", None, heartbeat_interval=1)
        async with tracker:
            await asyncio.sleep(0.1)
        # If we reach here without exception, the test passes.

    @pytest.mark.asyncio
    async def test_elapsed_seconds_advances(self):
        """elapsed_seconds increases while inside the context."""
        tracker = TaskProgressTracker("pip install", None, heartbeat_interval=60)
        async with tracker:
            await asyncio.sleep(0.1)
            elapsed = tracker.elapsed_seconds
        assert elapsed >= 0.05

    @pytest.mark.asyncio
    async def test_heartbeat_stops_on_exit(self):
        """No heartbeats are emitted after exiting the context manager."""
        received: list[dict] = []

        async def callback(progress: dict) -> None:
            received.append(progress)

        tracker = TaskProgressTracker("npm ci", callback, heartbeat_interval=1)
        async with tracker:
            await asyncio.sleep(1.5)

        count_on_exit = len(received)
        await asyncio.sleep(1.5)  # Wait another interval after exit

        assert len(received) == count_on_exit, "Heartbeats continued after context manager exited"

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_crash_tracker(self):
        """A raising callback is swallowed — tracker continues."""
        call_count = 0

        async def bad_callback(progress: dict) -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("simulated callback failure")

        tracker = TaskProgressTracker("pip install torch", bad_callback, heartbeat_interval=1)
        async with tracker:
            await asyncio.sleep(2.5)

        # Should have attempted at least 2 heartbeats without crashing
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_multiple_heartbeats_in_interval(self):
        """Multiple heartbeats fire over a longer wait period."""
        received: list[dict] = []

        async def callback(progress: dict) -> None:
            received.append(progress)

        tracker = TaskProgressTracker("docker pull ubuntu", callback, heartbeat_interval=1)
        async with tracker:
            await asyncio.sleep(3.5)

        assert len(received) >= 3, f"Expected at least 3 heartbeats, got {len(received)}"
