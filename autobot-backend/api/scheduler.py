# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Scheduler API endpoints
Provides workflow scheduling and queue management capabilities
"""

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas_system import (
    QueueControlRequest,
    RescheduleRequest,
    SchedulerBatchScheduleResponse,
    SchedulerCancelResponse,
    SchedulerQueueControlResponse,
    SchedulerQueueResponse,
    SchedulerRescheduleResponse,
    SchedulerStartResponse,
    SchedulerStatsResponse,
    SchedulerStatusResponse,
    SchedulerStopResponse,
    SchedulerTemplateScheduleResponse,
    SchedulerWorkflowCreateResponse,
    SchedulerWorkflowDetailResponse,
    SchedulerWorkflowListResponse,
    ScheduleWorkflowRequest,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from constants.error_constants import ERR_TEMPLATE_NOT_FOUND, ERR_WORKFLOW_NOT_FOUND
from type_defs.common import Metadata
from workflow_scheduler import WorkflowPriority
from workflow_scheduler import WorkflowScheduleRequest as InternalScheduleRequest
from workflow_scheduler import WorkflowStatus, get_workflow_scheduler

router = APIRouter(dependencies=[Depends(check_admin_permission)])


@router.post("/schedule", response_model=SchedulerWorkflowCreateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="schedule_workflow",
    error_code_prefix="SCHEDULER",
)
async def schedule_workflow(request: ScheduleWorkflowRequest):
    """Schedule a workflow for future execution"""
    # Validate priority
    try:
        priority = WorkflowPriority[request.priority.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {request.priority}")

    # Issue #319: Use request object to reduce parameter count
    internal_request = InternalScheduleRequest(
        user_message=request.user_message,
        scheduled_time=request.scheduled_time,
        priority=priority,
        complexity=request.complexity,
        template_id=request.template_id,
        variables=request.variables,
        auto_approve=request.auto_approve,
        tags=request.tags,
        dependencies=request.dependencies,
        user_id=request.user_id,
        estimated_duration_minutes=request.estimated_duration_minutes,
        timeout_minutes=request.timeout_minutes,
        max_retries=request.max_retries,
    )
    workflow_id = get_workflow_scheduler().schedule_workflow(request=internal_request)

    # Get the created workflow for response (Issue #372 - use model method)
    workflow = get_workflow_scheduler().get_workflow(workflow_id)

    return {
        "success": True,
        "workflow_id": workflow_id,
        "scheduled_workflow": workflow.to_summary_response(),
    }


@router.get("/workflows", response_model=SchedulerWorkflowListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_scheduled_workflows",
    error_code_prefix="SCHEDULER",
)
async def list_scheduled_workflows(
    status: str | None = Query(None, description="Filter by status"),
    user_id: str | None = Query(None, description="Filter by user ID"),
    tags: str | None = Query(None, description="Filter by tags (comma-separated)"),
):
    """List scheduled workflows with optional filtering"""
    # Parse filters
    status_filter = None
    if status:
        try:
            status_filter = WorkflowStatus[status.upper()]
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    tags_filter = None
    if tags:
        tags_filter = [tag.strip() for tag in tags.split(",")]

    # Get workflows
    workflows = get_workflow_scheduler().list_scheduled_workflows(
        status=status_filter, user_id=user_id, tags=tags_filter
    )

    # Convert to response format using model method (Issue #372)
    workflow_list = [workflow.to_list_response() for workflow in workflows]

    return {
        "success": True,
        "workflows": workflow_list,
        "total": len(workflow_list),
    }


@router.get("/workflows/{workflow_id}", response_model=SchedulerWorkflowDetailResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_workflow_details",
    error_code_prefix="SCHEDULER",
)
async def get_workflow_details(workflow_id: str):
    """Get detailed information about a specific scheduled workflow (Issue #372)"""
    workflow = get_workflow_scheduler().get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail=ERR_WORKFLOW_NOT_FOUND)

    # Use model method to reduce feature envy (Issue #372)
    return {
        "success": True,
        "workflow": workflow.to_detail_response(),
    }


@router.put("/workflows/{workflow_id}/reschedule", response_model=SchedulerRescheduleResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reschedule_workflow",
    error_code_prefix="SCHEDULER",
)
async def reschedule_workflow(workflow_id: str, request: RescheduleRequest):
    """Reschedule an existing workflow"""
    # Parse new priority if provided
    new_priority = None
    if request.new_priority:
        try:
            new_priority = WorkflowPriority[request.new_priority.upper()]
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {request.new_priority}")

    success = get_workflow_scheduler().reschedule_workflow(workflow_id, request.new_scheduled_time, new_priority)

    if not success:
        raise HTTPException(status_code=404, detail="Workflow not found or cannot be rescheduled")

    # Get updated workflow
    workflow = get_workflow_scheduler().get_workflow(workflow_id)

    return {
        "success": True,
        "message": "Workflow rescheduled successfully",
        "workflow": {
            "id": workflow.id,
            "scheduled_time": workflow.scheduled_time.isoformat(),
            "priority": workflow.priority.name,
            "status": workflow.status.name,
            "complexity": workflow.complexity.value,
        },
    }


