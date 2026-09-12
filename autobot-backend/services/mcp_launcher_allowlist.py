# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Launcher allowlist for admin-configured external stdio MCP servers (#11542).

A stdio MCP server is a shell command AutoBot spawns as a subprocess
(services.mcp_isolated_runtime). Letting an admin configure *any* command
would make the external-MCP-server admin CRUD an arbitrary remote-code-
execution primitive on the host running AutoBot. This module restricts the
leading executable to the small set of launchers the real MCP ecosystem
actually uses to run a third-party server: ``npx``/``uvx`` (fetch-and-run a
published package), ``python``/``python3``/``node`` (run an already-vendored
script), and ``docker`` (run a containerised server).

The allowlist is a code constant, not an env var: widening the set of
executables an admin can spawn is a code-review decision, not a runtime
config change (the same posture as _WORKER_ENV_ALLOW in
services/mcp_isolated_runtime.py).
"""

from __future__ import annotations

import os
import shlex

ALLOWED_LAUNCHERS = frozenset(
    {
        "npx",
        "uvx",
        "python",
        "python3",
        "node",
        "docker",
    }
)


class LauncherNotAllowedError(ValueError):
    """Raised when a configured stdio command's leading executable is not allowlisted."""


def validate_stdio_command(command: str) -> None:
    """Raise LauncherNotAllowedError unless *command*'s leading executable is allowlisted.

    ``command`` is the same shell-command string StdioTransport later splits
    and execs (skills/sync/mcp_transport.py) — validated here, at admin
    CRUD time, before it is ever persisted or spawned.
    """
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise LauncherNotAllowedError(f"could not parse stdio command: {exc}") from exc
    if not parts:
        raise LauncherNotAllowedError("stdio command is empty")

    launcher = os.path.basename(parts[0])
    if launcher not in ALLOWED_LAUNCHERS:
        raise LauncherNotAllowedError(
            f"launcher '{launcher}' is not allowed for external MCP servers; " f"allowed: {sorted(ALLOWED_LAUNCHERS)}"
        )
