# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Env vars of the bind-vs-dialed backend host split and the desktop-stream settings (#18810, #22146).

Registered by import: ``env_registry_backend_services`` imports this module, as it does its siblings.
"""

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_BACKEND_BIND_HOST",
        type=str,
        default="127.0.0.1",
        description="Address the backend listens on (0.0.0.0 for all interfaces); not a client host (#18810).",
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MCP_BRIDGE_PROBE_TIMEOUT_S",
        type=float,
        default=3.0,
        description="Seconds one MCP bridge availability or tool probe may take (api/mcp_registry.py).",
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_VNC_BASE_PORT",
        type=int,
        default=5900,
        description="RFB base port; a desktop session listens on this plus its X display number (#22146).",
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_WEBSOCKIFY_SEARCH_PATH",
        type=str,
        default="/usr/bin:/usr/local/bin",
        description="Directories searched for the websockify binary when it is not on PATH (#22146).",
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_NOVNC_BIND_HOST",
        type=str,
        default="127.0.0.1",
        description="Address a desktop session's websockify listens on; loopback unless a remote viewer needs it.",
        component="backend",
    )
)
