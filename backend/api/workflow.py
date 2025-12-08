# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow API endpoints for multi-agent orchestration
Handles workflow approvals, progress tracking, and coordination
"""

import asyncio
import time
import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional

from backend.type_defs.common import Metadata

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from src.event_manager import event_manager
from src.metrics.system_monitor import system_monitor
from src.metrics.workflow_metrics import workflow_metrics
from src.monitoring.prometheus_metrics import get_metrics_manager
from src.utils.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()

# Prometheus metrics instance
prometheus_metrics = get_metrics_manager()


# Issue #336: Agent step handlers extracted from elif chain
async def _handle_librarian_step(
    step: Metadata, action: str, workflow_id: str, orchestrator: Any
) -> None:
    """Handle librarian agent step (Issue #336 - extracted handler)."""
    from src.agents.kb_librarian_agent import KBLibrarianAgent

    kb_agent = KBLibrarianAgent()
    search_query = action.replace("Search Knowledge Base", "").strip()
    if not search_query:
        search_query = "network security scanning tools"

    result = await kb_agent.process_query(search_query)
    response = result.get("response", "Search completed")
    step["result"] = f"Knowledge base search completed: {response}"


async def _handle_research_step(
    step: Metadata, action: str, workflow_id: str, orchestrator: Any
) -> None:
    """Handle research agent step (Issue #336 - extracted handler)."""
    from src.agents.research_agent import ResearchAgent, ResearchRequest

    research_agent = ResearchAgent()
    action_lower = action.lower()

    if "research tools" in action_lower:
        request = ResearchRequest(query="network security scanning tools", focus="tools")
        result = await research_agent.research_specific_tools(request)
        step["result"] = f"Research completed: {result.get('summary', 'Tools researched')}"
    elif "installation guide" in action_lower:
        result = await research_agent.get_tool_installation_guide("nmap")
        guide = result.get("installation_guide", "Guide obtained")
        step["result"] = f"Installation guide retrieved: {guide}"
    else:
        request = ResearchRequest(query=action, focus="general")
        result = await research_agent.perform_research(request)
        step["result"] = f"Research completed: {result.summary}"


async def _handle_orchestrator_step(
    step: Metadata, action: str, workflow_id: str, orchestrator: Any
) -> None:
    """Handle orchestrator agent step (Issue #336 - extracted handler)."""
    action_lower = action.lower()

    if "present tool options" in action_lower:
        options = (
            "Tool options: nmap (network discovery), "
            "masscan (fast port scanner), zmap (internet scanner). "
            "Please select which tool to install."
        )
        step["result"] = options
    elif "create install plan" in action_lower:
        plan = (
            "Installation plan: 1) Update package manager, "
            "2) Install selected tool, 3) Configure tool, "
            "4) Run verification test"
        )
        step["result"] = plan
    else:
        result = await orchestrator.execute_goal(action)
        response = result.get("response", "Task coordinated")
        step["result"] = f"Orchestration completed: {response}"


async def _handle_knowledge_manager_step(
    step: Metadata, action: str, workflow_id: str, orchestrator: Any
) -> None:
    """Handle knowledge manager agent step (Issue #336 - extracted handler)."""
    from src.knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    content = f"Workflow step result: {step.get('result', action)}"
    metadata = {
        "workflow_id": workflow_id,
        "step_id": step["step_id"],
        "agent_type": "knowledge_manager",
        "timestamp": datetime.now().isoformat(),
    }

    await kb.add_document(content, metadata)
    step["result"] = "Information stored in knowledge base for future reference"


async def _handle_security_scanner_step(
    step: Metadata, action: str, workflow_id: str, orchestrator: Any
) -> None:
    """Handle security scanner agent step (Issue #336 - extracted handler)."""
    from src.agents.security_scanner_agent import security_scanner_agent

    scan_context = step.get("inputs", {})
    action_lower = action.lower()

    if "port scan" in action_lower:
        scan_context["scan_type"] = "port_scan"
    elif "vulnerability" in action_lower:
        scan_context["scan_type"] = "vulnerability_scan"
    elif "ssl" in action_lower:
        scan_context["scan_type"] = "ssl_scan"
    elif "service" in action_lower:
        scan_context["scan_type"] = "service_detection"

    result = await security_scanner_agent.execute(action, scan_context)
    status = result.get("status")
    message = result.get("message", "Scan results available")
    step["result"] = f"Security scan completed: {status} - {message}"
    step["scan_results"] = result


# Issue #315: Task type patterns for network discovery
_NETWORK_DISCOVERY_PATTERNS = [
    ("network scan", "network_scan"),
    ("host discovery", "host_discovery"),
    ("arp", "arp_scan"),
    ("asset inventory", "asset_inventory"),
    ("network map", "network_map"),
]


def _detect_network_task_type(action_lower: str) -> str | None:
    """Detect network discovery task type from action. (Issue #315 - extracted)"""
    for pattern, task_type in _NETWORK_DISCOVERY_PATTERNS:
        if pattern in action_lower:
            return task_type
    return None


async def _handle_network_discovery_step(
    step: Metadata, action: str, workflow_id: str, orchestrator: Any
) -> None:
    """Handle network discovery agent step (Issue #336 - extracted handler)."""
    from src.agents.network_discovery_agent import network_discovery_agent

    discovery_context = step.get("inputs", {})

    # Use dispatch pattern (Issue #315 - reduced depth)
    task_type = _detect_network_task_type(action.lower())
    if task_type:
        discovery_context["task_type"] = task_type

    result = await network_discovery_agent.execute(action, discovery_context)
    status = result.get("status")
    hosts_found = result.get("hosts_found", 0)
    step["result"] = f"Network discovery completed: {status} - Found {hosts_found} hosts"
    step["discovery_results"] = result


async def _handle_system_commands_step(
    step: Metadata, action: str, workflow_id: str, orchestrator: Any
) -> None:
    """Handle system commands agent step (Issue #336 - extracted handler)."""
    from src.agents.enhanced_system_commands_agent import EnhancedSystemCommandsAgent

    cmd_agent = EnhancedSystemCommandsAgent()
    action_lower = action.lower()

    if "install tool" in action_lower:
        tool_info = {"name": "nmap", "package_name": "nmap"}
        result = await cmd_agent.install_tool(tool_info, workflow_id)
        step["result"] = f"Installation result: {result.get('response', 'Tool installed')}"
    elif "verify installation" in action_lower:
        result = await cmd_agent.execute_command_with_output("nmap --version", workflow_id)
        step["result"] = f"Verification result: {result.get('output', 'Tool verified')}"
    else:
        result = await cmd_agent.execute_command_with_output(action, workflow_id)
        step["result"] = f"Command executed: {result.get('output', 'Command completed')}"


async def _handle_fallback_step(
    step: Metadata, action: str, workflow_id: str, orchestrator: Any, agent_type: str
) -> None:
    """Handle unknown agent type with fallback (Issue #336 - extracted handler)."""
    result = await orchestrator.execute_goal(f"{agent_type}: {action}")
    step["result"] = f"Executed by {agent_type}: {result.get('response', 'Task completed')}"


# Issue #336: Dispatch table for agent step handlers
AgentStepHandler = Callable[[Metadata, str, str, Any], Awaitable[None]]

AGENT_STEP_HANDLERS: Dict[str, AgentStepHandler] = {
    "librarian": _handle_librarian_step,
    "research": _handle_research_step,
    "orchestrator": _handle_orchestrator_step,
    "knowledge_manager": _handle_knowledge_manager_step,
    "security_scanner": _handle_security_scanner_step,
    "network_discovery": _handle_network_discovery_step,
    "system_commands": _handle_system_commands_step,
}


# Workflow models
class WorkflowApprovalRequest(BaseModel):
    workflow_id: str
    step_id: str
    step_description: str
    required_action: str
    context: Metadata
    timeout_seconds: int = 300


class WorkflowApprovalResponse(BaseModel):
    workflow_id: str
    step_id: str
    approved: bool
    user_input: Optional[Metadata] = None
    timestamp: float


class WorkflowStatusUpdate(BaseModel):
    workflow_id: str
    step_id: str
    status: str  # "pending", "in_progress", "completed", "failed", "waiting_approval"
    progress: float  # 0.0 to 1.0
    message: str
    timestamp: float


class WorkflowExecutionRequest(BaseModel):
    user_message: str
    workflow_id: Optional[str] = None
    auto_approve: bool = False


# In-memory workflow storage (in production, use Redis or database)
active_workflows: Dict[str, Metadata] = {}
pending_approvals: Dict[str, asyncio.Future] = {}

# Locks for thread-safe access to workflow state
_workflows_lock = asyncio.Lock()
_approvals_lock = asyncio.Lock()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_active_workflows",
    error_code_prefix="WORKFLOW",
)
@router.get("/workflows")
async def list_active_workflows():
    """List all active workflows with their current status."""
    async with _workflows_lock:
        workflows_summary = []

        for workflow_id, workflow_data in active_workflows.items():
            summary = {
                "workflow_id": workflow_id,
                "user_message": workflow_data.get("user_message", ""),
                "classification": workflow_data.get("classification", "unknown"),
                "total_steps": len(workflow_data.get("steps", [])),
                "current_step": workflow_data.get("current_step", 0),
                "status": workflow_data.get("status", "unknown"),
                "created_at": workflow_data.get("created_at", ""),
                "estimated_duration": workflow_data.get("estimated_duration", "unknown"),
                "agents_involved": workflow_data.get("agents_involved", []),
            }
            workflows_summary.append(summary)

        active_count = len(active_workflows)

    return {
        "success": True,
        "active_workflows": active_count,
        "workflows": workflows_summary,
    }


