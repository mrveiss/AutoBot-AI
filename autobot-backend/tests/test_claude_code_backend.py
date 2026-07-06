# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the Claude Code / Claude Agent SDK execution provider (Issue #10550).

All tests mock the claude CLI / SDK so they run without the binary installed
or a live Anthropic key.  The three acceptance criteria tested here:
  1. Provider is ``unavailable`` when SDK/CLI absent (health_check → False).
  2. A task run streams ACTION + OBSERVATION + MESSAGE events.
  3. MCP-server config (URL, token) is passed to the CLI / SDK call.
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.execution.base_backend import ExecutionStatus, ExecutionTask
from services.execution.claude_code_backend import (
    ClaudeCodeBackend,
    _build_mcp_config,
    _parse_cli_line,
    build_claude_code_backend,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK = ExecutionTask(
    task_id="task-test-01",
    code="Write a hello-world function",
    language="natural_language",
    timeout_seconds=30,
)


def _make_backend(event_stream=None, **kwargs) -> ClaudeCodeBackend:
    return ClaudeCodeBackend(
        event_stream=event_stream,
        mcp_host="127.0.0.1",
        mcp_port=8200,
        mcp_token="dev:kb,memory,agents",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Guard-import / unavailability tests
# ---------------------------------------------------------------------------


class TestProviderUnavailableWhenCliAbsent:
    """Provider degrades to unavailable when claude CLI is not installed."""

    @pytest.mark.asyncio
    async def test_health_check_false_no_cli(self):
        """health_check() → False when claude is absent from PATH."""
        backend = _make_backend()
        with patch.dict(os.environ, {"AUTOBOT_FEATURE_CLAUDE_CODE_EXECUTION": "true"}):
            with patch("services.execution.claude_code_backend.shutil.which", return_value=None):
                with patch.object(backend, "_resolve_api_key", return_value="sk-test"):
                    healthy = await backend.health_check()
        assert healthy is False

    @pytest.mark.asyncio
    async def test_health_check_false_no_flag(self):
        """health_check() → False when feature flag is off."""
        backend = _make_backend()
        with patch.dict(os.environ, {"AUTOBOT_FEATURE_CLAUDE_CODE_EXECUTION": "false"}):
            with patch("services.execution.claude_code_backend.shutil.which", return_value="/usr/bin/claude"):
                with patch.object(backend, "_resolve_api_key", return_value="sk-test"):
                    healthy = await backend.health_check()
        assert healthy is False

    @pytest.mark.asyncio
    async def test_health_check_false_no_api_key(self):
        """health_check() → False when Anthropic API key is not configured."""
        backend = _make_backend()
        with patch.dict(os.environ, {"AUTOBOT_FEATURE_CLAUDE_CODE_EXECUTION": "true"}):
            with patch("services.execution.claude_code_backend.shutil.which", return_value="/usr/bin/claude"):
                with patch.object(backend, "_resolve_api_key", return_value=None):
                    healthy = await backend.health_check()
        assert healthy is False

    @pytest.mark.asyncio
    async def test_execute_returns_failed_when_unhealthy(self):
        """execute() returns FAILED status when backend is not healthy."""
        backend = _make_backend()
        with patch.object(backend, "is_healthy", new_callable=AsyncMock, return_value=False):
            result = await backend.execute(_TASK)
        assert result.status == ExecutionStatus.FAILED
        assert "unavailable" in result.stderr.lower()

    @pytest.mark.asyncio
    async def test_health_check_true_when_preconditions_met(self):
        """health_check() → True when flag + key + CLI are all present."""
        backend = _make_backend()
        with patch.dict(os.environ, {"AUTOBOT_FEATURE_CLAUDE_CODE_EXECUTION": "true"}):
            with patch("services.execution.claude_code_backend.shutil.which", return_value="/usr/bin/claude"):
                with patch.object(backend, "_resolve_api_key", return_value="sk-test"):
                    healthy = await backend.health_check()
        assert healthy is True


# ---------------------------------------------------------------------------
# MCP config tests
# ---------------------------------------------------------------------------


class TestMcpConfig:
    """MCP server config is built and passed to the CLI/SDK."""

    def test_build_mcp_config_structure(self):
        """_build_mcp_config produces the expected mcpServers structure."""
        cfg = _build_mcp_config("http://127.0.0.1:8200", "mytoken")
        assert "mcpServers" in cfg
        autobot = cfg["mcpServers"]["autobot"]
        assert autobot["url"] == "http://127.0.0.1:8200"
        assert autobot["transport"] == "http"
        assert autobot["headers"]["Authorization"] == "Bearer mytoken"

    @pytest.mark.asyncio
    async def test_cli_path_writes_mcp_config_file(self):
        """CLI invocation writes a temp MCP config file and passes its path."""
        backend = _make_backend()
        captured_cmd: list[list[str]] = []

        async def _fake_exec(*cmd, **kwargs):
            captured_cmd.append(list(cmd))
            return _make_mock_proc([])

        with patch.dict(os.environ, {"AUTOBOT_FEATURE_CLAUDE_CODE_EXECUTION": "true"}):
            with patch("services.execution.claude_code_backend.shutil.which", return_value="/usr/bin/claude"):
                with patch.object(backend, "_resolve_api_key", return_value="sk-test"):
                    with patch("asyncio.create_subprocess_exec", new=_fake_exec):
                        await backend._run_cli(_TASK)

        assert len(captured_cmd) == 1
        cmd = captured_cmd[0]
        assert "--mcp-config" in cmd
        mcp_idx = cmd.index("--mcp-config")
        cfg_path = cmd[mcp_idx + 1]
        # The file is deleted after _run_cli returns; just check the arg is present.
        assert cfg_path.endswith(".json")

    @pytest.mark.asyncio
    async def test_backend_info_includes_mcp_url(self):
        """get_backend_info() exposes the MCP URL for monitoring."""
        backend = ClaudeCodeBackend(mcp_host="10.0.0.1", mcp_port=9999)
        info = backend.get_backend_info()
        assert info["mcp_url"] == "http://10.0.0.1:9999"


# ---------------------------------------------------------------------------
# Event-streaming tests
# ---------------------------------------------------------------------------


class TestEventStreaming:
    """Steps (tool calls, results, messages) stream into the event bus."""

    @pytest.mark.asyncio
    async def test_cli_stream_emits_action_and_observation_events(self):
        """A tool-use / tool-result pair produces ACTION then OBSERVATION events."""
        published: list[Any] = []

        stream = MagicMock()
        stream.publish = AsyncMock(side_effect=lambda evt: published.append(evt))

        # Simulate two JSONL lines: tool_use then tool_result
        tool_use_line = json.dumps({
            "type": "assistant",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "tu-001",
                    "name": "kb.search",
                    "input": {"query": "hello"},
                }]
            },
        })
        tool_result_line = json.dumps({
            "type": "tool_result",
            "tool_use_id": "tu-001",
            "output": "42 results",
            "is_error": False,
        })
        result_line = json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "Done",
            "usage": {},
        })

        backend = _make_backend(event_stream=stream)
        lines = [tool_use_line, tool_result_line, result_line]

        async def _fake_exec(*a, **kw):
            return _make_mock_proc(lines)

        with patch.dict(os.environ, {"AUTOBOT_FEATURE_CLAUDE_CODE_EXECUTION": "true"}):
            with patch("services.execution.claude_code_backend.shutil.which", return_value="/usr/bin/claude"):
                with patch.object(backend, "_resolve_api_key", return_value="sk-test"):
                    with patch("asyncio.create_subprocess_exec", new=_fake_exec):
                        await backend._run_cli(_TASK)

        event_types = [e.event_type.name for e in published]
        assert "ACTION" in event_types, f"No ACTION event; got {event_types}"
        assert "OBSERVATION" in event_types, f"No OBSERVATION event; got {event_types}"

    @pytest.mark.asyncio
    async def test_cli_stream_emits_message_event_for_text(self):
        """An assistant text block produces a MESSAGE event."""
        published: list[Any] = []
        stream = MagicMock()
        stream.publish = AsyncMock(side_effect=lambda evt: published.append(evt))

        text_line = json.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "Hello from Claude"}]
            },
        })
        backend = _make_backend(event_stream=stream)

        async def _fake_exec(*a, **kw):
            return _make_mock_proc([text_line])

        with patch.dict(os.environ, {"AUTOBOT_FEATURE_CLAUDE_CODE_EXECUTION": "true"}):
            with patch("services.execution.claude_code_backend.shutil.which", return_value="/usr/bin/claude"):
                with patch.object(backend, "_resolve_api_key", return_value="sk-test"):
                    with patch("asyncio.create_subprocess_exec", new=_fake_exec):
                        await backend._run_cli(_TASK)

        event_types = [e.event_type.name for e in published]
        assert "MESSAGE" in event_types


