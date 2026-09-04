# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Tier Classification System for vLLM Prefix Caching Optimization

This module classifies agents into tiers based on their shared prefix potential,
enabling maximum cache hit rates for vLLM prefix caching.

Tier 1 (Default Agents): 90-95% cache hit rate
Tier 2 (Analysis Agents): 70-80% cache hit rate
Tier 3 (Specialized Agents): 40-60% cache hit rate
Tier 4 (Orchestrator): 50-70% cache hit rate
"""

from enum import Enum
from functools import lru_cache
from typing import Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class AgentTier(Enum):
    """Agent tier classification for cache optimization."""

    TIER_1_DEFAULT = "tier1_default"  # 90-95% cache hit
    TIER_2_ANALYSIS = "tier2_analysis"  # 70-80% cache hit
    TIER_3_SPECIALIZED = "tier3_specialized"  # 40-60% cache hit
    TIER_4_ORCHESTRATOR = "tier4_orchestrator"  # 50-70% cache hit


# Agent type to tier mapping (#14194)
#
# Two independent rosters feed this map, and neither can see the other:
#
#   1. Claude Code dev subagents -- one name per .claude/agents/*.md file
#      (frontend-engineer, senior-backend-engineer, code-reviewer, ...).
#   2. AutoBot's own internal task-agent taxonomy -- AgentType in
#      agents/agent_orchestration/types.py, dispatched at runtime by
#      BaseModalityAgent subclasses (agents/*_agent.py) and the
#      orchestrator/workflow templates via
#      LLMService.chat_optimized(agent_type=...). AgentType values use
#      underscores ("audio_processing"); get_agent_tier() normalizes '_' to
#      '-' before lookup, so they are stored here in dash form.
#
# agent_tier_classifier_test.py asserts every member of BOTH rosters has an
# entry here (in both directions) so a name can no longer drift silently --
# see that file's module docstring for why it reads each roster without
# importing agent_tier_classifier or the agents package.
AGENT_TIER_MAP: Dict[str, AgentTier] = {
    # Tier 1: Default Implementation Agents (Highest Cache Hit Rate)
    "frontend-engineer": AgentTier.TIER_1_DEFAULT,
    "senior-backend-engineer": AgentTier.TIER_1_DEFAULT,
    "database-engineer": AgentTier.TIER_1_DEFAULT,
    "documentation-engineer": AgentTier.TIER_1_DEFAULT,
    "testing-engineer": AgentTier.TIER_1_DEFAULT,
    "devops-engineer": AgentTier.TIER_1_DEFAULT,
    "project-manager": AgentTier.TIER_1_DEFAULT,
    # AgentType.CHAT (#14194): the default conversational flow, shares the
    # most prefix of any task agent.
    "chat": AgentTier.TIER_1_DEFAULT,
    # Tier 2: Analysis Agents (High Cache Hit Rate)
    "code-reviewer": AgentTier.TIER_2_ANALYSIS,
    "performance-engineer": AgentTier.TIER_2_ANALYSIS,
    "security-auditor": AgentTier.TIER_2_ANALYSIS,
    "code-refactorer": AgentTier.TIER_2_ANALYSIS,
    # AgentType.RAG / AgentType.KNOWLEDGE_RETRIEVAL (#14194): retrieval +
    # synthesis, same cache profile as the other analysis agents.
    "rag": AgentTier.TIER_2_ANALYSIS,
    "knowledge-retrieval": AgentTier.TIER_2_ANALYSIS,
    # Tier 3: Specialized Agents (Moderate Cache Hit Rate)
    "code-skeptic": AgentTier.TIER_3_SPECIALIZED,
    "systems-architect": AgentTier.TIER_3_SPECIALIZED,
    "ai-ml-engineer": AgentTier.TIER_3_SPECIALIZED,
    "multimodal-engineer": AgentTier.TIER_3_SPECIALIZED,
    "frontend-designer": AgentTier.TIER_3_SPECIALIZED,
    "prd-writer": AgentTier.TIER_3_SPECIALIZED,
    "content-writer": AgentTier.TIER_3_SPECIALIZED,
    "memory-monitor": AgentTier.TIER_3_SPECIALIZED,
    "project-task-planner": AgentTier.TIER_3_SPECIALIZED,
    # #14194: added when .claude/agents/*.md gained these three definitions
    # (#14135, #14139) without a matching entry here. Narrow, non-default
    # tasks like the existing specialized agents above.
    "conversation-compacter": AgentTier.TIER_3_SPECIALIZED,
    "memory-curator": AgentTier.TIER_3_SPECIALIZED,
    "repo-sweeper": AgentTier.TIER_3_SPECIALIZED,
    # Issue #3389: task agents that call chat_completion_optimized
    "summarization": AgentTier.TIER_3_SPECIALIZED,
    "translation": AgentTier.TIER_3_SPECIALIZED,
    "sentiment-analysis": AgentTier.TIER_3_SPECIALIZED,
    "code-generation": AgentTier.TIER_3_SPECIALIZED,
    "audio-processing": AgentTier.TIER_3_SPECIALIZED,
    "image-analysis": AgentTier.TIER_3_SPECIALIZED,
    "data-analysis": AgentTier.TIER_3_SPECIALIZED,
    # AgentType.SYSTEM_COMMANDS / AgentType.RESEARCH (#14194): per-task tool
    # context (shell state, search results) keeps their shared prefix low.
    "system-commands": AgentTier.TIER_3_SPECIALIZED,
    "research": AgentTier.TIER_3_SPECIALIZED,
    # Tier 4: Orchestrator (Session-Specific)
    "orchestrator": AgentTier.TIER_4_ORCHESTRATOR,
}

# Tier to base prompt mapping
TIER_PROMPT_MAP: Dict[AgentTier, str] = {
    AgentTier.TIER_1_DEFAULT: "default.agent.system.main",
    AgentTier.TIER_2_ANALYSIS: "default.agent.system.main",  # Same base for now
    AgentTier.TIER_3_SPECIALIZED: "default.agent.system.main",  # Same base for now
    AgentTier.TIER_4_ORCHESTRATOR: "orchestrator.system_prompt",
}


@lru_cache(maxsize=64)
def get_agent_tier(agent_type: str) -> AgentTier:
    """
    Get the tier classification for an agent type.

    Issue #380: Added @lru_cache to avoid repeated dictionary lookups.

    Args:
        agent_type: The type of agent (e.g., 'frontend-engineer')

    Returns:
        AgentTier classification

    Example:
        >>> tier = get_agent_tier('frontend-engineer')
        >>> assert tier == AgentTier.TIER_1_DEFAULT
    """
    # Normalize agent type
    normalized_type = agent_type.lower().replace("_", "-")

    if normalized_type in AGENT_TIER_MAP:
        return AGENT_TIER_MAP[normalized_type]

    # Default to Tier 1 for unknown agents
    logger.warning(
        f"Unknown agent type '{agent_type}', defaulting to TIER_1_DEFAULT. "
        f"Consider adding to AGENT_TIER_MAP in agent_tier_classifier.py"
    )
    return AgentTier.TIER_1_DEFAULT


def get_base_prompt_for_agent(agent_type: str) -> str:
    """
    Get the optimal base prompt key for an agent type.

    This function determines which base prompt template provides
    the best cache hit rate for a given agent type.

    Args:
        agent_type: The type of agent (e.g., 'frontend-engineer')

    Returns:
        Base prompt key for the agent's tier

    Example:
        >>> prompt_key = get_base_prompt_for_agent('frontend-engineer')
        >>> assert prompt_key == 'default.agent.system.main'
    """
    tier = get_agent_tier(agent_type)
    return TIER_PROMPT_MAP[tier]


def get_cache_hit_expectation(agent_type: str) -> str:
    """
    Get the expected cache hit rate for an agent type.

    Args:
        agent_type: The type of agent

    Returns:
        Human-readable cache hit rate expectation

    Example:
        >>> rate = get_cache_hit_expectation('frontend-engineer')
        >>> assert '90-95%' in rate
    """
    tier = get_agent_tier(agent_type)

    cache_rates = {
        AgentTier.TIER_1_DEFAULT: "90-95%",
        AgentTier.TIER_2_ANALYSIS: "70-80%",
        AgentTier.TIER_3_SPECIALIZED: "40-60%",
        AgentTier.TIER_4_ORCHESTRATOR: "50-70%",
    }

    return cache_rates.get(tier, "Unknown")


def list_agents_by_tier(tier: AgentTier) -> list[str]:
    """
    List all agents in a specific tier.

    Args:
        tier: The AgentTier to filter by

    Returns:
        List of agent type strings in the tier

    Example:
        >>> agents = list_agents_by_tier(AgentTier.TIER_1_DEFAULT)
        >>> assert 'frontend-engineer' in agents
    """
    return [agent_type for agent_type, agent_tier in AGENT_TIER_MAP.items() if agent_tier == tier]


def get_tier_statistics() -> Dict[AgentTier, Dict[str, any]]:
    """
    Get statistics about agent tier distribution.

    Returns:
        Dictionary with tier statistics

    Example:
        >>> stats = get_tier_statistics()
        >>> assert stats[AgentTier.TIER_1_DEFAULT]['count'] == 8
    """
    from collections import Counter

    tier_counts = Counter(AGENT_TIER_MAP.values())

    return {
        tier: {
            "count": tier_counts[tier],
            "agents": list_agents_by_tier(tier),
            "cache_hit_rate": (
                get_cache_hit_expectation(list_agents_by_tier(tier)[0]) if list_agents_by_tier(tier) else "N/A"
            ),
            "base_prompt": TIER_PROMPT_MAP[tier],
        }
        for tier in AgentTier
    }


if __name__ == "__main__":
    # Print tier statistics when run directly
    logger.info("=== Agent Tier Classification Statistics ===\n")

    stats = get_tier_statistics()
    for tier, data in stats.items():
        logger.info(f"{tier.name}:")
        logger.info(f"  Count: {data['count']}")
        logger.info(f"  Cache Hit Rate: {data['cache_hit_rate']}")
        logger.info(f"  Base Prompt: {data['base_prompt']}")
        logger.info("  Agents: %s%s", ", ".join(data["agents"][:5]), "..." if len(data["agents"]) > 5 else "")
