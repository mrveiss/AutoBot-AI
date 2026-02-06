# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Orchestration Types Module

Issue #381: Extracted from agent_orchestrator.py god class refactoring.
Contains type definitions, enums, and routing pattern constants.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Set

if TYPE_CHECKING:
    from agents.base_agent import AgentHealth, BaseAgent


# Performance optimization: O(1) lookup for routing patterns (Issue #326)
CODE_SEARCH_TERMS = {"search", "find", "code", "function"}
CLASSIFICATION_TERMS = {"classify", "category", "type"}
GREETING_PATTERNS = {"hello", "hi", "how are you", "thank you", "goodbye"}
SYSTEM_COMMAND_PATTERNS = {
    "run",
    "execute",
    "command",
    "system",
    "shell",
    "terminal",
    "ps",
    "ls",
    "df",
}
RESEARCH_PATTERNS = {"search web", "research", "find online", "latest", "current", "recent"}
KNOWLEDGE_PATTERNS = {"according to", "based on documents", "analyze", "summarize"}


class AgentType(Enum):
    """Enumeration of available agent types."""

    CHAT = "chat"
    SYSTEM_COMMANDS = "system_commands"
    RAG = "rag"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    RESEARCH = "research"
    ORCHESTRATOR = "orchestrator"


@dataclass
class AgentCapability:
    """Describes an agent's capabilities and constraints."""

    agent_type: AgentType
    model_size: str
    specialization: str
    strengths: List[str]
    limitations: List[str]
    resource_usage: str


@dataclass
class DistributedAgentInfo:
    """Information about a distributed agent."""

    agent: "BaseAgent"
    health: "AgentHealth"
    last_health_check: datetime
    active_tasks: Set[str]


# Default agent capabilities configuration
DEFAULT_AGENT_CAPABILITIES = {
    AgentType.CHAT: AgentCapability(
        agent_type=AgentType.CHAT,
        model_size="1B",
        specialization="Conversational interactions",
        strengths=[
            "Quick responses",
            "Natural conversation",
            "Simple Q&A",
            "Greetings",
        ],
        limitations=[
            "Complex reasoning",
            "Multi-step tasks",
            "Technical analysis",
        ],
        resource_usage="Low",
    ),
    AgentType.SYSTEM_COMMANDS: AgentCapability(
        agent_type=AgentType.SYSTEM_COMMANDS,
        model_size="1B",
        specialization="System command generation",
        strengths=[
            "Shell commands",
            "System operations",
            "Security validation",
            "Command explanation",
        ],
        limitations=["Complex system analysis", "Multi-server orchestration"],
        resource_usage="Low",
    ),
    AgentType.RAG: AgentCapability(
        agent_type=AgentType.RAG,
        model_size="3B",
        specialization="Document synthesis",
        strengths=[
            "Information synthesis",
            "Document analysis",
            "Query reformulation",
            "Context ranking",
        ],
        limitations=["Real-time data", "Interactive tasks"],
        resource_usage="Medium-High",
    ),
    AgentType.KNOWLEDGE_RETRIEVAL: AgentCapability(
        agent_type=AgentType.KNOWLEDGE_RETRIEVAL,
        model_size="1B",
        specialization="Fast fact lookup",
        strengths=[
            "Quick searches",
            "Database queries",
            "Vector lookups",
            "Simple retrieval",
        ],
        limitations=["Complex synthesis", "Cross-document analysis"],
        resource_usage="Low",
    ),
    AgentType.RESEARCH: AgentCapability(
        agent_type=AgentType.RESEARCH,
        model_size="3B + Playwright",
        specialization="Web research coordination",
        strengths=[
            "Multi-step research",
            "Data extraction",
            "Source validation",
            "Web scraping",
        ],
        limitations=["Private data", "Real-time interaction"],
        resource_usage="High",
    ),
}