@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="get_workflow_details",
    error_code_prefix="WORKFLOW",
)
@router.get("/workflow/{workflow_id}")
async def get_workflow_details(workflow_id: str):
    """Get detailed information about a specific workflow."""
    async with _workflows_lock:
        if workflow_id not in active_workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")

        # Create a copy to avoid race conditions
        workflow = dict(active_workflows[workflow_id])

    return {"success": True, "workflow": workflow}


@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="get_workflow_status",
    error_code_prefix="WORKFLOW",
)
@router.get("/workflow/{workflow_id}/status")
async def get_workflow_status(workflow_id: str):
    """Get current status of a workflow."""
    if workflow_id not in active_workflows:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow = active_workflows[workflow_id]
    current_step = workflow.get("current_step", 0)
    steps = workflow.get("steps", [])

    if current_step < len(steps):
        current_step_info = steps[current_step]
    else:
        current_step_info = None

    return {
        "success": True,
        "workflow_id": workflow_id,
        "status": workflow.get("status", "unknown"),
        "current_step": current_step,
        "total_steps": len(steps),
        "progress": current_step / len(steps) if steps else 0.0,
        "current_step_info": current_step_info,
        "estimated_remaining": workflow.get("estimated_remaining", "unknown"),
    }


@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="approve_workflow_step",
    error_code_prefix="WORKFLOW",
)
@router.post("/workflow/{workflow_id}/approve")
async def approve_workflow_step(workflow_id: str, approval: WorkflowApprovalResponse):
    """Approve or deny a workflow step that requires user confirmation."""
    async with _workflows_lock:
        if workflow_id not in active_workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")

    approval_key = f"{workflow_id}_{approval.step_id}"

    async with _approvals_lock:
        if approval_key not in pending_approvals:
            raise HTTPException(
                status_code=404, detail="No pending approval for this workflow step"
            )

        # Set the approval result
        future = pending_approvals.pop(approval_key)
    if not future.done():
        future.set_result(
            {
                "approved": approval.approved,
                "user_input": approval.user_input,
                "timestamp": approval.timestamp,
            }
        )

    # Update workflow status (thread-safe)
    async with _workflows_lock:
        workflow = active_workflows[workflow_id]
        steps = workflow.get("steps", [])
        current_step = workflow.get("current_step", 0)

        if current_step < len(steps):
            steps[current_step]["status"] = "approved" if approval.approved else "denied"
            steps[current_step]["user_response"] = approval.user_input

        # Get workflow type for metrics
        workflow_type = workflow.get("classification", "unknown")
    prometheus_metrics.record_workflow_approval(
        workflow_type=workflow_type,
        decision="approved" if approval.approved else "rejected",
    )

    # Publish approval event
    await event_manager.publish(
        "workflow_approval",
        {
            "workflow_id": workflow_id,
            "step_id": approval.step_id,
            "approved": approval.approved,
            "user_input": approval.user_input,
        },
    )

    return {
        "success": True,
        "message": f"Workflow step {'approved' if approval.approved else 'denied'}",
        "next_action": (
            "continue_execution" if approval.approved else "workflow_cancelled"
        ),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_workflow",
    error_code_prefix="WORKFLOW",
)
@router.post("/execute")
async def execute_workflow(
    workflow_request: WorkflowExecutionRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """Execute a workflow with coordination of multiple agents."""
    # Get both orchestrators from app state
    lightweight_orchestrator = getattr(
        request.app.state, "lightweight_orchestrator", None
    )
    orchestrator = getattr(request.app.state, "orchestrator", None)

    if lightweight_orchestrator is None:
        raise HTTPException(
            status_code=422,
            detail="Lightweight orchestrator not available - "
            "application not fully initialized",
        )

    if orchestrator is None:
        raise HTTPException(
            status_code=422,
            detail="Main orchestrator not available - "
            "application not fully initialized",
        )

    # TEMPORARY FIX: Use lightweight orchestrator to avoid blocking
    # The full orchestrator's execute_goal method has blocking operations
    try:
        # Use lightweight orchestrator for fast, non-blocking response
        result = await lightweight_orchestrator.route_request(
            workflow_request.user_message
        )

        # Check if we got a simple response or should use full orchestration
        if result.get("bypass_orchestration"):
            return {
                "success": True,
                "type": "lightweight_response",
                "result": result.get(
                    "simple_response", "Response generated successfully"
                ),
                "routing_method": result.get(
                    "routing_reason", "lightweight_pattern_match"
                ),
            }
        else:
            # For complex requests, we need the full orchestrator but it's blocking
            # For now, return a message explaining this limitation
            return {
                "success": False,
                "type": "complex_workflow_blocked",
                "result": (
                    "Complex workflow orchestration is temporarily "
                    "disabled due to blocking operations. This request "
                    "requires multi-agent coordination which is not yet "
                    "available in the current implementation."
                ),
                "complexity": result.get("complexity", "unknown"),
                "suggested_agents": result.get("suggested_agents", []),
            }

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Workflow execution error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Workflow execution failed: {str(e)}"
        )

    # The following code is unreachable and disabled to prevent hanging
    # Create workflow response
    workflow_response = await orchestrator.create_workflow_response(
        workflow_request.user_message
    )
    workflow_id = (
        workflow_request.workflow_id
        or workflow_response.get("workflow_id")
        or str(uuid.uuid4())
    )

    # Store workflow in active workflows
    workflow_start_time = time.time()
    workflow_data = {
        "workflow_id": workflow_id,
        "user_message": workflow_request.user_message,
        "classification": workflow_response.get("message_classification"),
        "steps": [],
        "current_step": 0,
        "status": "planned",
        "created_at": datetime.now().isoformat(),
        "workflow_start_time": workflow_start_time,  # For Prometheus duration tracking
        "estimated_duration": workflow_response.get("estimated_duration"),
        "agents_involved": workflow_response.get("agents_involved", []),
        "auto_approve": workflow_request.auto_approve,
    }

    # Start workflow metrics tracking
    metrics_data = {
        "user_message": workflow_request.user_message,
        "complexity": workflow_response.get("message_classification", "unknown"),
        "total_steps": len(workflow_response.get("workflow_preview", [])),
        "agents_involved": workflow_response.get("agents_involved", []),
    }
    workflow_metrics.start_workflow_tracking(workflow_id, metrics_data)

    # Track workflow start in Prometheus (record later on completion with duration)
    prometheus_metrics.update_active_workflows(
        workflow_type=workflow_response.get("message_classification", "unknown"),
        count=len(
            [
                w
                for w in active_workflows.values()
                if w.get("classification")
                == workflow_response.get("message_classification")
            ]
        ),
    )

    # Record initial system metrics
    initial_resources = system_monitor.get_current_metrics()
    workflow_metrics.record_resource_usage(workflow_id, initial_resources)

    # Convert workflow preview to executable steps
    steps = []
    for i, step_desc in enumerate(workflow_response.get("workflow_preview", [])):
        step = {
            "step_id": f"step_{i+1}",
            "description": step_desc,
            "status": "pending",
            "requires_approval": "requires your approval" in step_desc,
            "agent_type": step_desc.split(":")[0].lower(),
            "action": (
                step_desc.split(":")[1].strip() if ":" in step_desc else step_desc
            ),
            "started_at": None,
            "completed_at": None,
        }
        steps.append(step)

    workflow_data["steps"] = steps

    # Store workflow (thread-safe)
    async with _workflows_lock:
        active_workflows[workflow_id] = workflow_data

    # Start workflow execution in background
    background_tasks.add_task(execute_workflow_steps, workflow_id, orchestrator)

    return {
        "success": True,
        "type": "workflow_orchestration",
        "workflow_id": workflow_id,
        "workflow_response": workflow_response,
        "execution_started": True,
        "status_endpoint": f"/api/workflow/{workflow_id}/status",
    }


