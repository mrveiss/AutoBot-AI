# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Orchestration Package

Issue #381: Extracted from agent_orchestrator.py god class refactoring.
Provides modular agent orchestration with distributed and legacy support.

- types.py: Enums, dataclasses, and routing pattern constants
- distributed_management.py: Distributed agent registration and health monitoring
- routing.py: Routing decision logic and LLM-based routing
- agent_execution.py: Agent execution, result synthesis, and fallback handling
"""

from .agent_execution import AgentExecutor
from .distributed_management import DistributedAgentManager
from .routing import AgentRouter
from .types import (
    CLASSIFICATION_TERMS,
    CODE_SEARCH_TERMS,
    DEFAULT_AGENT_CAPABILITIES,
    GREETING_PATTERNS,
    KNOWLEDGE_PATTERNS,
    RESEARCH_PATTERNS,
    SYSTEM_COMMAND_PATTERNS,
    AgentCapability,
    AgentType,
    DistributedAgentInfo,
)

__all__ = [
    # Types and enums
    "AgentType",
    "AgentCapability",
    "DistributedAgentInfo",
    "DEFAULT_AGENT_CAPABILITIES",
    # Pattern constants
    "CODE_SEARCH_TERMS",
    "CLASSIFICATION_TERMS",
    "GREETING_PATTERNS",
    "SYSTEM_COMMAND_PATTERNS",
    "RESEARCH_PATTERNS",
    "KNOWLEDGE_PATTERNS",
    # Managers and handlers
    "DistributedAgentManager",
    "AgentRouter",
    "AgentExecutor",
]
