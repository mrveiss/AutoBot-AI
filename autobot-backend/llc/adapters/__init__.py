# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC adapters package (GH#8226 / GH#8227 / GH#8228 / GH#8258).

Public surface:
- ``LLCAdapter``            — structural Protocol every adapter satisfies
- ``AdapterRunStatus``      — unified status dataclass
- ``get_adapter``           — registry accessor (by adapter type string)
- ``register_adapter``      — registry mutator
- ``AutoBotAgentAdapter``   — wraps any AutoBot agent for LLC dispatch
- ``ClaudeCodeAdapter``     — runs Claude Code CLI sessions (GH#8258)
- ``get_adapter_for_agent`` — stub; concrete registry wired in GH#8225
"""

from typing import Optional

from .autobot_agent_adapter import AutoBotAgentAdapter
from .base import AdapterRunStatus, LLCAdapter, get_adapter, register_adapter
from .claude_code_adapter import ClaudeCodeAdapter

__all__ = [
    "AdapterRunStatus",
    "AutoBotAgentAdapter",
    "ClaudeCodeAdapter",
    "LLCAdapter",
    "get_adapter",
    "get_adapter_for_agent",
    "register_adapter",
]

# Register claude_code adapter under its canonical type key.
register_adapter("claude_code", ClaudeCodeAdapter())


async def get_adapter_for_agent(agent_id: str) -> Optional[LLCAdapter]:
    """Return the registered adapter for *agent_id*, or None if unregistered.

    Concrete registry is built in GH#8225 (HeartbeatScheduler). Until then,
    always returns None so LivenessMonitor and the runs API degrade gracefully
    to no-ops on cancel().
    """
    return None
