# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Agent Card Builder

Issue #961: Generates an A2A-compliant Agent Card from AutoBot's existing
AgentCapability and AgentType definitions. No duplication — the card is
derived directly from DEFAULT_AGENT_CAPABILITIES at call time.

All imports from the agents package are lazy (inside functions) so this
module can be imported without triggering the full backend stack.
"""

import logging

from .types import AgentCapabilities, AgentCard, AgentSkill

logger = logging.getLogger(__name__)

AUTOBOT_VERSION = "1.0.0"

# Curated examples per agent type (keyed by AgentType.value string)
_SKILL_EXAMPLES = {
    "chat": ["Hello!", "How are you?", "Thank you for your help"],
    "system_commands": [
        "Show me disk usage",
        "List running processes",
        "Run ls -la /tmp",
    ],
    "rag": [
        "Summarize the uploaded documents",
        "Based on documents, what is the deployment process?",
    ],
    "knowledge_retrieval": [
        "Find information about Redis configuration",
        "Look up the API endpoint for agents",
    ],
    "research": [
        "Research the latest FastAPI best practices",
        "Find current Python async patterns",
    ],
    "data_analysis": [
        "Analyze this dataset for trends",
        "Calculate correlation between these metrics",
    ],
    "code_generation": [
        "Write a Python function to parse JSON",
        "Generate a FastAPI endpoint for user authentication",
    ],
    "translation": [
        "Translate 'Hello World' to Spanish",
        "Translate this paragraph to French",
    ],
    "summarization": [
        "Summarize this article in 3 bullet points",
        "Give me the key points from this document",
    ],
    "sentiment_analysis": [
        "Is this review positive or negative?",
        "Analyze the sentiment of this customer feedback",
    ],
    "image_analysis": [
        "Describe what is in this image",
        "What objects are visible in this photo?",
    ],
    "audio_processing": [
        "Transcribe this audio recording",
        "Convert this speech to text",
    ],
}


def _get_skill_tags(agent_type_value: str) -> list:
    """
    Return a small set of routing-pattern tags for a given agent type value.

    Lazy-imports the pattern sets to avoid triggering the full agent stack
    at module import time.
    """
    try:
        from agents.agent_orchestration.types import (
            AUDIO_PROCESSING_PATTERNS,
            CODE_GENERATION_PATTERNS,
            DATA_ANALYSIS_PATTERNS,
            IMAGE_ANALYSIS_PATTERNS,
            KNOWLEDGE_PATTERNS,
            RESEARCH_PATTERNS,
            SENTIMENT_PATTERNS,
            SUMMARIZATION_PATTERNS,
            SYSTEM_COMMAND_PATTERNS,
            TRANSLATION_PATTERNS,
        )

        pattern_map = {
            "system_commands": list(SYSTEM_COMMAND_PATTERNS)[:3],
            "research": list(RESEARCH_PATTERNS)[:3],
            "knowledge_retrieval": list(KNOWLEDGE_PATTERNS)[:3],
            "data_analysis": list(DATA_ANALYSIS_PATTERNS)[:3],
            "code_generation": list(CODE_GENERATION_PATTERNS)[:3],
            "translation": list(TRANSLATION_PATTERNS)[:3],
            "summarization": list(SUMMARIZATION_PATTERNS)[:3],
            "sentiment_analysis": list(SENTIMENT_PATTERNS)[:3],
            "image_analysis": list(IMAGE_ANALYSIS_PATTERNS)[:3],
            "audio_processing": list(AUDIO_PROCESSING_PATTERNS)[:3],
        }
        return pattern_map.get(agent_type_value, [agent_type_value])
    except ImportError:
        return [agent_type_value]


def _capability_to_skill(agent_type_value: str, cap) -> AgentSkill:
    """Convert an AutoBot AgentCapability to an A2A AgentSkill."""
    return AgentSkill(
        id=agent_type_value,
        name=cap.specialization,
        description=(
            f"{cap.specialization}. "
            f"Strengths: {', '.join(cap.strengths[:2])}. "
            f"Resource usage: {cap.resource_usage}."
        ),
        tags=_get_skill_tags(agent_type_value),
        examples=_SKILL_EXAMPLES.get(agent_type_value, []),
    )


def build_agent_card(base_url: str) -> AgentCard:
    """
    Build the AutoBot A2A Agent Card.

    Derives all skills directly from DEFAULT_AGENT_CAPABILITIES so the card
    stays in sync with the actual agent roster automatically.

    All agent imports are lazy so this function is safe to call even if
    the full backend stack is not initialised.

    Args:
        base_url: Server base URL (e.g. "https://172.16.168.20:8443")

    Returns:
        AgentCard ready to be serialized as /.well-known/agent.json
    """
    try:
        from agents.agent_orchestration.types import DEFAULT_AGENT_CAPABILITIES

        skills = [
            _capability_to_skill(agent_type.value, cap)
            for agent_type, cap in DEFAULT_AGENT_CAPABILITIES.items()
        ]
    except ImportError as exc:
        logger.warning("Could not load agent capabilities for card: %s", exc)
        skills = []

    return AgentCard(
        name="AutoBot",
        description=(
            "AutoBot AI automation platform with multi-agent capabilities. "
            "Handles conversational AI, system commands, knowledge retrieval, "
            "web research, code generation, data analysis, and more."
        ),
        url=f"{base_url}/api/a2a",
        version=AUTOBOT_VERSION,
        skills=skills,
        capabilities=AgentCapabilities(
            streaming=False,
            push_notifications=False,
            state_transition_history=True,
        ),
        provider="mrveiss",
        documentation_url="https://github.com/mrveiss/AutoBot-AI",
    )
