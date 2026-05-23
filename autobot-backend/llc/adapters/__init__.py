"""LLC adapters package (GH#8226 / GH#8227).

Public surface:
- ``LLCAdapter``          — structural Protocol every adapter satisfies
- ``AdapterRunStatus``    — unified status dataclass
- ``get_adapter``         — registry accessor
- ``register_adapter``    — registry mutator
- ``AutoBotAgentAdapter`` — wraps any AutoBot agent for LLC dispatch
"""

from .autobot_agent_adapter import AutoBotAgentAdapter
from .base import AdapterRunStatus, LLCAdapter, get_adapter, register_adapter

__all__ = [
    "AdapterRunStatus",
    "AutoBotAgentAdapter",
    "LLCAdapter",
    "get_adapter",
    "register_adapter",
]
