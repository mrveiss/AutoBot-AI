# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM-related Task Handlers
"""

import logging
from typing import TYPE_CHECKING, Any, Dict

from .base import TaskHandler

if TYPE_CHECKING:
    from src.worker_node import WorkerNode

logger = logging.getLogger(__name__)


class LLMChatCompletionHandler(TaskHandler):
    """Handler for llm_chat_completion tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        model_name = task_payload["model_name"]
        messages = task_payload["messages"]
        llm_kwargs = task_payload.get("kwargs", {})

        response = await worker.llm_interface.chat_completion(
            model_name, messages, **llm_kwargs
        )

        if response:
            result = {
                "status": "success",
                "message": "LLM completion successful.",
                "response": response,
            }
            worker.security_layer.audit_log(
                "llm_chat_completion",
                user_role,
                "success",
                {"task_id": task_id, "model": model_name},
            )
        else:
            result = {
                "status": "error",
                "message": "LLM completion failed.",
            }
            worker.security_layer.audit_log(
                "llm_chat_completion",
                user_role,
                "failure",
                {
                    "task_id": task_id,
                    "model": model_name,
                    "reason": "llm_failed",
                },
            )

        return result
