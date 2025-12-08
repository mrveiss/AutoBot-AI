# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Communication and User Interaction Task Handlers
"""

import logging
from typing import TYPE_CHECKING, Any, Dict

from src.event_manager import event_manager

from .base import TaskHandler

if TYPE_CHECKING:
    from src.worker_node import WorkerNode

logger = logging.getLogger(__name__)


class RespondConversationallyHandler(TaskHandler):
    """Handler for respond_conversationally tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """Execute conversational response task and publish via event manager."""
        response_text = task_payload.get("response_text", "No response provided.")

        await event_manager.publish("llm_response", {"response": response_text})

        result = {
            "status": "success",
            "message": "Responded conversationally.",
            "response_text": response_text,
        }

        worker.security_layer.audit_log(
            "respond_conversationally",
            user_role,
            "success",
            {"task_id": task_id, "response_preview": response_text[:50]},
        )

        return result


class AskUserForManualHandler(TaskHandler):
    """Handler for ask_user_for_manual tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """Execute manual request task for specific program documentation."""
        program_name = task_payload["program_name"]
        question_text = task_payload["question_text"]

        await event_manager.publish(
            "ask_user_for_manual",
            {
                "task_id": task_id,
                "program_name": program_name,
                "question_text": question_text,
            },
        )

        result = {
            "status": "success",
            "message": f"Asked user for manual for {program_name}.",
        }

        worker.security_layer.audit_log(
            "ask_user_for_manual",
            user_role,
            "success",
            {"task_id": task_id, "program_name": program_name},
        )

        return result


class AskUserCommandApprovalHandler(TaskHandler):
    """Handler for ask_user_command_approval tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """Execute command approval request task requiring user confirmation."""
        command_to_approve = task_payload["command"]

        await event_manager.publish(
            "ask_user_command_approval",
            {"task_id": task_id, "command": command_to_approve},
        )

        result = {
            "status": "pending_approval",
            "message": f"Requested user approval for command: {command_to_approve}",
        }

        worker.security_layer.audit_log(
            "ask_user_command_approval",
            user_role,
            "pending",
            {"task_id": task_id, "command": command_to_approve},
        )

        return result
