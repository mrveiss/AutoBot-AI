# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tool-execution time budgets: the one home for both (#19729).

The agent loop (``agent_loop/types.AgentLoopConfig``) and the parallel tool executor
(``tools/parallel/executor.ParallelExecutorConfig``) each restated these as literals.
Both now read the constants here. Registered in ``env_registry_agent_tools.py``.
"""

from autobot_shared.env_utils import env_int_clamped


def clamp_group_timeout(call_ms: int, group_ms: int) -> int:
    """The one rule for a group budget: never below one call's budget (#19900).

    The group ``wait_for`` would otherwise cancel every call before its own budget.
    """
    return max(group_ms, call_ms)


#: One tool call's budget, in milliseconds. Override with AUTOBOT_TOOL_CALL_TIMEOUT_MS.
TOOL_CALL_TIMEOUT_MS: int = env_int_clamped("AUTOBOT_TOOL_CALL_TIMEOUT_MS", 30000, min_v=1)

#: The budget for one group of calls (one agent-loop iteration), in milliseconds.
#: Override with AUTOBOT_TOOL_GROUP_TIMEOUT_MS. Never below TOOL_CALL_TIMEOUT_MS (#19900):
#: the group wait_for would otherwise cancel every call before its own budget.
TOOL_GROUP_TIMEOUT_MS: int = clamp_group_timeout(
    TOOL_CALL_TIMEOUT_MS, env_int_clamped("AUTOBOT_TOOL_GROUP_TIMEOUT_MS", 60000, min_v=1)
)
