# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
LLM-related Task Handlers

Issue #322: Refactored to use TaskExecutionContext to eliminate data clump pattern.
"""

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.models.task_result import task_error, task_success
from llm_shared.models import LLMResponse
from models.task_context import TaskExecutionContext

from .base import TaskHandler

logger = get_logger(__name__)


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

        # #19649: LLMService.chat() records the spend; the task id attributes it
        # unless the payload names its own conversation.
        response = await ctx.worker.llm_service.chat(
            messages, **{"conversation_id": ctx.task_id, "model_name": model_name, **llm_kwargs}
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
