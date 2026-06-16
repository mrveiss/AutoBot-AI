# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC adapters package (GH#8226 / GH#8227 / GH#8228 / GH#8258 / GH#9008 / GH#9033).

Public surface:
- ``LLCAdapter``                    — structural Protocol every adapter satisfies
- ``AdapterRunStatus``              — unified status dataclass
- ``get_adapter``                   — registry accessor (by adapter type string)
- ``register_adapter``              — registry mutator
- ``AutoBotAgentAdapter``           — wraps any AutoBot agent for LLC dispatch
- ``ClaudeCodeAdapter``             — runs Claude Code CLI sessions (GH#8258)
- ``ClaudeCodeSubscriptionAdapter`` — Claude Code subscription mode (GH#9033)
- ``CopilotLocalAdapter``           — wraps local ``gh copilot`` CLI sessions (GH#9008)
- ``CopilotSubscriptionAdapter``    — GitHub Copilot subscription mode (GH#9033)
- ``CodexSubscriptionAdapter``      — OpenAI Codex subscription stub (GH#9033)
- ``get_adapter_for_agent``         — stub; concrete registry wired in GH#8225
"""

from typing import Optional

from .autobot_agent_adapter import AutoBotAgentAdapter
from .base import (
    AdapterRunStatus,
    LLCAdapter,
    get_adapter,
    register_adapter,
    registered_adapter_types,
)
from .claude_code_adapter import ClaudeCodeAdapter
from .claude_code_subscription_adapter import ClaudeCodeSubscriptionAdapter
from .codex_subscription_adapter import CodexSubscriptionAdapter
from .copilot_local_adapter import CopilotLocalAdapter
from .copilot_subscription_adapter import CopilotSubscriptionAdapter

__all__ = [
    "AdapterRunStatus",
    "AutoBotAgentAdapter",
    "ClaudeCodeAdapter",
    "ClaudeCodeSubscriptionAdapter",
    "CodexSubscriptionAdapter",
    "CopilotLocalAdapter",
    "CopilotSubscriptionAdapter",
    "LLCAdapter",
    "get_adapter",
    "get_adapter_for_agent",
    "register_adapter",
    "registered_adapter_types",
]

# Register adapters under their canonical type keys.
register_adapter("claude_code", ClaudeCodeAdapter())
register_adapter("claude_code_subscription", ClaudeCodeSubscriptionAdapter())
register_adapter("copilot_local", CopilotLocalAdapter())
register_adapter("copilot_subscription", CopilotSubscriptionAdapter())
register_adapter("codex_subscription", CodexSubscriptionAdapter())


async def get_adapter_for_agent(agent_id: str) -> Optional[LLCAdapter]:
    """Return the registered adapter for *agent_id*, or None if unregistered.

    Concrete registry is built in GH#8225 (HeartbeatScheduler). Until then,
    always returns None so LivenessMonitor and the runs API degrade gracefully
    to no-ops on cancel().
    """
    return None
