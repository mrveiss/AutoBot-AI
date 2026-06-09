# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from .coordinator import (
    DistributedAgentCoordinator,
    get_distributed_agent_coordinator,
)
from .distributed_management import DistributedAgentManager
from .routing import AgentRouter
from .types import (
    AUDIO_PROCESSING_PATTERNS,
    CLASSIFICATION_TERMS,
    CODE_GENERATION_PATTERNS,
    CODE_SEARCH_TERMS,
    DATA_ANALYSIS_PATTERNS,
    DEFAULT_AGENT_CAPABILITIES,
    GREETING_PATTERNS,
    IMAGE_ANALYSIS_PATTERNS,
    KNOWLEDGE_PATTERNS,
    RESEARCH_PATTERNS,
    SENTIMENT_PATTERNS,
    SUMMARIZATION_PATTERNS,
    SYSTEM_COMMAND_PATTERNS,
    TRANSLATION_PATTERNS,
    AgentCapabilityDescriptor,
    AgentType,
    DistributedAgentInfo,
)

__all__ = [
    # Types and enums
    "AgentType",
    "AgentCapabilityDescriptor",
    "DistributedAgentInfo",
    "DEFAULT_AGENT_CAPABILITIES",
    # Pattern constants
    "CODE_SEARCH_TERMS",
    "CLASSIFICATION_TERMS",
    "GREETING_PATTERNS",
    "SYSTEM_COMMAND_PATTERNS",
    "RESEARCH_PATTERNS",
    "KNOWLEDGE_PATTERNS",
    # Issue #60: Specialized agent patterns
    "DATA_ANALYSIS_PATTERNS",
    "CODE_GENERATION_PATTERNS",
    "TRANSLATION_PATTERNS",
    "SUMMARIZATION_PATTERNS",
    "SENTIMENT_PATTERNS",
    "IMAGE_ANALYSIS_PATTERNS",
    "AUDIO_PROCESSING_PATTERNS",
    # Managers and handlers
    "DistributedAgentManager",
    "AgentRouter",
    "AgentExecutor",
    # Issue #3393: orchestrator moved from agents/agent_orchestrator.py
    # Issue #5040: renamed to DistributedAgentCoordinator
    "DistributedAgentCoordinator",
    "get_distributed_agent_coordinator",
]
