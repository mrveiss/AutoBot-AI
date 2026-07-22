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

import importlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Load the REAL services.sync_orchestrator (#11737) ────────────────────────
# The slm-backend root conftest stubs ``services.sync_orchestrator`` as a
# MagicMock (it is an api/code_sync.py import), so a bare import here would
# hand ``SyncOrchestrator.__new__`` a mock: ``TypeError: issubclass() arg 1
# must be a class``.  Pop the stub, import the real module through the hollow
# ``services`` package (its own heavy deps — sqlalchemy, models.database,
# services.database — stay satisfied by the conftest stubs), then restore the
# stub so sibling test files and api/* tests are unaffected (#11478 pattern).
_SO_KEY = "services.sync_orchestrator"
_orig_so = sys.modules.get(_SO_KEY)
sys.modules.pop(_SO_KEY, None)
try:
    _so_mod = importlib.import_module(_SO_KEY)
finally:
    if _orig_so is not None:
        sys.modules[_SO_KEY] = _orig_so
    else:
        sys.modules.pop(_SO_KEY, None)

SyncOrchestrator = _so_mod.SyncOrchestrator


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


# The ssh builders check Path(SSH_KEY_PATH).exists() for the optional `-i`
# flag.  The default key path lives under the autobot ssh dir — unreadable on
# dev boxes, where Path.exists() propagates PermissionError (EACCES is not in
# pathlib's ignored-errno set).  Pin the module global to a guaranteed-absent
# path so the check is a deterministic False in every environment; the argv
# assertions below are about `-o`/`-p` shape, not the key flag.
_MISSING_KEY_PATH = "/nonexistent-test-dir/autobot_key"


def test_build_ssh_command_argv_is_wellformed():
    with patch.object(_so_mod, "SSH_KEY_PATH", _MISSING_KEY_PATH):
        cmd = _orchestrator()._build_ssh_command(2222, "autobot", "10.0.0.5")
    _assert_ssh_argv_wellformed(cmd)


def test_build_ssh_command_port_and_target():
    with patch.object(_so_mod, "SSH_KEY_PATH", _MISSING_KEY_PATH):
        cmd = _orchestrator()._build_ssh_command(2222, "u", "h")
    assert "-p" in cmd and cmd[cmd.index("-p") + 1] == "2222"
    assert cmd[-1] == "u@h"


@pytest.mark.asyncio
async def test_get_current_git_commit_argv_is_wellformed():
    """_get_current_git_commit must also build a valid ssh argv (#10277)."""
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(b"a" * 40 + b"\n", b""))
    proc.returncode = 0
    # NOTE: sys.modules holds the conftest MagicMock stub for
    # services.sync_orchestrator (restored above), so a string patch target
    # would patch the stub, not the module under test.  _so_mod.asyncio IS the
    # stdlib asyncio module the real code resolves at call time — patch there.
    with (
        patch.object(_so_mod, "SSH_KEY_PATH", _MISSING_KEY_PATH),
        patch.object(
            _so_mod.asyncio,
            "create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ) as mock_exec,
    ):
        await _orchestrator()._get_current_git_commit("10.0.0.5", "autobot", "/home/autobot/code")  # noqa: ssot-path
    _assert_ssh_argv_wellformed(list(mock_exec.call_args[0]))
