# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM-related Task Handlers

Issue #322: Refactored to use TaskExecutionContext to eliminate data clump pattern.
"""

import logging
from typing import Any, Dict

from models.task_context import TaskExecutionContext

from .base import TaskHandler

logger = logging.getLogger(__name__)


class LLMChatCompletionHandler(TaskHandler):
    """Handler for llm_chat_completion tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute LLM chat completion task and return response."""
        model_name = ctx.require_payload_value("model_name")
        messages = ctx.require_payload_value("messages")
        llm_kwargs = ctx.get_payload_value("kwargs", {})

        response = await ctx.worker.llm_interface.chat_completion(
            model_name, messages, **llm_kwargs
        )

        if response:
            result = {
                "status": "success",
                "message": "LLM completion successful.",
                "response": response,
            }
            ctx.audit_log(
                "llm_chat_completion",
                "success",
                {"model": model_name},
            )
        else:
            result = {
                "status": "error",
                "message": "LLM completion failed.",
            }
            ctx.audit_log(
                "llm_chat_completion",
                "failure",
                {"model": model_name, "reason": "llm_failed"},
            )

        return result
