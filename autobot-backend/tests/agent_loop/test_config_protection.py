# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the config-protection guard (GH#11148).

Acceptance criteria:
  - A write/edit/delete/move targeting a linter/formatter config is hard-blocked
    in ``_execute_tools``, BEFORE the approval gate.
  - Non-config writes and read/list tools are unaffected.
  - Mixed-purpose manifests (pyproject.toml, setup.cfg) are NOT blocked.
  - ``AUTOBOT_ALLOW_CONFIG_EDITS`` opts out of the guard.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_loop.config_protection import (
    config_edits_allowed,
    is_protected_config,
    protected_config_write,
)
from agent_loop.loop import AgentLoop
from agent_loop.types import AgentLoopConfig


def _make_loop() -> AgentLoop:
    event_stream = MagicMock()
    event_stream.get_latest = AsyncMock(return_value=[])
    event_stream.publish = AsyncMock()
    config = AgentLoopConfig(
        mandatory_think_enabled=False,
        think_on_completion=False,
        log_iterations=False,
    )
    return AgentLoop(event_stream=event_stream, config=config)


class TestIsProtectedConfig:
    @pytest.mark.parametrize(
        "path",
        [
            ".eslintrc.json",
            "frontend/.eslintrc.js",
            ".prettierrc",
            "/repo/.prettierrc.yaml",
            "ruff.toml",
            ".markdownlint.json",
            "commitlint.config.js",
            ".editorconfig",
            ".pre-commit-config.yaml",
            "mypy.ini",
            "biome.json",
        ],
    )
    def test_protected_paths_match(self, path: str) -> None:
        assert is_protected_config(path) is not None

    @pytest.mark.parametrize(
        "path",
        [
            "pyproject.toml",  # mixed-purpose: intentionally not protected
            "setup.cfg",  # mixed-purpose: intentionally not protected
            "autobot-backend/agent_loop/loop.py",
            "src/main.ts",
            "README.md",
            "config.json",
            "",
            None,
        ],
    )
    def test_non_config_paths_pass(self, path: str | None) -> None:
        assert is_protected_config(path) is None


class TestProtectedConfigWrite:
    def test_write_file_to_config_matches(self) -> None:
        tool = {"tool_name": "write_file", "args": {"file_path": ".eslintrc.json"}}
        assert protected_config_write(tool) == ".eslintrc.json"

    def test_edit_file_path_key_fallback(self) -> None:
        tool = {"tool_name": "edit_file", "args": {"path": "ruff.toml"}}
        assert protected_config_write(tool) == "ruff.toml"

    def test_read_file_is_ignored(self) -> None:
        tool = {"tool_name": "read_file", "args": {"file_path": ".eslintrc.json"}}
        assert protected_config_write(tool) is None

    def test_write_to_non_config_passes(self) -> None:
        tool = {"tool_name": "write_file", "args": {"file_path": "src/app.ts"}}
        assert protected_config_write(tool) is None


class TestConfigEditsAllowed:
    def test_default_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AUTOBOT_ALLOW_CONFIG_EDITS", raising=False)
        assert config_edits_allowed() is False

    def test_env_opt_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOBOT_ALLOW_CONFIG_EDITS", "1")
        assert config_edits_allowed() is True


class TestExecuteToolsIntegration:
    """End-to-end: a protected-config write is blocked before approval."""

    @pytest.mark.asyncio
    async def test_config_write_blocked_before_approval(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AUTOBOT_ALLOW_CONFIG_EDITS", raising=False)
        loop = _make_loop()
        loop._check_tool_call_repetition = MagicMock(return_value=None)
        loop._check_approvals = AsyncMock(return_value={})
        loop.tool_executor = MagicMock()

        result = await loop._execute_tools([{"tool_name": "write_file", "args": {"file_path": ".prettierrc"}}])

        assert "write_file" in result
        assert "config-protection" in result["write_file"]["error"].lower()
        loop._check_approvals.assert_not_awaited()
        loop.tool_executor.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_config_write_proceeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AUTOBOT_ALLOW_CONFIG_EDITS", raising=False)
        loop = _make_loop()
        loop._check_tool_call_repetition = MagicMock(return_value=None)
        # Stop right after the config check to prove the write passed it.
        loop._check_approvals = AsyncMock(return_value={"write_file": {"error": "stop"}})

        result = await loop._execute_tools([{"tool_name": "write_file", "args": {"file_path": "src/app.ts"}}])

        loop._check_approvals.assert_awaited_once()
        assert result == {"write_file": {"error": "stop"}}

    @pytest.mark.asyncio
    async def test_env_override_lets_config_write_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOBOT_ALLOW_CONFIG_EDITS", "1")
        loop = _make_loop()
        loop._check_tool_call_repetition = MagicMock(return_value=None)
        loop._check_approvals = AsyncMock(return_value={"write_file": {"error": "stop"}})

        result = await loop._execute_tools([{"tool_name": "write_file", "args": {"file_path": ".prettierrc"}}])

        loop._check_approvals.assert_awaited_once()
        assert result == {"write_file": {"error": "stop"}}
