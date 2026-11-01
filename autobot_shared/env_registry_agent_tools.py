# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Env vars for the tool-execution time budgets (autobot_shared/tool_timeouts.py, #19729).

A sibling of ``env_registry_agent_runtime.py``, which sits too close to the file-size ceiling
to take them; it imports this module.
"""

from __future__ import annotations

from autobot_shared import env_registry_approvals  # noqa: F401  (registers the approval gate's vars, #18412)
from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TOOL_CALL_TIMEOUT_MS",
        type=int,
        default=30000,
        range=(1, None),
        description=(
            "Milliseconds one tool call may run before it is timed out, for both the agent "
            "loop and the parallel tool executor (autobot_shared/tool_timeouts.py, #19729). "
            "Raising it lets slow tools finish; lowering it fails a hung tool sooner. Minimum 1."
        ),
        component="agent_loop",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TOOL_GROUP_TIMEOUT_MS",
        type=int,
        default=60000,
        range=(1, None),
        description=(
            "Milliseconds one group of tool calls (one agent-loop iteration) may run, for both "
            "the agent loop and the parallel tool executor (autobot_shared/tool_timeouts.py, "
            "#19729). Keep it at least the per-call budget. Minimum 1."
        ),
        component="agent_loop",
    )
)
