# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Complex-request delegation for POST /workflow/execute (#1770, #20585)."""

from typing import TYPE_CHECKING, Dict

from fastapi import BackgroundTasks, HTTPException

from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:
    from api.schemas_workflows import WorkflowExecutionRequest

logger = get_logger(__name__)


async def _execute_complex_workflow(
    workflow_request: "WorkflowExecutionRequest",
    background_tasks: BackgroundTasks,
    session_id: str,
    owner_id: str | None = None,
) -> Dict:
    """Delegate a complex workflow request to WorkflowAutomationManager (#1770).

    Creates the workflow via the automation service and starts execution as a
    background task so the endpoint returns immediately. #20585: ``owner_id`` is the
    verified caller, so the workflow's command steps run as that account instead of
    being refused for having no creator.
    """
    from services.workflow_automation.routes import get_workflow_manager

    manager = get_workflow_manager()
    workflow_id = await manager.create_workflow_from_chat_request(
        workflow_request.user_message, session_id, owner_id=owner_id
    )

    if not workflow_id:
        logger.error(
            "workflow_automation could not create workflow for message: %s",
            workflow_request.user_message,
        )
        raise HTTPException(
            status_code=500,
            detail="Could not create workflow from request",
        )

    background_tasks.add_task(manager.start_workflow_execution, workflow_id)

    return {
        "success": True,
        "type": "workflow_orchestration",
        "workflow_id": workflow_id,
        "execution_started": True,
        "status_endpoint": f"/api/workflow_automation/workflow_status/{workflow_id}",
    }
