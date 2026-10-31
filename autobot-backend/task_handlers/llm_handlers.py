# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
LLM-related Task Handlers

Issue #322: Refactored to use TaskExecutionContext to eliminate data clump pattern.
"""

from typing import Any, Dict

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.models.task_result import task_error, task_success
from llm_shared.models import LLMResponse
from models.task_context import TaskExecutionContext

from .base import TaskHandler

logger = get_logger(__name__)

_ALLOWED_CHAT_KWARGS = frozenset({"temperature", "max_tokens", "top_p"})
#: Ceiling on ``max_tokens`` a task payload may request.
LLM_TASK_MAX_TOKENS_CAP = env_int("AUTOBOT_LLM_TASK_MAX_TOKENS_CAP", 4096)


def _allowed_chat_kwargs(payload_kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """The payload's sampling options a task may set; everything else is dropped by name (#19649).

    A task payload must not choose the provider, the conversation, or an unbounded
    ``max_tokens``: those decide whose quota is spent and how much.
    """
    allowed: Dict[str, Any] = {}
    dropped = []
    for key, value in (payload_kwargs or {}).items():
        numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
        if key in _ALLOWED_CHAT_KWARGS and numeric:
            allowed[key] = value
        else:
            dropped.append(key)
    if "max_tokens" in allowed:
        allowed["max_tokens"] = min(int(allowed["max_tokens"]), LLM_TASK_MAX_TOKENS_CAP)
    if dropped:
        logger.warning("llm_chat_completion dropped payload kwargs: %s", ", ".join(sorted(map(str, dropped))))
    return allowed


def _response_payload(response: LLMResponse) -> Dict[str, Any]:
    """The JSON-safe part of an LLMResponse a task result carries (#19649)."""
    return {
        "content": response.content,
        "model": response.model,
        "provider": response.provider,
        "usage": response.usage,
    }


class LLMChatCompletionHandler(TaskHandler):
    """Handler for llm_chat_completion tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute LLM chat completion task and return response."""
        model_name = ctx.require_payload_value("model_name")
        messages = ctx.require_payload_value("messages")
        llm_kwargs = ctx.get_payload_value("kwargs", {})

        # #19649: LLMService.chat() records the spend, attributed to a synthetic id for
        # this task (never a real conversation id from the payload).
        response = await ctx.worker.llm_service.chat(
            messages,
            conversation_id=f"task:{ctx.task_id}",
            model_name=model_name,
            **_allowed_chat_kwargs(llm_kwargs),
        )

        if response.content and not response.error:
            result = task_success(
                "LLM completion successful.",
                data={"response": _response_payload(response)},
            )
            ctx.audit_log(
                "llm_chat_completion",
                "success",
                {"model": model_name},
            )
        else:
            result = task_error("LLM completion failed.")
            ctx.audit_log(
                "llm_chat_completion",
                "failure",
                {"model": model_name, "reason": "llm_failed", "error": response.error},
            )

        return result