# ---------------------------------------------------------------------------
# JSONL parser unit tests
# ---------------------------------------------------------------------------


class TestParseCLILine:
    """_parse_cli_line correctly maps JSONL shapes to _StepEvent."""

    def test_parses_tool_use(self):
        line = json.dumps({
            "type": "assistant",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "id-1",
                    "name": "kb.search",
                    "input": {"q": "x"},
                }]
            },
        })
        step = _parse_cli_line(line)
        assert step is not None
        assert step.kind == "tool_use"
        assert step.tool_name == "kb.search"
        assert step.tool_id == "id-1"

    def test_parses_tool_result(self):
        line = json.dumps({"type": "tool_result", "tool_use_id": "id-1", "output": "ok", "is_error": False})
        step = _parse_cli_line(line)
        assert step is not None
        assert step.kind == "tool_result"
        assert step.content["output"] == "ok"

    def test_parses_text_message(self):
        line = json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "hi"}]},
        })
        step = _parse_cli_line(line)
        assert step is not None
        assert step.kind == "message"
        assert step.content["text"] == "hi"

    def test_parses_result_event(self):
        line = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "done", "usage": {}})
        step = _parse_cli_line(line)
        assert step is not None
        assert step.kind == "complete"

    def test_parses_error_event(self):
        line = json.dumps({"type": "error", "error": {"message": "rate limited"}})
        step = _parse_cli_line(line)
        assert step is not None
        assert step.kind == "error"

    def test_returns_none_for_garbage(self):
        assert _parse_cli_line("not json at all !!!") is None
        assert _parse_cli_line("") is None
        assert _parse_cli_line(json.dumps({"type": "unknown_ev"})) is None

    def test_returns_none_for_empty_assistant_message(self):
        line = json.dumps({"type": "assistant", "message": {"content": []}})
        step = _parse_cli_line(line)
        assert step is None