async def _handle_approval_result(
    approval_result: dict, step: dict, workflow: dict
) -> bool:
    """Handle approval result and update status (Issue #315: extracted).

    Returns:
        True if approved and should continue, False if cancelled
    """
    if not approval_result.get("approved", False):
        async with _workflows_lock:
            step["status"] = "cancelled"
            workflow["status"] = "cancelled"
        return False

    async with _workflows_lock:
        step["user_response"] = approval_result.get("user_input")
    return True


async def _wait_for_step_approval(
    workflow_id: str, workflow: dict, step: dict
) -> bool | None:
    """Wait for step approval with timeout handling (Issue #315: extracted).

    Returns:
        True if approved, False if cancelled, None if timeout
    """
    from src.utils.async_cancellation import execute_with_cancellation

    approval_key = f"{workflow_id}_{step['step_id']}"
    approval_future = asyncio.Future()

    async with _approvals_lock:
        pending_approvals[approval_key] = approval_future

    # Publish approval request event
    await event_manager.publish(
        "workflow_approval_required",
        {
            "workflow_id": workflow_id,
            "step_id": step["step_id"],
            "description": step["description"],
            "context": {
                "step_index": step.get("step_index", 0),
                "agent_type": step["agent_type"],
                "action": step["action"],
            },
        },
    )

    try:
        approval_result = await execute_with_cancellation(
            approval_future, f"workflow_approval_{workflow['id']}"
        )
        return await _handle_approval_result(approval_result, step, workflow)
    except asyncio.TimeoutError:
        async with _workflows_lock:
            step["status"] = "timeout"
            workflow["status"] = "timeout"
        return None


