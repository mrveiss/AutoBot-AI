# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow API endpoints for multi-agent orchestration
Handles workflow approvals, progress tracking, and coordination
"""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from api.schemas_workflows import (
    WorkflowApprovalResponse,
    WorkflowApproveResponse,
    WorkflowCancelResponse,
    WorkflowDetailResponse,
    WorkflowExecutionRequest,
    WorkflowExecutionResponse,
    WorkflowListResponse,
    WorkflowPendingApprovalsResponse,
    WorkflowStatusResponse,
)
from api.workflow_state import get_workflow_state_machine
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from constants.error_constants import ERR_WORKFLOW_NOT_FOUND
from events.bus import PersistStrategy, publish_event
from metrics.system_monitor import system_monitor
from metrics.workflow_metrics import workflow_metrics
from models.task_context import WorkflowStepContext
from monitoring.prometheus_metrics import get_metrics_manager
from patterns.conversation_patterns import conversation_patterns
from type_defs.common import Metadata

logger = get_logger(__name__)

router = APIRouter()

# Prometheus metrics instance
prometheus_metrics = get_metrics_manager()


# Issue #336: Agent step handlers extracted from elif chain
# Issue #322: Refactored to use WorkflowStepContext to eliminate data clump pattern
async def _handle_librarian_step(ctx: WorkflowStepContext) -> None:
    """Handle librarian agent step (Issue #336 - extracted handler)."""
    from agents.kb_librarian_agent import KBLibrarianAgent

    kb_agent = KBLibrarianAgent()
    search_query = ctx.action.replace("Search Knowledge Base", "").strip()
    if not search_query:
        search_query = "network security scanning tools"

    result = await kb_agent.process_query(search_query)
    response = result.get("response", "Search completed")
    ctx.step["result"] = f"Knowledge base search completed: {response}"


async def _handle_research_step(ctx: WorkflowStepContext) -> None:
    """Handle research agent step (Issue #336 - extracted handler, Issue #322 - context)."""
    from agents.web_researcher import ResearchRequest, WebResearcher

    research_agent = WebResearcher()
    action_lower = ctx.action.lower()

    if "research tools" in action_lower:
        request = ResearchRequest(query="network security scanning tools", focus="tools")
        result = await research_agent.research_specific_tools(request)
        ctx.step["result"] = f"Research completed: {result.get('summary', 'Tools researched')}"
    elif "installation guide" in action_lower:
        result = await research_agent.get_tool_installation_guide("nmap")
        guide = result.get("installation_guide", "Guide obtained")
        ctx.step["result"] = f"Installation guide retrieved: {guide}"
    else:
        request = ResearchRequest(query=ctx.action, focus="general")
        result = await research_agent.perform_research(request)
        ctx.step["result"] = f"Research completed: {result.summary}"


async def _handle_orchestrator_step(ctx: WorkflowStepContext) -> None:
    """Handle orchestrator agent step (Issue #336 - extracted handler, Issue #322 - context)."""
    action_lower = ctx.action.lower()

    if "present tool options" in action_lower:
        options = (
            "Tool options: nmap (network discovery), "
            "masscan (fast port scanner), zmap (internet scanner). "
            "Please select which tool to install."
        )
        ctx.step["result"] = options
    elif "create install plan" in action_lower:
        plan = (
            "Installation plan: 1) Update package manager, "
            "2) Install selected tool, 3) Configure tool, "
            "4) Run verification test"
        )
        ctx.step["result"] = plan
    else:
        result = await ctx.orchestrator.execute_goal(ctx.action)
        response = result.get("response", "Task coordinated")
        ctx.step["result"] = f"Orchestration completed: {response}"


async def _handle_knowledge_manager_step(ctx: WorkflowStepContext) -> None:
    """Handle knowledge manager agent step (Issue #336 - extracted handler, Issue #322 - context)."""
    from knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    content = f"Workflow step result: {ctx.step.get('result', ctx.action)}"
    metadata = {
        "workflow_id": ctx.workflow_id,
        "step_id": ctx.step["step_id"],
        "agent_type": "knowledge_manager",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }

    await kb.add_document(content, metadata)
    ctx.step["result"] = "Information stored in knowledge base for future reference"


async def _handle_security_scanner_step(ctx: WorkflowStepContext) -> None:
    """Handle security scanner agent step (Issue #336 - extracted handler, Issue #322 - context)."""
    from agents.security_scanner_agent import security_scanner_agent

    scan_context = ctx.step.get("inputs", {})
    action_lower = ctx.action.lower()

    if "port scan" in action_lower:
        scan_context["scan_type"] = "port_scan"
    elif "vulnerability" in action_lower:
        scan_context["scan_type"] = "vulnerability_scan"
    elif "ssl" in action_lower:
        scan_context["scan_type"] = "ssl_scan"
    elif "service" in action_lower:
        scan_context["scan_type"] = "service_detection"

    result = await security_scanner_agent.execute(ctx.action, scan_context)
    status = result.get("status")
    message = result.get("message", "Scan results available")
    ctx.step["result"] = f"Security scan completed: {status} - {message}"
    ctx.step["scan_results"] = result


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


async def _handle_network_discovery_step(ctx: WorkflowStepContext) -> None:
    """Handle network discovery agent step (Issue #336 - extracted handler, Issue #322 - context)."""
    from agents.network_discovery_agent import network_discovery_agent

    discovery_context = ctx.step.get("inputs", {})

    # Use dispatch pattern (Issue #315 - reduced depth)
    task_type = _detect_network_task_type(ctx.action.lower())
    if task_type:
        discovery_context["task_type"] = task_type

    result = await network_discovery_agent.execute(ctx.action, discovery_context)
    status = result.get("status")
    hosts_found = result.get("hosts_found", 0)
    ctx.step["result"] = f"Network discovery completed: {status} - Found {hosts_found} hosts"
    ctx.step["discovery_results"] = result


async def _handle_system_commands_step(ctx: WorkflowStepContext) -> None:
    """Handle system commands agent step (Issue #336 - extracted handler, Issue #322 - context)."""
    from agents.enhanced_system_commands_agent import EnhancedSystemCommandsAgent

    cmd_agent = EnhancedSystemCommandsAgent()
    action_lower = ctx.action.lower()

    if "install tool" in action_lower:
        tool_info = {"name": "nmap", "package_name": "nmap"}
        result = await cmd_agent.install_tool(tool_info, ctx.workflow_id)
        ctx.step["result"] = f"Installation result: {result.get('response', 'Tool installed')}"
    elif "verify installation" in action_lower:
        result = await cmd_agent.execute_command_with_output("nmap --version", ctx.workflow_id)
        ctx.step["result"] = f"Verification result: {result.get('output', 'Tool verified')}"
    else:
        result = await cmd_agent.execute_command_with_output(ctx.action, ctx.workflow_id)
        ctx.step["result"] = f"Command executed: {result.get('output', 'Command completed')}"


async def _handle_fallback_step(ctx: WorkflowStepContext, agent_type: str) -> None:
    """Handle unknown agent type with fallback (Issue #336 - extracted handler, Issue #322 - context)."""
    result = await ctx.orchestrator.execute_goal(f"{agent_type}: {ctx.action}")
    ctx.step["result"] = f"Executed by {agent_type}: {result.get('response', 'Task completed')}"


# Issue #336: Dispatch table for agent step handlers
# Issue #322: Updated to use WorkflowStepContext
AgentStepHandler = Callable[[WorkflowStepContext], Awaitable[None]]

AGENT_STEP_HANDLERS: Dict[str, AgentStepHandler] = {
    "librarian": _handle_librarian_step,
    "research": _handle_research_step,
    "orchestrator": _handle_orchestrator_step,
    "knowledge_manager": _handle_knowledge_manager_step,
    "security_scanner": _handle_security_scanner_step,
    "network_discovery": _handle_network_discovery_step,
    "system_commands": _handle_system_commands_step,
}


# =============================================================================
# Issue #281: Helper functions for execute_workflow
# =============================================================================


def _validate_orchestrator(request: Request):
    """Validate that the main orchestrator is available (Issue #2181: simplified).

    Issue #2181: LightweightOrchestrator was never set on app.state, making
    POST /workflow/execute always return 422. Consolidated to validate only
    the main orchestrator; simple routing is handled inline by _try_simple_response.
    """
    orchestrator = getattr(request.app.state, "orchestrator", None)

    if orchestrator is None:
        raise HTTPException(
            status_code=422,
            detail="Main orchestrator not available - application not fully initialized",
        )

    return orchestrator


# Issue #2181/#2235: Use the centralized ConversationPatterns module for
# simple-message detection.  This preserves ALL conversation types (greeting,
# farewell, gratitude, status inquiry, affirmation, negation) and their
# response templates rather than a reduced set of hardcoded regexes.
_conversation_patterns = conversation_patterns


def _try_simple_response(user_message: str) -> Dict | None:
    """Return a canned response for trivial messages, or None for complex ones.

    Consolidated from LightweightOrchestrator (Issue #2181).  Uses the
    centralized ConversationPatterns module (#2235 review fix) to cover all
    six conversation types with their canonical response templates.
    """
    conv_type = _conversation_patterns.classify_message(user_message)
    if conv_type is None:
        return None
    return {
        "success": True,
        "type": "lightweight_response",
        "result": _conversation_patterns.get_response_template(conv_type),
        "routing_method": "conversation_pattern_match",
    }


async def _execute_complex_workflow(
    workflow_request: "WorkflowExecutionRequest",
    background_tasks: BackgroundTasks,
    session_id: str,
) -> Dict:
    """Delegate a complex workflow request to WorkflowAutomationManager (#1770).

    Creates the workflow via the automation service and starts execution as a
    background task so the endpoint returns immediately.
    """
    from services.workflow_automation.routes import get_workflow_manager

    manager = get_workflow_manager()
    workflow_id = await manager.create_workflow_from_chat_request(workflow_request.user_message, session_id)

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


def _prepare_workflow_data(workflow_id: str, user_message: str, workflow_response: Dict, auto_approve: bool) -> Dict:
    """Prepare workflow data structure (Issue #281: extracted)."""
    return {
        "workflow_id": workflow_id,
        "user_message": user_message,
        "classification": workflow_response.get("message_classification"),
        "steps": [],
        "current_step": 0,
        "status": "planned",
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "workflow_start_time": time.time(),
        "estimated_duration": workflow_response.get("estimated_duration"),
        "agents_involved": workflow_response.get("agents_involved", []),
        "auto_approve": auto_approve,
    }


def _convert_preview_to_steps(workflow_preview: list) -> list:
    """Convert workflow preview to executable steps (Issue #281: extracted)."""
    steps = []
    for i, step_desc in enumerate(workflow_preview):
        step = {
            "step_id": f"step_{i+1}",
            "description": step_desc,
            "status": "pending",
            "requires_approval": "requires your approval" in step_desc,
            "agent_type": step_desc.split(":")[0].lower(),
            "action": (step_desc.split(":")[1].strip() if ":" in step_desc else step_desc),
            "started_at": None,
            "completed_at": None,
        }
        steps.append(step)
    return steps


# In-memory workflow storage (in production, use Redis or database)
active_workflows: Dict[str, Metadata] = {}
pending_approvals: Dict[str, asyncio.Future] = {}

# Locks for thread-safe access to workflow state
_workflows_lock = asyncio.Lock()
_approvals_lock = asyncio.Lock()


def _workflow_state_to_summary(state) -> Dict:
    """Convert a WorkflowState to the API summary format (#1380)."""
    meta = state.metadata or {}
    total = len(state.steps_completed) + len(state.steps_remaining)
    return {
        "workflow_id": state.workflow_id,
        "user_message": state.goal,
        "classification": meta.get("classification", "unknown"),
        "total_steps": total,
        "current_step": state.current_step,
        "status": state.current_step,
        "created_at": state.created_at,
        "estimated_duration": meta.get("estimated_duration", "unknown"),
        "agents_involved": meta.get("agents_involved", []),
    }


def _legacy_workflow_to_summary(workflow_id: str, workflow_data: Dict) -> Dict:
    """Convert a legacy in-memory workflow dict to API summary."""
    return {
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


@router.get("/workflows", response_model=WorkflowListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_active_workflows",
    error_code_prefix="WORKFLOW",
)
async def list_active_workflows(admin_check: bool = Depends(check_admin_permission)):
    """List all active workflows with their current status.

    Queries Redis-persisted workflows first, then merges legacy
    in-memory workflows.  Redis takes precedence (#1380).

    Issue #744: Requires admin authentication."""
    summaries_by_id: Dict[str, Dict] = {}

    # 1. Try Redis-persisted workflows (takes precedence)
    try:
        sm = get_workflow_state_machine()
        for state in await sm.list_active():
            summaries_by_id[state.workflow_id] = _workflow_state_to_summary(state)
    except Exception:
        logger.warning(
            "Redis workflow query failed, using in-memory only",
            exc_info=True,
        )

    # 2. Merge legacy in-memory workflows (Redis wins on conflict)
    async with _workflows_lock:
        for wf_id, wf_data in active_workflows.items():
            if wf_id not in summaries_by_id:
                summaries_by_id[wf_id] = _legacy_workflow_to_summary(wf_id, wf_data)

    workflows_list = list(summaries_by_id.values())
    return {
        "success": True,
        "active_workflows": len(workflows_list),
        "workflows": workflows_list,
    }


@router.get("/workflow/{workflow_id}", response_model=WorkflowDetailResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_workflow_details",
    error_code_prefix="WORKFLOW",
)
async def get_workflow_details(workflow_id: str, admin_check: bool = Depends(check_admin_permission)):
    """Get detailed information about a specific workflow.

    Issue #744: Requires admin authentication."""
    async with _workflows_lock:
        if workflow_id not in active_workflows:
            raise HTTPException(status_code=404, detail=ERR_WORKFLOW_NOT_FOUND)

        # Create a copy to avoid race conditions
        workflow = dict(active_workflows[workflow_id])

    return {"success": True, "workflow": workflow}


@router.get("/workflow/{workflow_id}/status", response_model=WorkflowStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_workflow_status",
    error_code_prefix="WORKFLOW",
)
async def get_workflow_status(workflow_id: str, admin_check: bool = Depends(check_admin_permission)):
    """Get current status of a workflow.

    Issue #744: Requires admin authentication."""
    if workflow_id not in active_workflows:
        raise HTTPException(status_code=404, detail=ERR_WORKFLOW_NOT_FOUND)

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


async def _resolve_approval_future(approval_key: str, approval: "WorkflowApprovalResponse") -> None:
    """Helper for approve_workflow_step. Ref: #1088.

    Pop and resolve the pending approval future for approval_key.
    Raises HTTPException(404) if no pending approval exists.
    """
    async with _approvals_lock:
        if approval_key not in pending_approvals:
            raise HTTPException(status_code=404, detail="No pending approval for this workflow step")
        future = pending_approvals.pop(approval_key)
    if not future.done():
        future.set_result(
            {
                "approved": approval.approved,
                "user_input": approval.user_input,
                "timestamp": approval.timestamp,
            }
        )


async def _update_step_status_and_metrics(workflow_id: str, approval: "WorkflowApprovalResponse") -> None:
    """Helper for approve_workflow_step. Ref: #1088.

    Update the current step's status and user_response in the workflow,
    then record the approval decision in Prometheus.
    """
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


@router.post("/workflow/{workflow_id}/approve", response_model=WorkflowApproveResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="approve_workflow_step",
    error_code_prefix="WORKFLOW",
)
async def approve_workflow_step(
    workflow_id: str,
    approval: WorkflowApprovalResponse,
    admin_check: bool = Depends(check_admin_permission),
):
    """Approve or deny a workflow step that requires user confirmation.

    Issue #744: Requires admin authentication."""
    async with _workflows_lock:
        if workflow_id not in active_workflows:
            raise HTTPException(status_code=404, detail=ERR_WORKFLOW_NOT_FOUND)

    approval_key = f"{workflow_id}_{approval.step_id}"

    # Resolve the pending future (Issue #1088: extracted helper)
    await _resolve_approval_future(approval_key, approval)

    # Update step status and record metrics (Issue #1088: extracted helper)
    await _update_step_status_and_metrics(workflow_id, approval)

    # Publish approval event
    await publish_event(
        "global",
        "workflow_approval",
        {
            "workflow_id": workflow_id,
            "step_id": approval.step_id,
            "approved": approval.approved,
            "user_input": approval.user_input,
        },
        persist=PersistStrategy.NONE,
    )

    return {
        "success": True,
        "message": f"Workflow step {'approved' if approval.approved else 'denied'}",
        "next_action": ("continue_execution" if approval.approved else "workflow_cancelled"),
    }


@router.post("/execute", response_model=WorkflowExecutionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_workflow",
    error_code_prefix="WORKFLOW",
)
async def execute_workflow(
    workflow_request: WorkflowExecutionRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Execute a workflow with coordination of multiple agents.

    Routes trivial messages via inline pattern matching and complex requests
    through the workflow automation service (WorkflowAutomationManager).

    Issue #281: Refactored from 158 lines to use extracted helper methods.
    Issue #744: Requires admin authentication.
    Issue #1770: Re-enabled complex workflow path via workflow_automation service.
    Issue #2181: Replaced LightweightOrchestrator (never set on app.state, always
    caused 422) with inline _try_simple_response + _validate_orchestrator.
    """
    # Validate main orchestrator (Issue #2181: simplified from _validate_orchestrators)
    _validate_orchestrator(request)

    # Try simple pattern match first (Issue #2181: inlined from LightweightOrchestrator)
    simple = _try_simple_response(workflow_request.user_message)
    if simple:
        return simple

    # Complex workflow — delegate to the workflow_automation service (#1770)
    try:
        session_id = str(uuid.uuid4())
        return await _execute_complex_workflow(workflow_request, background_tasks, session_id)
    except Exception as e:
        logger.error("Workflow execution error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Workflow execution failed")


async def _handle_approval_result(approval_result: dict, step: dict, workflow: dict) -> bool:
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


async def _wait_for_step_approval(workflow_id: str, workflow: dict, step: dict) -> bool | None:
    """Wait for step approval with timeout handling (Issue #315: extracted).

    Returns:
        True if approved, False if cancelled, None if timeout
    """
    from utils.async_cancellation import execute_with_cancellation

    approval_key = f"{workflow_id}_{step['step_id']}"
    approval_future = asyncio.Future()

    async with _approvals_lock:
        pending_approvals[approval_key] = approval_future

    # Publish approval request event
    await publish_event(
        "global",
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
        persist=PersistStrategy.NONE,
    )

    try:
        approval_result = await execute_with_cancellation(approval_future, f"workflow_approval_{workflow['id']}")
        return await _handle_approval_result(approval_result, step, workflow)
    except asyncio.TimeoutError:
        async with _workflows_lock:
            step["status"] = "timeout"
            workflow["status"] = "timeout"
        return None


async def _publish_step_started(workflow_id: str, step: Metadata, step_index: int, total_steps: int) -> None:
    """
    Publish workflow step started event.

    Issue #281: Extracted helper for step start event publishing.

    Args:
        workflow_id: Workflow identifier
        step: Step data
        step_index: Current step index
        total_steps: Total number of steps
    """
    await publish_event(
        "global",
        "workflow_step_started",
        {
            "workflow_id": workflow_id,
            "step_id": step["step_id"],
            "description": step["description"],
            "step_index": step_index,
            "total_steps": total_steps,
        },
        persist=PersistStrategy.NONE,
    )


async def _publish_step_completed(workflow_id: str, step: Metadata) -> None:
    """
    Publish workflow step completed event.

    Issue #281: Extracted helper for step completion event publishing.

    Args:
        workflow_id: Workflow identifier
        step: Step data with result
    """
    await publish_event(
        "global",
        "workflow_step_completed",
        {
            "workflow_id": workflow_id,
            "step_id": step["step_id"],
            "description": step["description"],
            "result": step.get("result", "Step completed successfully"),
        },
        persist=PersistStrategy.NONE,
    )


def _record_workflow_metrics(workflow_type: str, workflow_start_time: float, status: str) -> None:
    """
    Record Prometheus metrics for workflow completion.

    Issue #281: Extracted helper for metrics recording.

    Args:
        workflow_type: Type/classification of workflow
        workflow_start_time: Start timestamp
        status: 'success' or 'failed'
    """
    if workflow_start_time:
        duration = time.time() - workflow_start_time
        prometheus_metrics.record_workflow_execution(workflow_type=workflow_type, status=status, duration=duration)

        # Update active workflows count (decrement)
        prometheus_metrics.update_active_workflows(
            workflow_type=workflow_type,
            count=max(
                0,
                len([w for w in active_workflows.values() if w.get("classification") == workflow_type]) - 1,
            ),
        )


async def _execute_step_with_approval(
    workflow_id: str, workflow: Metadata, step: Metadata, step_index: int, orchestrator
) -> bool:
    """
    Execute a single workflow step, handling approval if needed.

    Issue #281: Extracted helper for step execution with approval.

    Args:
        workflow_id: Workflow identifier
        workflow: Workflow data
        step: Step to execute
        step_index: Current step index
        orchestrator: Orchestrator instance

    Returns:
        True if step completed, False if cancelled/timeout
    """
    # Check if step requires approval
    async with _workflows_lock:
        auto_approve = workflow.get("auto_approve", False)
        requires_approval = step["requires_approval"] and not auto_approve

    if requires_approval:
        async with _workflows_lock:
            step["status"] = "waiting_approval"
            step["step_index"] = step_index

        # Wait for approval using helper (Issue #315)
        approval_result = await _wait_for_step_approval(workflow_id, workflow, step)
        if approval_result is None or approval_result is False:
            return False  # Timeout or cancelled

    # Execute the step
    await execute_single_step(workflow_id, step, orchestrator)

    async with _workflows_lock:
        step["status"] = "completed"
        step["completed_at"] = datetime.now(tz=timezone.utc).isoformat()

    return True


async def _execute_step_iteration(
    workflow_id: str,
    workflow: Metadata,
    steps: list,
    step_index: int,
    step: Metadata,
    orchestrator,
) -> bool:
    """Helper for execute_workflow_steps. Ref: #1088.

    Initialize step state, publish step-started, run with approval, publish
    step-completed. Returns False if the step was cancelled or timed out,
    True on success.
    """
    async with _workflows_lock:
        workflow["current_step"] = step_index
        step["status"] = "in_progress"
        step["started_at"] = datetime.now(tz=timezone.utc).isoformat()

    # Publish step start event (Issue #281: uses helper)
    await _publish_step_started(workflow_id, step, step_index, len(steps))

    # Execute step with approval handling (Issue #281: uses helper)
    if not await _execute_step_with_approval(workflow_id, workflow, step, step_index, orchestrator):
        return False  # Timeout or cancelled

    # Publish step completion event (Issue #281: uses helper)
    await _publish_step_completed(workflow_id, step)
    return True


async def _finalize_workflow_completed(workflow_id: str, workflow: Metadata, steps: list) -> None:
    """Helper for execute_workflow_steps. Ref: #1088.

    Mark the workflow as completed, record metrics, and publish the
    workflow_completed event.
    """
    async with _workflows_lock:
        workflow["status"] = "completed"
        workflow["completed_at"] = datetime.now(tz=timezone.utc).isoformat()
        workflow_start_time = workflow.get("workflow_start_time")
        workflow_type = workflow.get("classification", "unknown")

    # Record metrics (Issue #281: uses helper)
    _record_workflow_metrics(workflow_type, workflow_start_time, "success")

    await publish_event(
        "global",
        "workflow_completed",
        {
            "workflow_id": workflow_id,
            "user_message": workflow["user_message"],
            "total_steps": len(steps),
            "execution_time": "calculated_time_here",
        },
        persist=PersistStrategy.NONE,
    )


async def _finalize_workflow_failed(workflow_id: str, workflow: Metadata, error: Exception) -> None:
    """Helper for execute_workflow_steps. Ref: #1088.

    Mark the workflow as failed, record metrics, and publish the
    workflow_failed event.
    """
    async with _workflows_lock:
        workflow["status"] = "failed"
        workflow["error"] = str(error)
        workflow_start_time = workflow.get("workflow_start_time")
        workflow_type = workflow.get("classification", "unknown")

    # Record metrics (Issue #281: uses helper)
    _record_workflow_metrics(workflow_type, workflow_start_time, "failed")

    await publish_event(
        "global",
        "workflow_failed",
        {
            "workflow_id": workflow_id,
            "error": str(error),
            "current_step": workflow.get("current_step", 0),
        },
        persist=PersistStrategy.NONE,
    )


async def execute_workflow_steps(workflow_id: str, orchestrator):
    """
    Execute workflow steps in sequence with proper coordination.

    Issue #281: Refactored from 143 lines to use extracted helper methods.
    """
    async with _workflows_lock:
        if workflow_id not in active_workflows:
            return

        workflow = active_workflows[workflow_id]
        steps = workflow["steps"]
        workflow["status"] = "executing"

    try:
        for step_index, step in enumerate(steps):
            # Execute one step: init state, approval, publish (Issue #1088: extracted)
            if not await _execute_step_iteration(workflow_id, workflow, steps, step_index, step, orchestrator):
                return  # Timeout or cancelled

        # Workflow completed (Issue #1088: extracted)
        await _finalize_workflow_completed(workflow_id, workflow, steps)

    except Exception as e:
        # Workflow failed (Issue #1088: extracted)
        await _finalize_workflow_failed(workflow_id, workflow, e)


async def execute_single_step(workflow_id: str, step: Metadata, orchestrator):
    """Execute a single workflow step with real agent integration."""
    agent_type = step["agent_type"].split(".")[1] if "." in step["agent_type"] else step["agent_type"]
    action = step["action"]
    step_id = step.get("step_id", f"step_{agent_type}")

    # Start step timing
    workflow_metrics.start_step_timing(workflow_id, step_id, agent_type)

    # Record resource usage at step start
    step_resources = system_monitor.get_current_metrics()
    workflow_metrics.record_resource_usage(workflow_id, step_resources)

    try:
        # Issue #336: Use dispatch table instead of elif chain
        # Issue #322: Create WorkflowStepContext to eliminate data clump
        ctx = WorkflowStepContext(
            workflow_id=workflow_id,
            step=step,
            orchestrator=orchestrator,
            action=action,
        )
        handler = AGENT_STEP_HANDLERS.get(agent_type)
        if handler:
            await handler(ctx)
        else:
            # Fallback to orchestrator for unknown agent types
            await _handle_fallback_step(ctx, agent_type)

    except Exception as e:
        logger.error("Error executing step %s: %s", step_id, e)
        step["result"] = "Error executing step"
        step["status"] = "failed"

        # End step timing with failure
        workflow_metrics.end_step_timing(workflow_id, step_id, success=False, error="Internal server error")

        # Record Prometheus workflow step metric (failed)
        if workflow_id in active_workflows:
            workflow_type = active_workflows[workflow_id].get("classification", "unknown")
            prometheus_metrics.record_workflow_step(workflow_type=workflow_type, step_type=agent_type, status="failed")
    else:
        # End step timing with success
        workflow_metrics.end_step_timing(workflow_id, step_id, success=True)

        # Record Prometheus workflow step metric (success)
        if workflow_id in active_workflows:
            workflow_type = active_workflows[workflow_id].get("classification", "unknown")
            prometheus_metrics.record_workflow_step(
                workflow_type=workflow_type, step_type=agent_type, status="completed"
            )


@router.delete("/workflow/{workflow_id}", response_model=WorkflowCancelResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cancel_workflow",
    error_code_prefix="WORKFLOW",
)
async def cancel_workflow(workflow_id: str, admin_check: bool = Depends(check_admin_permission)):
    """Cancel an active workflow.

    Issue #744: Requires admin authentication."""
    async with _workflows_lock:
        if workflow_id not in active_workflows:
            raise HTTPException(status_code=404, detail=ERR_WORKFLOW_NOT_FOUND)

        workflow = active_workflows[workflow_id]
        workflow["status"] = "cancelled"
        workflow["cancelled_at"] = datetime.now(tz=timezone.utc).isoformat()
        user_message = workflow.get("user_message", "")

    # Cancel any pending approvals (thread-safe)
    async with _approvals_lock:
        for key in list(pending_approvals.keys()):
            if key.startswith(workflow_id):
                future = pending_approvals.pop(key)
                if not future.done():
                    future.cancel()

    await publish_event(
        "global",
        "workflow_cancelled",
        {"workflow_id": workflow_id, "user_message": user_message},
        persist=PersistStrategy.NONE,
    )

    return {"success": True, "message": "Workflow cancelled successfully"}


@router.get(
    "/workflow/{workflow_id}/pending_approvals",
    response_model=WorkflowPendingApprovalsResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pending_approvals",
    error_code_prefix="WORKFLOW",
)
async def get_pending_approvals(workflow_id: str, admin_check: bool = Depends(check_admin_permission)):
    """Get pending approval requests for a workflow.

    Issue #744: Requires admin authentication."""
    if workflow_id not in active_workflows:
        raise HTTPException(status_code=404, detail=ERR_WORKFLOW_NOT_FOUND)

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
