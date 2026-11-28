# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""System-prompt assembly for ``LLMService.chat_optimized`` (extracted for function length, #620/#16845)."""

from __future__ import annotations

from typing import Awaitable, Callable, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


_VLLM_FALLBACK_MODEL = "meta-llama/Llama-3.2-3B-Instruct"


def vllm_default_model() -> str:
    """The configured vLLM model, read from the vLLM key directly so Ollama and vLLM never share a cache key (#4054)."""
    try:
        from config.manager import get_config_manager

        return get_config_manager().get("llm.vllm.default_model", _VLLM_FALLBACK_MODEL)
    except Exception:
        logger.warning("vLLM default model unreadable from config; using %s", _VLLM_FALLBACK_MODEL, exc_info=True)
        return _VLLM_FALLBACK_MODEL


async def _compressed_tool_descriptions(available_tools: List) -> Dict | None:
    """Compressed descriptions for ``available_tools``, or None (names only) when compression fails (#5827)."""
    from tools import get_tool_registry

    try:
        registry = get_tool_registry()
        tool_set = set(available_tools)
        uncompressed = {n: d for n, d in registry.get_raw_descriptions().items() if n in tool_set}
        compressed_map = await registry.get_compressed_descriptions()
        tool_descriptions = {n: d for n, d in compressed_map.items() if n in tool_set}
        uncompressed_bytes = sum(len(d) for d in uncompressed.values())
        compressed_bytes = sum(len(d) for d in tool_descriptions.values())
        saving_pct = (1 - compressed_bytes / uncompressed_bytes) * 100 if uncompressed_bytes else 0
        logger.debug(
            "[#5827] Tool desc savings: %d tools, %d → %d bytes (%.0f%% reduction)",
            len(tool_descriptions),
            uncompressed_bytes,
            compressed_bytes,
            saving_pct,
        )
        return tool_descriptions
    except Exception:
        logger.warning(
            "[#5827] compress_description failed; falling back to tool names only",
            exc_info=True,
        )
    return None


async def build_optimized_system_prompt(
    *,
    agent_type: str,
    user_message: str,
    session_id: str,
    user_name: str | None,
    user_role: str | None,
    available_tools: List | None,
    recent_context: str | None,
    additional_params: Dict | None,
    build_clauses: Callable[..., Awaitable[tuple[str | None, str | None]]],
) -> str:
    """The prefix-cache-optimised system prompt for ``chat_optimized``.

    ``build_clauses`` is ``LLMService._build_prompt_clauses`` (the async
    preference/skill lookups).
    """
    from agent_tier_classifier import get_base_prompt_for_agent
    from prompt_manager import get_optimized_prompt
    from tools import get_tool_registry

    # Issue #5870: default to full registry when caller omits available_tools.
    if available_tools is None:
        available_tools = get_tool_registry().get_available_tools()

    tool_descriptions = await _compressed_tool_descriptions(available_tools)

    # #12829: get_optimized_prompt accepts a preference clause (#10545) and a
    # skill clause (#12810), but nothing ever passed either — both halves were
    # built, tested and left disconnected, so learned tenant preferences and
    # ranked skills never reached a prompt. Both are async lookups, which is
    # why they are pre-fetched here rather than inside the sync assembler.
    # Each helper returns None on any failure, so prompt assembly is unaffected
    # when the aggregator or ranker is unavailable.
    preference_clause, skill_clause = await build_clauses(
        agent_type=agent_type,
        user_message=user_message,
        available_tools=available_tools,
        additional_params=additional_params,
    )

    system_prompt = get_optimized_prompt(
        base_prompt_key=get_base_prompt_for_agent(agent_type),
        session_id=session_id,
        user_name=user_name,
        user_role=user_role,
        available_tools=available_tools,
        recent_context=recent_context,
        additional_params=additional_params,
        tool_descriptions=tool_descriptions,
        preference_clause=preference_clause,
        skill_clause=skill_clause,
    )
    return system_prompt