async def execute_workflow_steps(workflow_id: str, orchestrator):
    """Execute workflow steps in sequence with proper coordination."""
    async with _workflows_lock:
        if workflow_id not in active_workflows:
            return

        workflow = active_workflows[workflow_id]
        steps = workflow["steps"]
        workflow["status"] = "executing"

    try:
        for step_index, step in enumerate(steps):
            async with _workflows_lock:
                workflow["current_step"] = step_index
                step["status"] = "in_progress"
                step["started_at"] = datetime.now().isoformat()

            # Publish step start event
            await event_manager.publish(
                "workflow_step_started",
                {
                    "workflow_id": workflow_id,
                    "step_id": step["step_id"],
                    "description": step["description"],
                    "step_index": step_index,
                    "total_steps": len(steps),
                },
            )

            # Check if step requires approval
            async with _workflows_lock:
                workflow = active_workflows[workflow_id]
                auto_approve = workflow.get("auto_approve", False)
                requires_approval = step["requires_approval"] and not auto_approve

            if requires_approval:
                async with _workflows_lock:
                    step["status"] = "waiting_approval"
                    step["step_index"] = step_index  # Store for helper

                # Wait for approval using helper (Issue #315)
                approval_result = await _wait_for_step_approval(
                    workflow_id, workflow, step
                )
                if approval_result is None or approval_result is False:
                    return  # Timeout or cancelled

            # Execute the step (mock execution for demonstration)
            await execute_single_step(workflow_id, step, orchestrator)

            async with _workflows_lock:
                step["status"] = "completed"
                step["completed_at"] = datetime.now().isoformat()

            # Publish step completion event
            await event_manager.publish(
                "workflow_step_completed",
                {
                    "workflow_id": workflow_id,
                    "step_id": step["step_id"],
                    "description": step["description"],
                    "result": step.get("result", "Step completed successfully"),
                },
            )

        # Workflow completed
        async with _workflows_lock:
            workflow["status"] = "completed"
            workflow["completed_at"] = datetime.now().isoformat()
            workflow_start_time = workflow.get("workflow_start_time")
            workflow_type = workflow.get("classification", "unknown")

        # Record Prometheus workflow execution metric (success)
        if workflow_start_time:
            duration = time.time() - workflow_start_time
            prometheus_metrics.record_workflow_execution(
                workflow_type=workflow_type, status="success", duration=duration
            )

            # Update active workflows count (decrement)
            prometheus_metrics.update_active_workflows(
                workflow_type=workflow_type,
                count=max(
                    0,
                    len(
                        [
                            w
                            for w in active_workflows.values()
                            if w.get("classification") == workflow_type
                        ]
                    )
                    - 1,
                ),
            )

        await event_manager.publish(
            "workflow_completed",
            {
                "workflow_id": workflow_id,
                "user_message": workflow["user_message"],
                "total_steps": len(steps),
                "execution_time": "calculated_time_here",
            },
        )

    except Exception as e:
        async with _workflows_lock:
            workflow["status"] = "failed"
            workflow["error"] = str(e)
            workflow_start_time = workflow.get("workflow_start_time")
            workflow_type = workflow.get("classification", "unknown")

        # Record Prometheus workflow execution metric (failed)
        if workflow_start_time:
            duration = time.time() - workflow_start_time
            prometheus_metrics.record_workflow_execution(
                workflow_type=workflow_type, status="failed", duration=duration
            )

            # Update active workflows count (decrement)
            prometheus_metrics.update_active_workflows(
                workflow_type=workflow_type,
                count=max(
                    0,
                    len(
                        [
                            w
                            for w in active_workflows.values()
                            if w.get("classification") == workflow_type
                        ]
                    )
                    - 1,
                ),
            )

        await event_manager.publish(
            "workflow_failed",
            {
                "workflow_id": workflow_id,
                "error": str(e),
                "current_step": workflow.get("current_step", 0),
            },
        )


