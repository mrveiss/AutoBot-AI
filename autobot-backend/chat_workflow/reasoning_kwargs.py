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

from autobot_shared.logging_manager import get_logger
from llm_shared.providers.reasoning_effort import map_effort_to_provider_params

logger = get_logger(__name__)

_INTERLEAVED_THINKING_BETA = "interleaved-thinking-2025-05-14"


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


def _thinking_kwargs(budget_tokens: int) -> Dict[str, Any]:
    """Anthropic extended-thinking request kwargs for *budget_tokens*."""
    return {
        "thinking": {"type": "enabled", "budget_tokens": budget_tokens},
        "max_tokens": max(budget_tokens + 1000, 8192),
        "temperature": 1,
        "betas": [_INTERLEAVED_THINKING_BETA],
    }


async def build_reasoning_api_kwargs(context: Dict[str, Any], selected_model: str) -> Dict[str, Any] | None:
    """Thinking-mode (#8993) or reasoning-effort (#9017) kwargs for this iteration, else ``None``.

    Effort is applied only when thinking mode is not already set (avoid double-config); a
    per-conversation override beats the user default, and 'auto' adds nothing.
    """
    is_claude = "claude" in selected_model.lower()
    if context.get("thinking_mode_enabled") and is_claude:
        budget_tokens = int(context.get("thinking_budget_tokens", 10000))
        logger.info("[#8993] Thinking mode enabled for model=%s budget_tokens=%d", selected_model, budget_tokens)
        return _thinking_kwargs(budget_tokens)

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
        return _thinking_kwargs(thinking_tokens)
    return effort_params