@router.delete("/workflows/{workflow_id}", response_model=SchedulerCancelResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cancel_workflow",
    error_code_prefix="SCHEDULER",
)
async def cancel_workflow(workflow_id: str):
    """Cancel a scheduled or queued workflow"""
    success = get_workflow_scheduler().cancel_workflow(workflow_id)

    if not success:
        raise HTTPException(status_code=404, detail="Workflow not found or cannot be cancelled")

    return {
        "success": True,
        "message": "Workflow cancelled successfully",
        "workflow_id": workflow_id,
    }


@router.get("/status", response_model=SchedulerStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_scheduler_status",
    error_code_prefix="SCHEDULER",
)
async def get_scheduler_status():
    """Get current scheduler and queue status"""
    status = get_workflow_scheduler().get_scheduler_status()

    return {"success": True, "scheduler_status": status}


@router.get("/queue", response_model=SchedulerQueueResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_queue_status",
    error_code_prefix="SCHEDULER",
)
async def get_queue_status():
    """Get current queue status and workflows"""
    queue_status = get_workflow_scheduler().queue.get_queue_status()
    queued_workflows = get_workflow_scheduler().queue.list_queued()
    running_workflows = get_workflow_scheduler().queue.list_running()

    # Convert to response format
    queued_list = []
    for workflow in queued_workflows:
        queued_list.append(
            {
                "id": workflow.id,
                "name": workflow.name,
                "priority": workflow.priority.name,
                "complexity": workflow.complexity.value,
                "estimated_duration_minutes": workflow.estimated_duration_minutes,
            }
        )

    running_list = []
    for workflow in running_workflows:
        running_list.append(
            {
                "id": workflow.id,
                "name": workflow.name,
                "priority": workflow.priority.name,
                "complexity": workflow.complexity.value,
                "estimated_duration_minutes": workflow.estimated_duration_minutes,
            }
        )

    return {
        "success": True,
        "queue_status": queue_status,
        "queued_workflows": queued_list,
        "running_workflows": running_list,
    }


@router.post("/queue/control", response_model=SchedulerQueueControlResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="control_queue",
    error_code_prefix="SCHEDULER",
)
async def control_queue(request: QueueControlRequest):
    """Control queue operations (pause, resume, set max concurrent)"""
    if request.action == "pause":
        get_workflow_scheduler().queue.pause_queue()
        message = "Queue paused"
    elif request.action == "resume":
        get_workflow_scheduler().queue.resume_queue()
        message = "Queue resumed"
    elif request.action == "set_max_concurrent":
        if request.value is None:
            raise HTTPException(
                status_code=400,
                detail="value required for set_max_concurrent action",
            )
        get_workflow_scheduler().queue.set_max_concurrent(request.value)
        message = f"Max concurrent workflows set to {request.value}"
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")

    return {
        "success": True,
        "message": message,
        "queue_status": get_workflow_scheduler().queue.get_queue_status(),
    }


@router.post("/start", response_model=SchedulerStartResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_scheduler",
    error_code_prefix="SCHEDULER",
)
async def start_scheduler():
    """Start the workflow scheduler"""
    await get_workflow_scheduler().start()

    return {
        "success": True,
        "message": "Workflow scheduler started",
        "status": get_workflow_scheduler().get_scheduler_status(),
    }


@router.post("/stop", response_model=SchedulerStopResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stop_scheduler",
    error_code_prefix="SCHEDULER",
)
async def stop_scheduler():
    """Stop the workflow scheduler"""
    await get_workflow_scheduler().stop()

    return {"success": True, "message": "Workflow scheduler stopped"}


def _parse_template_variables(variables: str | None) -> Metadata:
    """Helper for schedule_template_workflow. Ref: #1088.

    Parses the JSON-encoded template variables query parameter.

    Args:
        variables: JSON string of template variables, or None

    Returns:
        Parsed variables dict (empty dict if variables is None)

    Raises:
        HTTPException: 400 if JSON is invalid
    """
    if not variables:
        return {}
    import json

    try:
        return json.loads(variables)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in variables parameter")


def _build_template_schedule_request(
    template_id: str,
    template,
    template_variables: Metadata,
    scheduled_time: str,
    priority: str,
    auto_approve: bool,
    user_id: str | None,
) -> InternalScheduleRequest:
    """Helper for schedule_template_workflow. Ref: #1088.

    Builds an InternalScheduleRequest from the resolved template and parameters.

    Args:
        template_id: Template identifier
        template: Resolved template object
        template_variables: Parsed variable dict
        scheduled_time: ISO-formatted scheduled time string
        priority: Workflow priority string
        auto_approve: Whether to auto-approve workflow steps
        user_id: Optional user identifier

    Returns:
        Populated InternalScheduleRequest
    """
    user_message = f"Execute template: {template.name}"
    if template_variables:
        user_message += f" with variables: {template_variables}"
    return InternalScheduleRequest(
        user_message=user_message,
        scheduled_time=scheduled_time,
        priority=priority,
        complexity=(template.complexity.value if hasattr(template, "complexity") else "simple"),
        template_id=template_id,
        variables=template_variables,
        auto_approve=auto_approve,
        user_id=user_id,
        estimated_duration_minutes=template.estimated_duration_minutes,
        tags=template.tags.copy(),
    )


