# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Env vars for the tool-execution time budgets (autobot_shared/tool_timeouts.py, #19729).

A sibling of ``env_registry_agent_runtime.py``, which sits too close to the file-size ceiling
to take them; it imports this module. It also holds the chat-graph and ask-human vars
(autobot_shared/ssot_chat_graph_settings.py, #21024); ``AUTOBOT_ASK_HUMAN_TIMEOUT_SECONDS`` stays
registered in ``env_registry_agent_runtime.py`` (one registration).
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
            "#19729, #19900). Never below the per-call budget: a smaller value is raised to "
            "AUTOBOT_TOOL_CALL_TIMEOUT_MS where it is read. Minimum 1."
        ),
        component="agent_loop",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ASK_HUMAN_ESCALATION_POLICY",
        type=str,
        default="abandon",
        description=(
            "What the agent loop does when an ask-human question times out: "
            "abandon, default or re_ask (#21024); any other value fails config load. Defined once in SSOT "
            "(config.llm.ask_human_escalation_policy)."
        ),
        component="agent_loop",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_PLANNER_ENABLED",
        type=bool,
        default=False,
        description=(
            "Enables the planner node in the chat graph, the canonical loop "
            "(#21023, #20846). Off by default; enabling adds planning to chat turns."
        ),
        component="chat_workflow",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_PLANNER_TIMEOUT_SECONDS",
        type=int,
        default=30,
        description=(
            "Seconds the chat planner may take to write a plan (#21023); past it the turn runs " "without a plan."
        ),
        component="chat_workflow",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_PLANNER_MIN_MESSAGE_CHARS",
        type=int,
        default=24,
        description=(
            "Chat turns shorter than this many characters skip the planner, which otherwise adds one "
            "LLM call (bounded by AUTOBOT_CHAT_PLANNER_TIMEOUT_SECONDS) before the first token (#21023)."
        ),
        component="chat_workflow",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_STALL_ESCALATION",
        type=str,
        default="stop",
        description=(
            "What the chat graph does when a turn stalls: stop halts the turn, "
            "ask escalates to the human (#21022, #20846); any other value fails config load."
        ),
        component="chat_workflow",
    )
)