async def execute_single_step(workflow_id: str, step: Metadata, orchestrator):
    """Execute a single workflow step with real agent integration."""
    agent_type = (
        step["agent_type"].split(".")[1]
        if "." in step["agent_type"]
        else step["agent_type"]
    )
    action = step["action"]
    step_id = step.get("step_id", f"step_{agent_type}")

    # Start step timing
    workflow_metrics.start_step_timing(workflow_id, step_id, agent_type)

    # Record resource usage at step start
    step_resources = system_monitor.get_current_metrics()
    workflow_metrics.record_resource_usage(workflow_id, step_resources)

    try:
        # Issue #336: Use dispatch table instead of elif chain
        handler = AGENT_STEP_HANDLERS.get(agent_type)
        if handler:
            await handler(step, action, workflow_id, orchestrator)
        else:
            # Fallback to orchestrator for unknown agent types
            await _handle_fallback_step(step, action, workflow_id, orchestrator, agent_type)

    except Exception as e:
        step["result"] = f"Error executing step: {str(e)}"
        step["status"] = "failed"

        # End step timing with failure
        workflow_metrics.end_step_timing(
            workflow_id, step_id, success=False, error=str(e)
        )

        # Record Prometheus workflow step metric (failed)
        if workflow_id in active_workflows:
            workflow_type = active_workflows[workflow_id].get(
                "classification", "unknown"
            )
            prometheus_metrics.record_workflow_step(
                workflow_type=workflow_type, step_type=agent_type, status="failed"
            )
    else:
        # End step timing with success
        workflow_metrics.end_step_timing(workflow_id, step_id, success=True)

        # Record Prometheus workflow step metric (success)
        if workflow_id in active_workflows:
            workflow_type = active_workflows[workflow_id].get(
                "classification", "unknown"
            )
            prometheus_metrics.record_workflow_step(
                workflow_type=workflow_type, step_type=agent_type, status="completed"
            )