@router.get("/templates/schedule/{template_id}", response_model=SchedulerTemplateScheduleResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="schedule_template_workflow",
    error_code_prefix="SCHEDULER",
)
async def schedule_template_workflow(
    template_id: str,
    scheduled_time: str = Query(..., description="When to execute the workflow"),
    priority: str = Query("normal", description="Workflow priority"),
    variables: str | None = Query(None, description="Template variables as JSON string"),
    auto_approve: bool = Query(False, description="Auto-approve workflow steps"),
    user_id: str | None = Query(None, description="User ID for the workflow"),
):
    """Schedule a workflow from a template.

    Issue #1088: Extracted _parse_template_variables and
    _build_template_schedule_request helpers to reduce to <=65 lines.
    """
    template_variables = _parse_template_variables(variables)

    from workflow_templates import workflow_template_manager

    template = workflow_template_manager.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=ERR_TEMPLATE_NOT_FOUND)

    internal_request = _build_template_schedule_request(
        template_id,
        template,
        template_variables,
        scheduled_time,
        priority,
        auto_approve,
        user_id,
    )
    workflow_id = get_workflow_scheduler().schedule_workflow(request=internal_request)
    workflow = get_workflow_scheduler().get_workflow(workflow_id)

    return {
        "success": True,
        "workflow_id": workflow_id,
        "template_info": {
            "template_id": template_id,
            "template_name": template.name,
            "category": template.category.value,
        },
        "scheduled_workflow": {
            "id": workflow.id,
            "name": workflow.name,
            "scheduled_time": workflow.scheduled_time.isoformat(),
            "priority": workflow.priority.name,
            "status": workflow.status.name,
            "complexity": workflow.complexity.value,
        },
    }


@router.get("/stats", response_model=SchedulerStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_scheduler_statistics",
    error_code_prefix="SCHEDULER",
)
async def get_scheduler_statistics():
    """Get detailed scheduler statistics"""
    status = get_workflow_scheduler().get_scheduler_status()

    # Get additional statistics
    all_workflows = get_workflow_scheduler().list_scheduled_workflows()

    # Priority distribution
    priority_stats = {}
    for priority in WorkflowPriority:
        priority_stats[priority.name] = len([w for w in all_workflows if w.priority == priority])

    # Status distribution
    status_stats = {}
    for status in WorkflowStatus:
        status_stats[status.name] = len([w for w in all_workflows if w.status == status])

    # Template usage
    template_usage = {}
    for workflow in all_workflows:
        if workflow.template_id:
            template_usage[workflow.template_id] = template_usage.get(workflow.template_id, 0) + 1

    # Average durations
    durations = [w.estimated_duration_minutes for w in all_workflows]
    avg_duration = sum(durations) / len(durations) if durations else 0

    return {
        "success": True,
        "statistics": {
            **status,
            "priority_distribution": priority_stats,
            "status_distribution": status_stats,
            "template_usage": template_usage,
            "average_duration_minutes": round(avg_duration, 1),
            "duration_range": {
                "min": min(durations) if durations else 0,
                "max": max(durations) if durations else 0,
            },
        },
    }


@router.post("/batch-schedule", response_model=SchedulerBatchScheduleResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="batch_schedule_workflows",
    error_code_prefix="SCHEDULER",
)
async def batch_schedule_workflows(workflows: List[ScheduleWorkflowRequest]):
    """Schedule multiple workflows in batch"""
    scheduled_workflows = []
    errors = []

    for i, request in enumerate(workflows):
        try:
            # Validate priority
            priority = WorkflowPriority[request.priority.upper()]

            # Issue #319: Use request object to reduce parameter count
            internal_request = InternalScheduleRequest(
                user_message=request.user_message,
                scheduled_time=request.scheduled_time,
                priority=priority,
                complexity=request.complexity,
                template_id=request.template_id,
                variables=request.variables,
                auto_approve=request.auto_approve,
                tags=request.tags,
                dependencies=request.dependencies,
                user_id=request.user_id,
                estimated_duration_minutes=request.estimated_duration_minutes,
                timeout_minutes=request.timeout_minutes,
                max_retries=request.max_retries,
            )
            workflow_id = get_workflow_scheduler().schedule_workflow(request=internal_request)

            scheduled_workflows.append(workflow_id)

        except Exception as e:
            logger.exception("Unexpected error: %s", e)
            errors.append("Workflow {i}")

    return {
        "success": True,
        "scheduled_workflows": scheduled_workflows,
        "errors": errors,
        "total_scheduled": len(scheduled_workflows),
        "total_errors": len(errors),
    }
