# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Communication and User Interaction Task Handlers

Issue #322: Refactored to use TaskExecutionContext to eliminate data clump pattern.
"""

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.models.task_result import task_pending_approval, task_success
from events.bus import PersistStrategy, publish_event
from models.task_context import TaskExecutionContext

from .base import TaskHandler

logger = get_logger(__name__)


class RespondConversationallyHandler(TaskHandler):
    """Handler for respond_conversationally tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute conversational response task and publish via event manager."""
        response_text = ctx.get_payload_value("response_text", "No response provided.")

        await publish_event("global", "llm_response", {"response": response_text}, persist=PersistStrategy.NONE)

        result = task_success(
            "Responded conversationally.",
            data={"response_text": response_text},
        )

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

        await publish_event(
            "global",
            "ask_user_for_manual",
            {
                "task_id": ctx.task_id,
                "program_name": program_name,
                "question_text": question_text,
            },
            persist=PersistStrategy.NONE,
        )

        result = task_success(f"Asked user for manual for {program_name}.")

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

        await publish_event(
            "global",
            "ask_user_command_approval",
            {"task_id": ctx.task_id, "command": command_to_approve},
            persist=PersistStrategy.NONE,
        )

        result = task_pending_approval(f"Requested user approval for command: {command_to_approve}")

        ctx.audit_log(
            "ask_user_command_approval",
            "pending",
            {"command": command_to_approve},
        )

        return result
