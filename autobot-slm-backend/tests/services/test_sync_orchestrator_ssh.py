# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for SyncOrchestrator._build_ssh_command (Issue #10277).

Regression guard: a stray ``-o`` with no ``key=value`` argument made ssh fail
with ``command-line line 0: no argument after keyword "-o"``, breaking every
node role-sync. These tests assert the produced argv is well-formed.
"""

from services.sync_orchestrator import SyncOrchestrator


def _build(port: int = 2222, user: str = "autobot", host: str = "10.0.0.5") -> list:
    # __new__ skips __init__ (which only creates a cache dir); _build_ssh_command
    # does not touch instance state, so this is a safe, side-effect-free build.
    orchestrator = SyncOrchestrator.__new__(SyncOrchestrator)
    return orchestrator._build_ssh_command(port, user, host)


def test_every_dash_o_has_keyvalue_argument():
    cmd = _build()
    for idx, token in enumerate(cmd):
        if token == "-o":
            assert idx + 1 < len(cmd), "trailing -o with no argument"
            value = cmd[idx + 1]
            assert "=" in value and not value.startswith("-"), f"-o not followed by key=value: {value!r}"


def test_port_flag_passed_correctly():
    cmd = _build(port=2222)
    assert "-p" in cmd
    assert cmd[cmd.index("-p") + 1] == "2222"


def test_target_host_is_last_argument():
    cmd = _build(user="u", host="h")
    assert cmd[-1] == "u@h"