# ---------------------------------------------------------------------------
# SDK path tests (SDK mocked)
# ---------------------------------------------------------------------------


class TestSDKPath:
    """SDK execution path — sdk itself is mocked."""

    @pytest.mark.asyncio
    async def test_sdk_path_streams_events_when_sdk_available(self):
        """When SDK available + use_sdk=True, events flow through _dispatch_sdk_event."""
        published: list[Any] = []
        stream = MagicMock()
        stream.publish = AsyncMock(side_effect=lambda evt: published.append(evt))

        backend = _make_backend(event_stream=stream, use_sdk=True)

        # Patch _SDK_AVAILABLE so the backend believes SDK is present.
        sdk_events = [
            {"type": "tool_use", "id": "s1", "name": "memory.search", "input": {"q": "test"}},
            {"type": "tool_result", "tool_use_id": "s1", "output": "result", "is_error": False},
            {"type": "text", "text": "All done."},
        ]

        async def _fake_sdk_stream(t, cfg):
            for ev in sdk_events:
                yield ev

        with patch("services.execution.claude_code_backend._SDK_AVAILABLE", True):
            with patch.object(backend, "_use_sdk", True):
                with patch.object(backend, "_sdk_stream", _fake_sdk_stream):
                    with patch.object(backend, "is_healthy", new_callable=AsyncMock, return_value=True):
                        result = await backend.execute(_TASK)

        assert result.status == ExecutionStatus.SUCCESS
        event_types = [e.event_type.name for e in published]
        assert "ACTION" in event_types
        assert "OBSERVATION" in event_types
        assert "MESSAGE" in event_types

    @pytest.mark.asyncio
    async def test_sdk_path_falls_back_to_cli_when_sdk_absent(self):
        """use_sdk=True but SDK absent → falls back to CLI path."""
        backend = _make_backend(use_sdk=True)
        cli_called = []

        async def _fake_cli(t):
            cli_called.append(True)
            return "output", "", True

        with patch("services.execution.claude_code_backend._SDK_AVAILABLE", False):
            with patch.object(backend, "_run_cli", _fake_cli):
                await backend._run_sdk(_TASK)

        assert cli_called, "Expected CLI fallback when SDK absent"


# ---------------------------------------------------------------------------
# Factory test
# ---------------------------------------------------------------------------


class TestBuildFactory:
    def test_factory_returns_claude_code_backend(self):
        backend = build_claude_code_backend()
        assert isinstance(backend, ClaudeCodeBackend)
        assert backend._mcp_port == 8200

    def test_factory_passes_event_stream(self):
        stream = MagicMock()
        backend = build_claude_code_backend(event_stream=stream)
        assert backend._event_stream is stream


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


def _async_iter_bytes(lines: list[str]):
    """Return an async generator that yields lines as bytes."""

    async def _gen():
        for line in lines:
            yield (line + "\n").encode("utf-8")

    return _gen()


def _make_mock_proc(lines: list[str]) -> MagicMock:
    """Build a mock subprocess object whose stdout yields *lines* as bytes."""
    proc = MagicMock()
    proc.stdout = _async_iter_bytes(lines)

    async def _read_stderr() -> bytes:
        return b""

    proc.stderr = MagicMock()
    proc.stderr.read = _read_stderr
    proc.returncode = 0
    proc.wait = AsyncMock()
    proc.kill = MagicMock()
    return proc
