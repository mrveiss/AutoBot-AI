# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the fact-forcing gate (GH#11149).

Acceptance criteria:
  - The first edit to an existing, not-yet-investigated file is blocked before
    the approval gate; reading it (this task) clears the gate.
  - A read + edit of the same file in one batch is allowed.
  - Creating a NEW (non-existent) file is never blocked.
  - Off by default; enabled by config or AUTOBOT_FACT_FORCING=1.
"""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_loop.fact_forcing import (
    fact_forcing_env_enabled,
    first_uninvestigated_edit,
    record_investigations,
)
from agent_loop.loop import AgentLoop
from agent_loop.types import AgentLoopConfig


def _make_loop(fact_forcing: bool = True) -> AgentLoop:
    event_stream = MagicMock()
    event_stream.get_latest = AsyncMock(return_value=[])
    event_stream.publish = AsyncMock()
    config = AgentLoopConfig(
        mandatory_think_enabled=False,
        think_on_completion=False,
        log_iterations=False,
        fact_forcing_enabled=fact_forcing,
    )
    return AgentLoop(event_stream=event_stream, config=config)


class TestRecordInvestigations:
    def test_records_read_paths(self) -> None:
        seen: set[str] = set()
        record_investigations(
            [
                {"tool_name": "read_file", "args": {"file_path": "a/b.py"}},
                {"tool_name": "grep_search", "args": {"path": "c/d.py"}},
                {"tool_name": "write_file", "args": {"file_path": "e/f.py"}},
            ],
            seen,
        )
        # Paths are stored realpath-normalized (GH#11179).
        assert os.path.realpath("a/b.py") in seen
        assert os.path.realpath("c/d.py") in seen
        assert os.path.realpath("e/f.py") not in seen  # writes are not investigations


class TestFirstUninvestigatedEdit:
    def test_existing_uninvestigated_edit_is_flagged(self) -> None:
        tool = {"tool_name": "edit_file", "args": {"file_path": "x.py"}}
        assert first_uninvestigated_edit(tool, set(), exists_fn=lambda _p: True) == "x.py"

    def test_investigated_edit_passes(self) -> None:
        tool = {"tool_name": "edit_file", "args": {"file_path": "x.py"}}
        # The investigated set holds realpath-normalized paths (GH#11179).
        seen = {os.path.realpath("x.py")}
        assert first_uninvestigated_edit(tool, seen, exists_fn=lambda _p: True) is None

    def test_new_file_is_never_flagged(self) -> None:
        tool = {"tool_name": "write_file", "args": {"file_path": "new.py"}}
        assert first_uninvestigated_edit(tool, set(), exists_fn=lambda _p: False) is None

    def test_non_edit_tool_passes(self) -> None:
        tool = {"tool_name": "read_file", "args": {"file_path": "x.py"}}
        assert first_uninvestigated_edit(tool, set(), exists_fn=lambda _p: True) is None

    def test_existence_error_fails_open(self) -> None:
        def _boom(_p: str) -> bool:
            raise OSError("nope")

        tool = {"tool_name": "edit_file", "args": {"file_path": "x.py"}}
        assert first_uninvestigated_edit(tool, set(), exists_fn=_boom) is None


class TestEnvToggle:
    def test_default_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AUTOBOT_FACT_FORCING", raising=False)
        assert fact_forcing_env_enabled() is False

    def test_env_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOBOT_FACT_FORCING", "1")
        assert fact_forcing_env_enabled() is True


class TestLoopIntegration:
    @pytest.mark.asyncio
    async def test_edit_existing_uninvestigated_is_blocked(self, tmp_path) -> None:
        target = tmp_path / "mod.py"
        target.write_text("x = 1\n", encoding="utf-8")
        loop = _make_loop(fact_forcing=True)
        loop._check_tool_call_repetition = MagicMock(return_value=None)
        loop._check_approvals = AsyncMock(return_value={})
        loop.tool_executor = MagicMock()

        result = await loop._execute_tools([{"tool_name": "edit_file", "args": {"file_path": str(target)}}])

        assert str(target) in next(iter(result.values()))["error"]
        assert "fact-forcing" in next(iter(result.values()))["error"].lower()
        loop._check_approvals.assert_not_awaited()
        loop.tool_executor.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_then_edit_same_batch_is_allowed(self, tmp_path) -> None:
        target = tmp_path / "mod.py"
        target.write_text("x = 1\n", encoding="utf-8")
        loop = _make_loop(fact_forcing=True)
        loop._check_tool_call_repetition = MagicMock(return_value=None)
        loop._check_approvals = AsyncMock(return_value={"edit_file": {"error": "stop"}})

        result = await loop._execute_tools(
            [
                {"tool_name": "read_file", "args": {"file_path": str(target)}},
                {"tool_name": "edit_file", "args": {"file_path": str(target)}},
            ]
        )

        loop._check_approvals.assert_awaited_once()
        assert result == {"edit_file": {"error": "stop"}}

    @pytest.mark.asyncio
    async def test_edit_after_prior_read_is_allowed(self, tmp_path) -> None:
        target = tmp_path / "mod.py"
        target.write_text("x = 1\n", encoding="utf-8")
        loop = _make_loop(fact_forcing=True)
        loop._check_tool_call_repetition = MagicMock(return_value=None)
        loop._check_approvals = AsyncMock(return_value={"edit_file": {"error": "stop"}})

        # Prior iteration: read the file (also passes through to approval).
        await loop._execute_tools([{"tool_name": "read_file", "args": {"file_path": str(target)}}])
        loop._check_approvals.reset_mock()
        # Later iteration: edit is now allowed.
        result = await loop._execute_tools([{"tool_name": "edit_file", "args": {"file_path": str(target)}}])

        loop._check_approvals.assert_awaited_once()
        assert result == {"edit_file": {"error": "stop"}}

    @pytest.mark.asyncio
    async def test_new_file_write_is_allowed(self, tmp_path) -> None:
        new_file = tmp_path / "brand_new.py"  # does not exist
        loop = _make_loop(fact_forcing=True)
        loop._check_tool_call_repetition = MagicMock(return_value=None)
        loop._check_approvals = AsyncMock(return_value={"write_file": {"error": "stop"}})

        result = await loop._execute_tools([{"tool_name": "write_file", "args": {"file_path": str(new_file)}}])

        loop._check_approvals.assert_awaited_once()
        assert result == {"write_file": {"error": "stop"}}

    @pytest.mark.asyncio
    async def test_disabled_by_default_allows_edit(self, tmp_path) -> None:
        target = tmp_path / "mod.py"
        target.write_text("x = 1\n", encoding="utf-8")
        loop = _make_loop(fact_forcing=False)
        loop._check_tool_call_repetition = MagicMock(return_value=None)
        loop._check_approvals = AsyncMock(return_value={"edit_file": {"error": "stop"}})

        result = await loop._execute_tools([{"tool_name": "edit_file", "args": {"file_path": str(target)}}])

        loop._check_approvals.assert_awaited_once()
        assert result == {"edit_file": {"error": "stop"}}

    @pytest.mark.asyncio
    async def test_env_enables_when_config_off(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AUTOBOT_FACT_FORCING", "1")
        target = tmp_path / "mod.py"
        target.write_text("x = 1\n", encoding="utf-8")
        loop = _make_loop(fact_forcing=False)
        loop._check_tool_call_repetition = MagicMock(return_value=None)
        loop._check_approvals = AsyncMock(return_value={})
        loop.tool_executor = MagicMock()

        result = await loop._execute_tools([{"tool_name": "edit_file", "args": {"file_path": str(target)}}])

        assert "fact-forcing" in next(iter(result.values()))["error"].lower()
        loop._check_approvals.assert_not_awaited()
