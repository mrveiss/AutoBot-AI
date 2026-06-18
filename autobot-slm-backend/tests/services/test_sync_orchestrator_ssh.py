# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for SyncOrchestrator ssh command construction (Issue #10277).

Regression guard: stray ``-o`` tokens with no ``key=value`` argument made ssh
fail with ``command-line line 0: no argument after keyword "-o"``, breaking node
role-sync (_build_ssh_command) and source-commit lookup (_get_current_git_commit).
These tests assert every ssh argv built in the orchestrator is well-formed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.sync_orchestrator import SyncOrchestrator


def _assert_ssh_argv_wellformed(cmd: list) -> None:
    """Every ``-o`` must be followed by a ``key=value`` token (never a bare flag)."""
    for idx, token in enumerate(cmd):
        if token == "-o":
            assert idx + 1 < len(cmd), f"trailing -o with no argument: {cmd!r}"
            value = cmd[idx + 1]
            assert "=" in value and not value.startswith("-"), f"-o not followed by key=value: {value!r} in {cmd!r}"


def _orchestrator() -> SyncOrchestrator:
    # __new__ skips __init__ (which only creates a cache dir); the ssh builders
    # do not touch instance state, so this is a safe, side-effect-free build.
    return SyncOrchestrator.__new__(SyncOrchestrator)


def test_build_ssh_command_argv_is_wellformed():
    cmd = _orchestrator()._build_ssh_command(2222, "autobot", "10.0.0.5")
    _assert_ssh_argv_wellformed(cmd)


def test_build_ssh_command_port_and_target():
    cmd = _orchestrator()._build_ssh_command(2222, "u", "h")
    assert "-p" in cmd and cmd[cmd.index("-p") + 1] == "2222"
    assert cmd[-1] == "u@h"


@pytest.mark.asyncio
async def test_get_current_git_commit_argv_is_wellformed():
    """_get_current_git_commit must also build a valid ssh argv (#10277)."""
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(b"a" * 40 + b"\n", b""))
    proc.returncode = 0
    with patch(
        "services.sync_orchestrator.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=proc),
    ) as mock_exec:
        await _orchestrator()._get_current_git_commit("10.0.0.5", "autobot", "/home/autobot/code")
    _assert_ssh_argv_wellformed(list(mock_exec.call_args[0]))
