# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Plan-approval helpers for the workflow routes (Ref: #1088).

Split out of ``routes.py`` in #17014: that file sat one line under the 600-line
ceiling, and the ownership checks had to go somewhere. These two functions are pure
request handling with no routing of their own, so they move without changing any
caller's behaviour.
"""

from fastapi import HTTPException

from constants.error_constants import ERR_WORKFLOW_NOT_FOUND

from .models import PlanApprovalResponse


def validate_approval_request(manager, workflow_id: str) -> None:
    """Verify the workflow exists and has a pending approval, else raise 404."""
    if not manager.get_workflow_status(workflow_id):
        raise HTTPException(status_code=404, detail=ERR_WORKFLOW_NOT_FOUND)
    if not manager.get_pending_approval(workflow_id):
        raise HTTPException(status_code=404, detail="No pending approval for this workflow")


async def execute_approval_outcome(manager, request: PlanApprovalResponse) -> dict:
    """Start execution on approval, or cancel on rejection; return the response."""
    if request.approved:
        await manager.start_workflow_execution(request.workflow_id)
        return {
            "success": True,
            "workflow_id": request.workflow_id,
            "status": "executing",
            "message": "Plan approved, workflow execution started",
        }

    await manager.cancel_workflow(request.workflow_id)
    return {
        "success": True,
        "workflow_id": request.workflow_id,
        "status": "rejected",
        "message": f"Plan rejected: {request.reason or 'No reason provided'}",
    }
