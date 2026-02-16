# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Scheduler API endpoints
Provides workflow scheduling and queue management capabilities
"""

from datetime import datetime
from typing import List, Optional, Union

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.type_defs.common import Metadata
from backend.constants.threshold_constants import RetryConfig
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from workflow_scheduler import WorkflowPriority
from workflow_scheduler import WorkflowScheduleRequest as InternalScheduleRequest
from workflow_scheduler import WorkflowStatus, workflow_scheduler

router = APIRouter()


class ScheduleWorkflowRequest(BaseModel):
    user_message: str
    scheduled_time: Union[str, datetime]
    priority: str = "normal"
    complexity: str = "simple"
    template_id: Optional[str] = None
    variables: Optional[Metadata] = None
    auto_approve: bool = False
    tags: Optional[List[str]] = None
    dependencies: Optional[List[str]] = None
    user_id: Optional[str] = None
    estimated_duration_minutes: int = 30
    timeout_minutes: int = 120
    max_retries: int = RetryConfig.DEFAULT_RETRIES


class RescheduleRequest(BaseModel):
    new_scheduled_time: Union[str, datetime]
    new_priority: Optional[str] = None


class QueueControlRequest(BaseModel):
    action: str  # "pause", "resume", "set_max_concurrent"
    value: Optional[int] = None


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="schedule_workflow",
    error_code_prefix="SCHEDULER",
)
@router.post("/schedule")
async def schedule_workflow(request: ScheduleWorkflowRequest):
    """Schedule a workflow for future execution"""
    # Validate priority
    try:
        priority = WorkflowPriority[request.priority.upper()]
    except KeyError:
        raise HTTPException(
            status_code=400, detail=f"Invalid priority: {request.priority}"
        )

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
    workflow_id = workflow_scheduler.schedule_workflow(request=internal_request)

    # Get the created workflow for response (Issue #372 - use model method)
    workflow = workflow_scheduler.get_workflow(workflow_id)

    return {
        "success": True,
        "workflow_id": workflow_id,
        "scheduled_workflow": workflow.to_summary_response(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_scheduled_workflows",
    error_code_prefix="SCHEDULER",
)
@router.get("/workflows")
async def list_scheduled_workflows(
    status: Optional[str] = Query(None, description="Filter by status"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
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
    workflows = workflow_scheduler.list_scheduled_workflows(
        status=status_filter, user_id=user_id, tags=tags_filter
    )

    # Convert to response format using model method (Issue #372)
    workflow_list = [workflow.to_list_response() for workflow in workflows]

    return {
        "success": True,
        "workflows": workflow_list,
        "total": len(workflow_list),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_workflow_details",
    error_code_prefix="SCHEDULER",
)
@router.get("/workflows/{workflow_id}")
async def get_workflow_details(workflow_id: str):
    """Get detailed information about a specific scheduled workflow (Issue #372)"""
    workflow = workflow_scheduler.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Use model method to reduce feature envy (Issue #372)
    return {
        "success": True,
        "workflow": workflow.to_detail_response(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reschedule_workflow",
    error_code_prefix="SCHEDULER",
)
@router.put("/workflows/{workflow_id}/reschedule")
async def reschedule_workflow(workflow_id: str, request: RescheduleRequest):
    """Reschedule an existing workflow"""
    # Parse new priority if provided
    new_priority = None
    if request.new_priority:
        try:
            new_priority = WorkflowPriority[request.new_priority.upper()]
        except KeyError:
            raise HTTPException(
                status_code=400, detail=f"Invalid priority: {request.new_priority}"
            )

    success = workflow_scheduler.reschedule_workflow(
        workflow_id, request.new_scheduled_time, new_priority
    )

    if not success:
        raise HTTPException(
            status_code=404, detail="Workflow not found or cannot be rescheduled"
        )

    # Get updated workflow
    workflow = workflow_scheduler.get_workflow(workflow_id)

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cancel_workflow",
    error_code_prefix="SCHEDULER",
)
@router.delete("/workflows/{workflow_id}")
async def cancel_workflow(workflow_id: str):
    """Cancel a scheduled or queued workflow"""
    success = workflow_scheduler.cancel_workflow(workflow_id)

    if not success:
        raise HTTPException(
            status_code=404, detail="Workflow not found or cannot be cancelled"
        )

    return {
        "success": True,
        "message": "Workflow cancelled successfully",
        "workflow_id": workflow_id,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_scheduler_status",
    error_code_prefix="SCHEDULER",
)
@router.get("/status")
async def get_scheduler_status():
    """Get current scheduler and queue status"""
    status = workflow_scheduler.get_scheduler_status()

    return {"success": True, "scheduler_status": status}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_queue_status",
    error_code_prefix="SCHEDULER",
)
@router.get("/queue")
async def get_queue_status():
    """Get current queue status and workflows"""
    queue_status = workflow_scheduler.queue.get_queue_status()
    queued_workflows = workflow_scheduler.queue.list_queued()
    running_workflows = workflow_scheduler.queue.list_running()

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="control_queue",
    error_code_prefix="SCHEDULER",
)
@router.post("/queue/control")
async def control_queue(request: QueueControlRequest):
    """Control queue operations (pause, resume, set max concurrent)"""
    if request.action == "pause":
        workflow_scheduler.queue.pause_queue()
        message = "Queue paused"
    elif request.action == "resume":
        workflow_scheduler.queue.resume_queue()
        message = "Queue resumed"
    elif request.action == "set_max_concurrent":
        if request.value is None:
            raise HTTPException(
                status_code=400,
                detail="value required for set_max_concurrent action",
            )
        workflow_scheduler.queue.set_max_concurrent(request.value)
        message = f"Max concurrent workflows set to {request.value}"
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")

    return {
        "success": True,
        "message": message,
        "queue_status": workflow_scheduler.queue.get_queue_status(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_scheduler",
    error_code_prefix="SCHEDULER",
)
@router.post("/start")
async def start_scheduler():
    """Start the workflow scheduler"""
    await workflow_scheduler.start()

    return {
        "success": True,
        "message": "Workflow scheduler started",
        "status": workflow_scheduler.get_scheduler_status(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stop_scheduler",
    error_code_prefix="SCHEDULER",
)
@router.post("/stop")
async def stop_scheduler():
    """Stop the workflow scheduler"""
    await workflow_scheduler.stop()

    return {"success": True, "message": "Workflow scheduler stopped"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="schedule_template_workflow",
    error_code_prefix="SCHEDULER",
)
@router.get("/templates/schedule/{template_id}")
async def schedule_template_workflow(
    template_id: str,
    scheduled_time: str = Query(..., description="When to execute the workflow"),
    priority: str = Query("normal", description="Workflow priority"),
    variables: Optional[str] = Query(
        None, description="Template variables as JSON string"
    ),
    auto_approve: bool = Query(False, description="Auto-approve workflow steps"),
    user_id: Optional[str] = Query(None, description="User ID for the workflow"),
):
    """Schedule a workflow from a template"""
    # Parse variables if provided
    template_variables = {}
    if variables:
        import json

        try:
            template_variables = json.loads(variables)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400, detail="Invalid JSON in variables parameter"
            )

    # Validate template exists
    from workflow_templates import workflow_template_manager

    template = workflow_template_manager.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Create user message from template
    user_message = f"Execute template: {template.name}"
    if template_variables:
        user_message += f" with variables: {template_variables}"

    # Issue #319: Use request object to reduce parameter count
    internal_request = InternalScheduleRequest(
        user_message=user_message,
        scheduled_time=scheduled_time,
        priority=priority,
        complexity=(
            template.complexity.value if hasattr(template, "complexity") else "simple"
        ),
        template_id=template_id,
        variables=template_variables,
        auto_approve=auto_approve,
        user_id=user_id,
        estimated_duration_minutes=template.estimated_duration_minutes,
        tags=template.tags.copy(),
    )
    workflow_id = workflow_scheduler.schedule_workflow(request=internal_request)

    # Get the created workflow
    workflow = workflow_scheduler.get_workflow(workflow_id)

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_scheduler_statistics",
    error_code_prefix="SCHEDULER",
)
@router.get("/stats")
async def get_scheduler_statistics():
    """Get detailed scheduler statistics"""
    status = workflow_scheduler.get_scheduler_status()

    # Get additional statistics
    all_workflows = workflow_scheduler.list_scheduled_workflows()

    # Priority distribution
    priority_stats = {}
    for priority in WorkflowPriority:
        priority_stats[priority.name] = len(
            [w for w in all_workflows if w.priority == priority]
        )

    # Status distribution
    status_stats = {}
    for status in WorkflowStatus:
        status_stats[status.name] = len(
            [w for w in all_workflows if w.status == status]
        )

    # Template usage
    template_usage = {}
    for workflow in all_workflows:
        if workflow.template_id:
            template_usage[workflow.template_id] = (
                template_usage.get(workflow.template_id, 0) + 1
            )

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="batch_schedule_workflows",
    error_code_prefix="SCHEDULER",
)
@router.post("/batch-schedule")
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
            workflow_id = workflow_scheduler.schedule_workflow(request=internal_request)

            scheduled_workflows.append(workflow_id)

        except Exception as e:
            errors.append(f"Workflow {i}: {str(e)}")

    return {
        "success": True,
        "scheduled_workflows": scheduled_workflows,
        "errors": errors,
        "total_scheduled": len(scheduled_workflows),
        "total_errors": len(errors),
    }
