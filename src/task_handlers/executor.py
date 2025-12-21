# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Task Executor - Routes tasks to appropriate handlers

This module implements the Strategy Pattern for task execution,
dramatically reducing nesting depth and improving maintainability.

Issue #322: Updated to use TaskExecutionContext for cleaner handler interface.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict

from backend.models.task_context import TaskExecutionContext

from .communication_handlers import (
    AskUserCommandApprovalHandler,
    AskUserForManualHandler,
    RespondConversationallyHandler,
)
from .gui_handlers import (
    GUIBringWindowToFrontHandler,
    GUIClickElementHandler,
    GUIMoveMouseHandler,
    GUIReadTextFromRegionHandler,
    GUITypeTextHandler,
)
from .knowledge_base_handlers import (
    KBAddFileHandler,
    KBSearchHandler,
    KBStoreFactHandler,
)
from .llm_handlers import LLMChatCompletionHandler
from .shell_handlers import ExecuteShellCommandHandler
from .system_handlers import (
    SystemExecuteCommandHandler,
    SystemGetProcessInfoHandler,
    SystemListServicesHandler,
    SystemManageServiceHandler,
    SystemQueryInfoHandler,
    SystemTerminateProcessHandler,
    WebFetchHandler,
)

if TYPE_CHECKING:
    from src.worker_node import WorkerNode

logger = logging.getLogger(__name__)


class TaskExecutor:
    """
    Routes task execution to appropriate handlers using Strategy Pattern.

    This replaces the deeply nested if/elif chain in execute_task with a
    clean, maintainable routing system.
    """

    def __init__(self, worker: "WorkerNode"):
        """
        Initialize the TaskExecutor with all task handlers.

        Args:
            worker: The WorkerNode instance providing module access
        """
        self.worker = worker

        # Register all task handlers - Strategy Pattern dispatch table
        self.handlers = {
            # LLM tasks
            "llm_chat_completion": LLMChatCompletionHandler(),
            # Knowledge base tasks
            "kb_add_file": KBAddFileHandler(),
            "kb_search": KBSearchHandler(),
            "kb_store_fact": KBStoreFactHandler(),
            # Shell command tasks
            "execute_shell_command": ExecuteShellCommandHandler(),
            # GUI automation tasks
            "gui_click_element": GUIClickElementHandler(),
            "gui_read_text_from_region": GUIReadTextFromRegionHandler(),
            "gui_type_text": GUITypeTextHandler(),
            "gui_move_mouse": GUIMoveMouseHandler(),
            "gui_bring_window_to_front": GUIBringWindowToFrontHandler(),
            # System integration tasks
            "system_query_info": SystemQueryInfoHandler(),
            "system_list_services": SystemListServicesHandler(),
            "system_manage_service": SystemManageServiceHandler(),
            "system_execute_command": SystemExecuteCommandHandler(),
            "system_get_process_info": SystemGetProcessInfoHandler(),
            "system_terminate_process": SystemTerminateProcessHandler(),
            "web_fetch": WebFetchHandler(),
            # Communication tasks
            "respond_conversationally": RespondConversationallyHandler(),
            "ask_user_for_manual": AskUserForManualHandler(),
            "ask_user_command_approval": AskUserCommandApprovalHandler(),
        }

        logger.info(
            f"TaskExecutor initialized with {len(self.handlers)} task handlers"
        )

    async def execute(
        self,
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """
        Execute a task by routing to the appropriate handler.

        Issue #322: Updated to use TaskExecutionContext.

        Args:
            task_payload: Task data including type and parameters
            user_role: User role for audit logging
            task_id: Unique task identifier

        Returns:
            Dict with status, message, and any result data
        """
        task_type = task_payload.get("type")

        # Look up the appropriate handler
        handler = self.handlers.get(task_type)

        if not handler:
            logger.warning("Unknown task type: %s", task_type)
            return {
                "status": "error",
                "message": f"Unsupported task type: {task_type}",
            }

        # Issue #322: Create context object to eliminate data clump pattern
        ctx = TaskExecutionContext(
            worker=self.worker,
            task_payload=task_payload,
            user_role=user_role,
            task_id=task_id,
        )

        # Delegate to the handler with context
        try:
            result = await handler.execute(ctx)
            return result
        except KeyError as e:
            # Missing required parameter
            error_msg = f"Missing required parameter: {str(e)}"
            logger.error("Task %s failed: %s", task_id, error_msg)
            return {
                "status": "error",
                "message": error_msg,
            }
        except Exception as e:
            # Unexpected error during handler execution
            error_msg = f"Handler execution error: {str(e)}"
            logger.error("Task %s failed: %s", task_id, error_msg, exc_info=True)

            # Audit log the failure using context
            ctx.audit_log(
                f"execute_task_{task_type}",
                "failure",
                {
                    "payload": task_payload,
                    "error": str(e),
                },
            )

            return {
                "status": "error",
                "message": error_msg,
            }

    def register_handler(self, task_type: str, handler):
        """
        Register a new task handler.

        This allows for easy extension with new task types without
        modifying the core executor logic.

        Args:
            task_type: The task type string
            handler: TaskHandler instance
        """
        self.handlers[task_type] = handler
        logger.info("Registered handler for task type: %s", task_type)

    def get_supported_task_types(self):
        """
        Get a list of all supported task types.

        Returns:
            List of task type strings
        """
        return list(self.handlers.keys())
