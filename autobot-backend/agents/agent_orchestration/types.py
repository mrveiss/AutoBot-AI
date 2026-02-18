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
RESEARCH_PATTERNS = {
    "search web",
    "research",
    "find online",
    "latest",
    "current",
    "recent",
}
KNOWLEDGE_PATTERNS = {"according to", "based on documents", "analyze", "summarize"}

# Issue #60: Routing patterns for specialized agents
DATA_ANALYSIS_PATTERNS = {
    "analyze data",
    "statistics",
    "statistical",
    "data analysis",
    "dataset",
    "correlation",
    "trend",
    "pattern detection",
    "metrics",
}
CODE_GENERATION_PATTERNS = {
    "generate code",
    "write code",
    "code for",
    "implement",
    "programming",
    "function that",
    "class that",
    "algorithm",
}
TRANSLATION_PATTERNS = {
    "translate",
    "translation",
    "in spanish",
    "in french",
    "in german",
    "in chinese",
    "in japanese",
    "to english",
    "language",
}
SUMMARIZATION_PATTERNS = {
    "summarize",
    "summary",
    "summarization",
    "key points",
    "tldr",
    "condense",
    "brief overview",
    "main ideas",
}
SENTIMENT_PATTERNS = {
    "sentiment",
    "emotion",
    "feeling",
    "tone",
    "opinion",
    "positive or negative",
    "mood",
    "sentiment analysis",
}
IMAGE_ANALYSIS_PATTERNS = {
    "image",
    "picture",
    "photo",
    "visual",
    "describe image",
    "what is in this",
    "object detection",
    "scene",
}
AUDIO_PROCESSING_PATTERNS = {
    "audio",
    "transcribe",
    "transcription",
    "speech",
    "recording",
    "voice",
    "sound",
    "podcast",
}


class AgentType(Enum):
    """Enumeration of available agent types."""

    CHAT = "chat"
    SYSTEM_COMMANDS = "system_commands"
    RAG = "rag"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    RESEARCH = "research"
    ORCHESTRATOR = "orchestrator"
    DATA_ANALYSIS = "data_analysis"
    CODE_GENERATION = "code_generation"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"
    SENTIMENT_ANALYSIS = "sentiment_analysis"
    IMAGE_ANALYSIS = "image_analysis"
    AUDIO_PROCESSING = "audio_processing"


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
    # Issue #60: Specialized agent capabilities
    AgentType.DATA_ANALYSIS: AgentCapability(
        agent_type=AgentType.DATA_ANALYSIS,
        model_size="3B",
        specialization="Data analysis and pattern detection",
        strengths=["Statistical analysis", "Pattern detection", "Trend identification"],
        limitations=["Large dataset processing", "Real-time streaming data"],
        resource_usage="Medium",
    ),
    AgentType.CODE_GENERATION: AgentCapability(
        agent_type=AgentType.CODE_GENERATION,
        model_size="3B",
        specialization="Programming assistance and code generation",
        strengths=["Code generation", "Code explanation", "Multi-language support"],
        limitations=["Complex system architecture", "Runtime debugging"],
        resource_usage="Medium",
    ),
    AgentType.TRANSLATION: AgentCapability(
        agent_type=AgentType.TRANSLATION,
        model_size="1B",
        specialization="Multi-language translation",
        strengths=[
            "Accurate translation",
            "Language detection",
            "Context preservation",
        ],
        limitations=["Rare languages", "Highly specialized jargon"],
        resource_usage="Low",
    ),
    AgentType.SUMMARIZATION: AgentCapability(
        agent_type=AgentType.SUMMARIZATION,
        model_size="3B",
        specialization="Text and document summarization",
        strengths=[
            "Concise summaries",
            "Key point extraction",
            "Document condensation",
        ],
        limitations=["Very long documents", "Technical precision"],
        resource_usage="Medium",
    ),
    AgentType.SENTIMENT_ANALYSIS: AgentCapability(
        agent_type=AgentType.SENTIMENT_ANALYSIS,
        model_size="1B",
        specialization="Sentiment and emotion classification",
        strengths=["Sentiment detection", "Emotion classification", "Tone analysis"],
        limitations=["Sarcasm detection", "Cultural nuance"],
        resource_usage="Low",
    ),
    AgentType.IMAGE_ANALYSIS: AgentCapability(
        agent_type=AgentType.IMAGE_ANALYSIS,
        model_size="3B",
        specialization="Image analysis and vision tasks",
        strengths=["Object detection", "Scene description", "Image classification"],
        limitations=["Video processing", "3D reconstruction"],
        resource_usage="Medium-High",
    ),
    AgentType.AUDIO_PROCESSING: AgentCapability(
        agent_type=AgentType.AUDIO_PROCESSING,
        model_size="3B",
        specialization="Audio transcription and analysis",
        strengths=["Transcription", "Speaker identification", "Audio classification"],
        limitations=["Real-time streaming", "Music transcription"],
        resource_usage="Medium-High",
    ),
}
