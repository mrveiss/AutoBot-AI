# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Orchestrator — backward-compatibility shim.

Issue #3393: The implementation has been moved into the agent_orchestration/
package (agents/agent_orchestration/coordinator.py).  This file re-exports the
public API so that any remaining callers continue to work during the transition.

Do NOT add new code here.  Import directly from agents.agent_orchestration instead.
"""

# Re-export entire public API from the consolidated package
from agents.agent_orchestration import (  # noqa: F401
    CLASSIFICATION_TERMS,
    CODE_SEARCH_TERMS,
    DEFAULT_AGENT_CAPABILITIES,
    GREETING_PATTERNS,
    KNOWLEDGE_PATTERNS,
    RESEARCH_PATTERNS,
    SYSTEM_COMMAND_PATTERNS,
    AgentCapability,
    AgentExecutor,
    AgentOrchestrator,
    AgentRouter,
    AgentType,
    DistributedAgentInfo,
    DistributedAgentManager,
    get_agent_orchestrator,
)

__all__ = [
    # Types
    "AgentType",
    "AgentCapability",
    "DistributedAgentInfo",
    # Main class
    "AgentOrchestrator",
    # Singleton access
    "get_agent_orchestrator",
    # Availability flags (kept for API surface)
    "DEFAULT_AGENT_CAPABILITIES",
    "CODE_SEARCH_TERMS",
    "CLASSIFICATION_TERMS",
    "GREETING_PATTERNS",
    "SYSTEM_COMMAND_PATTERNS",
    "RESEARCH_PATTERNS",
    "KNOWLEDGE_PATTERNS",
    # Managers
    "DistributedAgentManager",
    "AgentRouter",
    "AgentExecutor",
]