@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="cancel_workflow",
    error_code_prefix="WORKFLOW",
)
@router.delete("/workflow/{workflow_id}")
async def cancel_workflow(workflow_id: str):
    """Cancel an active workflow."""
    async with _workflows_lock:
        if workflow_id not in active_workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")

        workflow = active_workflows[workflow_id]
        workflow["status"] = "cancelled"
        workflow["cancelled_at"] = datetime.now().isoformat()
        user_message = workflow.get("user_message", "")

    # Cancel any pending approvals (thread-safe)
    async with _approvals_lock:
        for key in list(pending_approvals.keys()):
            if key.startswith(workflow_id):
                future = pending_approvals.pop(key)
                if not future.done():
                    future.cancel()

    await event_manager.publish(
        "workflow_cancelled",
        {"workflow_id": workflow_id, "user_message": user_message},
    )

    return {"success": True, "message": "Workflow cancelled successfully"}


@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="get_pending_approvals",
    error_code_prefix="WORKFLOW",
)
@router.get("/workflow/{workflow_id}/pending_approvals")
async def get_pending_approvals(workflow_id: str):
    """Get pending approval requests for a workflow."""
    if workflow_id not in active_workflows:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow = active_workflows[workflow_id]
    pending_steps = []

    for step in workflow.get("steps", []):
        if step["status"] == "waiting_approval":
            pending_steps.append(
                {
                    "step_id": step["step_id"],
                    "description": step["description"],
                    "agent_type": step["agent_type"],
                    "action": step["action"],
                    "context": step.get("context", {}),
                }
            )

    return {
        "success": True,
        "workflow_id": workflow_id,
        "pending_approvals": pending_steps,
    }
