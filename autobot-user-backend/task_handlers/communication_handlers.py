# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Communication and User Interaction Task Handlers

Issue #322: Refactored to use TaskExecutionContext to eliminate data clump pattern.
"""

import logging
from typing import Any, Dict

from backend.models.task_context import TaskExecutionContext
from src.event_manager import event_manager

from .base import TaskHandler

logger = logging.getLogger(__name__)


class RespondConversationallyHandler(TaskHandler):
    """Handler for respond_conversationally tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute conversational response task and publish via event manager."""
        response_text = ctx.get_payload_value("response_text", "No response provided.")

        await event_manager.publish("llm_response", {"response": response_text})

        result = {
            "status": "success",
            "message": "Responded conversationally.",
            "response_text": response_text,
        }

        ctx.audit_log(
            "respond_conversationally",
            "success",
            {"response_preview": response_text[:50]},
        )

        return result


class AskUserForManualHandler(TaskHandler):
    """Handler for ask_user_for_manual tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute manual request task for specific program documentation."""
        program_name = ctx.require_payload_value("program_name")
        question_text = ctx.require_payload_value("question_text")

        await event_manager.publish(
            "ask_user_for_manual",
            {
                "task_id": ctx.task_id,
                "program_name": program_name,
                "question_text": question_text,
            },
        )

        result = {
            "status": "success",
            "message": f"Asked user for manual for {program_name}.",
        }

        ctx.audit_log(
            "ask_user_for_manual",
            "success",
            {"program_name": program_name},
        )

        return result


class AskUserCommandApprovalHandler(TaskHandler):
    """Handler for ask_user_command_approval tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute command approval request task requiring user confirmation."""
        command_to_approve = ctx.require_payload_value("command")

        await event_manager.publish(
            "ask_user_command_approval",
            {"task_id": ctx.task_id, "command": command_to_approve},
        )

        result = {
            "status": "pending_approval",
            "message": f"Requested user approval for command: {command_to_approve}",
        }

        ctx.audit_log(
            "ask_user_command_approval",
            "pending",
            {"command": command_to_approve},
        )

        return result
