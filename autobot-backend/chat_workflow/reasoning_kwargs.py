# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-iteration provider kwargs for thinking mode and reasoning effort (#8993, #9017).

Moved out of ``manager.py`` unchanged in behaviour, to make room under that file's size
ceiling for the failover seam (#19753): the module only ever shrinks.
"""

from __future__ import annotations

from typing import Any, Dict

from autobot_shared.chat_model_context import chat_think_field, note_session_thinking
from autobot_shared.logging_manager import get_logger
from chat_workflow.vision_capability import resolve_model_supports_thinking
from llm_shared.providers.anthropic_request import thinking_request_kwargs
from llm_shared.providers.reasoning_effort import map_effort_to_provider_params

logger = get_logger(__name__)


async def resolve_reasoning_effort(context: Dict[str, Any]) -> str:
    """Resolve reasoning effort with priority: per-request > user-default > 'auto'.

    Resolution order (#9017):
      1. context["reasoning_effort"] — per-conversation value from the request
      2. Redis user:{id}:preferences:reasoning_effort — account-level default
      3. 'auto' — no extra params, provider decides

    Invalid or missing values are returned as 'auto' (inert).
    """
    effort: str | None = context.get("reasoning_effort")
    if effort:
        return effort

    user_id: str | None = context.get("user_id")
    if user_id:
        try:
            from api.users import _get_user_preferences_from_redis

            prefs = await _get_user_preferences_from_redis(user_id)
            return prefs.reasoning_effort
        except Exception as exc:
            logger.warning("[#9017] Failed to load user reasoning_effort pref: %s", exc)

    return "auto"


def _thinking_kwargs(model: str, budget_tokens: int) -> Dict[str, Any]:
    """Anthropic thinking request kwargs for *model*: adaptive or fixed-budget, as the SSOT says (#20884)."""
    return {**thinking_request_kwargs(model, budget_tokens), "temperature": 1}


async def ollama_think_kwargs(model: str, endpoint: str, thinking_enabled: bool | None) -> Dict[str, bool]:
    """``{"think": bool}`` for a thinking-capable local model with a user-set toggle, else ``{}`` (#22258).

    The decision is ``chat_model_context.chat_think_field``; this only reads the model's capability from the runtime.
    """
    if thinking_enabled is None or "claude" in model.lower():
        return {}
    return chat_think_field(thinking_enabled, await resolve_model_supports_thinking(model, endpoint))


async def build_reasoning_api_kwargs(
    context: Dict[str, Any], selected_model: str, ollama_endpoint: str = "", session_id: str = ""
) -> Dict[str, Any] | None:
    """The provider kwargs of :func:`_provider_reasoning_kwargs` plus Ollama's top-level ``think`` (#22258)."""
    toggle = context.get("thinking_mode_enabled")
    note_session_thinking(session_id, toggle)  # the interpretation pass of this session carries no context
    think = await ollama_think_kwargs(selected_model, ollama_endpoint, toggle) if ollama_endpoint else {}
    kwargs = await _provider_reasoning_kwargs(context, selected_model)
    return {**(kwargs or {}), **think} or None


async def _provider_reasoning_kwargs(context: Dict[str, Any], selected_model: str) -> Dict[str, Any] | None:
    """Thinking-mode (#8993) or reasoning-effort (#9017) kwargs for this iteration, else ``None``.

    Effort is applied only when thinking mode is not already set (avoid double-config); a
    per-conversation override beats the user default, and 'auto' adds nothing.
    """
    is_claude = "claude" in selected_model.lower()
    if context.get("thinking_mode_enabled") and is_claude:
        budget_tokens = int(context.get("thinking_budget_tokens", 10000))
        logger.info("[#8993] Thinking mode enabled for model=%s budget_tokens=%d", selected_model, budget_tokens)
        return _thinking_kwargs(selected_model, budget_tokens)

    effort = await resolve_reasoning_effort(context)
    if not effort or effort == "auto":
        return None
    effort_params = map_effort_to_provider_params(effort, selected_model)
    if not effort_params:
        return None
    logger.info(
        "[#9017] Reasoning effort=%s applied for model=%s params=%s", effort, selected_model, list(effort_params)
    )
    thinking_tokens = effort_params.get("thinking_tokens")
    if thinking_tokens and is_claude:
        return _thinking_kwargs(selected_model, thinking_tokens)
    return effort_params
