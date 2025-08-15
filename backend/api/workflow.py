"""
Workflow API endpoints for multi-agent orchestration
Handles workflow approvals, progress tracking, and coordination
"""

import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from src.event_manager import event_manager
from src.metrics.system_monitor import system_monitor
from src.metrics.workflow_metrics import workflow_metrics

router = APIRouter()


# Workflow models
class WorkflowApprovalRequest(BaseModel):
    workflow_id: str
    step_id: str
    step_description: str
    required_action: str
    context: Dict[str, Any]
    timeout_seconds: int = 300


class WorkflowApprovalResponse(BaseModel):
    workflow_id: str
    step_id: str
    approved: bool
    user_input: Optional[Dict[str, Any]] = None
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
active_workflows: Dict[str, Dict[str, Any]] = {}
pending_approvals: Dict[str, asyncio.Future] = {}


@router.get("/workflows")
async def list_active_workflows():
    """List all active workflows with their current status."""
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

    return {
        "success": True,
        "active_workflows": len(active_workflows),
        "workflows": workflows_summary,
    }


@router.get("/workflow/{workflow_id}")
async def get_workflow_details(workflow_id: str):
    """Get detailed information about a specific workflow."""
    if workflow_id not in active_workflows:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow = active_workflows[workflow_id]

    return {"success": True, "workflow": workflow}


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


@router.post("/workflow/{workflow_id}/approve")
async def approve_workflow_step(workflow_id: str, approval: WorkflowApprovalResponse):
    """Approve or deny a workflow step that requires user confirmation."""
    if workflow_id not in active_workflows:
        raise HTTPException(status_code=404, detail="Workflow not found")

    approval_key = f"{workflow_id}_{approval.step_id}"

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

    # Update workflow status
    workflow = active_workflows[workflow_id]
    steps = workflow.get("steps", [])
    current_step = workflow.get("current_step", 0)

    if current_step < len(steps):
        steps[current_step]["status"] = "approved" if approval.approved else "denied"
        steps[current_step]["user_response"] = approval.user_input

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


@router.post("/execute")
async def execute_workflow(
    request: WorkflowExecutionRequest, background_tasks: BackgroundTasks
):
    """Execute a workflow with coordination of multiple agents."""
    try:
        # Import orchestrator here to avoid circular imports
        from src.orchestrator import Orchestrator

        orchestrator = Orchestrator()

        # Check if this should use workflow orchestration
        should_orchestrate = await orchestrator.should_use_workflow_orchestration(
            request.user_message
        )

        if not should_orchestrate:
            # Simple request, handle directly
            result = await orchestrator.execute_goal(request.user_message)
            return {"success": True, "type": "direct_execution", "result": result}

        # Create workflow response
        workflow_response = await orchestrator.create_workflow_response(
            request.user_message
        )
        workflow_id = (
            request.workflow_id
            or workflow_response.get("workflow_id")
            or str(uuid.uuid4())
        )

        # Store workflow in active workflows
        workflow_data = {
            "workflow_id": workflow_id,
            "user_message": request.user_message,
            "classification": workflow_response.get("message_classification"),
            "steps": [],
            "current_step": 0,
            "status": "planned",
            "created_at": datetime.now().isoformat(),
            "estimated_duration": workflow_response.get("estimated_duration"),
            "agents_involved": workflow_response.get("agents_involved", []),
            "auto_approve": request.auto_approve,
        }

        # Start workflow metrics tracking
        metrics_data = {
            "user_message": request.user_message,
            "complexity": workflow_response.get("message_classification", "unknown"),
            "total_steps": len(workflow_response.get("workflow_preview", [])),
            "agents_involved": workflow_response.get("agents_involved", []),
        }
        workflow_metrics.start_workflow_tracking(workflow_id, metrics_data)

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

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Workflow execution failed: {str(e)}"
        )


async def execute_workflow_steps(workflow_id: str, orchestrator):
    """Execute workflow steps in sequence with proper coordination."""
    if workflow_id not in active_workflows:
        return

    workflow = active_workflows[workflow_id]
    steps = workflow["steps"]

    try:
        workflow["status"] = "executing"

        for step_index, step in enumerate(steps):
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
            if step["requires_approval"] and not workflow.get("auto_approve", False):
                step["status"] = "waiting_approval"

                # Create approval request
                approval_key = f"{workflow_id}_{step['step_id']}"
                approval_future = asyncio.Future()
                pending_approvals[approval_key] = approval_future

                # Publish approval request event
                await event_manager.publish(
                    "workflow_approval_required",
                    {
                        "workflow_id": workflow_id,
                        "step_id": step["step_id"],
                        "description": step["description"],
                        "context": {
                            "step_index": step_index,
                            "agent_type": step["agent_type"],
                            "action": step["action"],
                        },
                    },
                )

                # Wait for approval (with timeout)
                try:
                    approval_result = await asyncio.wait_for(
                        approval_future, timeout=300
                    )

                    if not approval_result.get("approved", False):
                        step["status"] = "cancelled"
                        workflow["status"] = "cancelled"
                        return

                    step["user_response"] = approval_result.get("user_input")

                except asyncio.TimeoutError:
                    step["status"] = "timeout"
                    workflow["status"] = "timeout"
                    return

            # Execute the step (mock execution for demonstration)
            await execute_single_step(workflow_id, step, orchestrator)

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
        workflow["status"] = "completed"
        workflow["completed_at"] = datetime.now().isoformat()

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
        workflow["status"] = "failed"
        workflow["error"] = str(e)

        await event_manager.publish(
            "workflow_failed",
            {
                "workflow_id": workflow_id,
                "error": str(e),
                "current_step": workflow.get("current_step", 0),
            },
        )


async def execute_single_step(workflow_id: str, step: Dict[str, Any], orchestrator):
    """Execute a single workflow step with real agent integration."""
    agent_type = (
        step["agent_type"].split(".")[1]
        if "." in step["agent_type"]
        else step["agent_type"]
    )
    action = step["action"]
    description = step["description"]
    step_id = step.get("step_id", f"step_{agent_type}")

    # Start step timing
    workflow_metrics.start_step_timing(workflow_id, step_id, agent_type)

    # Record resource usage at step start
    step_resources = system_monitor.get_current_metrics()
    workflow_metrics.record_resource_usage(workflow_id, step_resources)

    try:
        if agent_type == "librarian":
            # Real knowledge base search
            from src.agents.kb_librarian_agent import KBLibrarianAgent

            kb_agent = KBLibrarianAgent()

            # Extract search query from action
            search_query = action.replace("Search Knowledge Base", "").strip()
            if not search_query:
                search_query = "network security scanning tools"  # Default based on workflow context

            result = await kb_agent.process_query(search_query)
            step[
                "result"
            ] = f"Knowledge base search completed: {result.get('response', 'Search completed')}"

        elif agent_type == "research":
            # Real web research
            from src.agents.research_agent import ResearchAgent, ResearchRequest

            research_agent = ResearchAgent()

            if "research tools" in action.lower():
                request = ResearchRequest(
                    query="network security scanning tools", focus="tools"
                )
                result = await research_agent.research_specific_tools(request)
                step[
                    "result"
                ] = f"Research completed: {result.get('summary', 'Tools researched')}"
            elif "installation guide" in action.lower():
                result = await research_agent.get_tool_installation_guide("nmap")
                step[
                    "result"
                ] = f"Installation guide retrieved: {result.get('installation_guide', 'Guide obtained')}"
            else:
                request = ResearchRequest(query=action, focus="general")
                result = await research_agent.perform_research(request)
                step["result"] = f"Research completed: {result.summary}"

        elif agent_type == "orchestrator":
            # Orchestrator coordination
            if "present tool options" in action.lower():
                step[
                    "result"
                ] = "Tool options: nmap (network discovery), masscan (fast port scanner), zmap (internet scanner). Please select which tool to install."
            elif "create install plan" in action.lower():
                step[
                    "result"
                ] = "Installation plan: 1) Update package manager, 2) Install selected tool, 3) Configure tool, 4) Run verification test"
            else:
                result = await orchestrator.execute_goal(action)
                step[
                    "result"
                ] = f"Orchestration completed: {result.get('response', 'Task coordinated')}"

        elif agent_type == "knowledge_manager":
            # Store information in knowledge base
            from src.knowledge_base import KnowledgeBase

            kb = KnowledgeBase()

            content = f"Workflow step result: {step.get('result', action)}"
            metadata = {
                "workflow_id": workflow_id,
                "step_id": step["step_id"],
                "agent_type": agent_type,
                "timestamp": datetime.now().isoformat(),
            }

            await kb.add_document(content, metadata)
            step["result"] = "Information stored in knowledge base for future reference"

        elif agent_type == "security_scanner":
            # Security scanning agent
            from src.agents.security_scanner_agent import security_scanner_agent

            # Extract scan parameters from action
            scan_context = step.get("inputs", {})
            if "port scan" in action.lower():
                scan_context["scan_type"] = "port_scan"
            elif "vulnerability" in action.lower():
                scan_context["scan_type"] = "vulnerability_scan"
            elif "ssl" in action.lower():
                scan_context["scan_type"] = "ssl_scan"
            elif "service" in action.lower():
                scan_context["scan_type"] = "service_detection"

            result = await security_scanner_agent.execute(action, scan_context)
            step[
                "result"
            ] = f"Security scan completed: {result.get('status')} - {result.get('message', 'Scan results available')}"
            step["scan_results"] = result

        elif agent_type == "network_discovery":
            # Network discovery agent
            from src.agents.network_discovery_agent import network_discovery_agent

            # Extract discovery parameters
            discovery_context = step.get("inputs", {})
            if "network scan" in action.lower():
                discovery_context["task_type"] = "network_scan"
            elif "host discovery" in action.lower():
                discovery_context["task_type"] = "host_discovery"
            elif "arp" in action.lower():
                discovery_context["task_type"] = "arp_scan"
            elif "asset inventory" in action.lower():
                discovery_context["task_type"] = "asset_inventory"
            elif "network map" in action.lower():
                discovery_context["task_type"] = "network_map"

            result = await network_discovery_agent.execute(action, discovery_context)
            step[
                "result"
            ] = f"Network discovery completed: {result.get('status')} - Found {result.get('hosts_found', 0)} hosts"
            step["discovery_results"] = result

        elif agent_type == "system_commands":
            # Real system command execution
            from src.agents.enhanced_system_commands_agent import (
                EnhancedSystemCommandsAgent,
            )

            cmd_agent = EnhancedSystemCommandsAgent()

            if "install tool" in action.lower():
                # Use the agent's install_tool method
                tool_info = {"name": "nmap", "package_name": "nmap"}
                result = await cmd_agent.install_tool(tool_info, workflow_id)
                step[
                    "result"
                ] = f"Installation result: {result.get('response', 'Tool installed')}"
            elif "verify installation" in action.lower():
                result = await cmd_agent.execute_command_with_output(
                    "nmap --version", workflow_id
                )
                step[
                    "result"
                ] = f"Verification result: {result.get('output', 'Tool verified')}"
            else:
                result = await cmd_agent.execute_command_with_output(
                    action, workflow_id
                )
                step[
                    "result"
                ] = f"Command executed: {result.get('output', 'Command completed')}"

        else:
            # Fallback to orchestrator for unknown agent types
            result = await orchestrator.execute_goal(f"{agent_type}: {action}")
            step[
                "result"
            ] = f"Executed by {agent_type}: {result.get('response', 'Task completed')}"

    except Exception as e:
        step["result"] = f"Error executing step: {str(e)}"
        step["status"] = "failed"

        # End step timing with failure
        workflow_metrics.end_step_timing(
            workflow_id, step_id, success=False, error=str(e)
        )
    else:
        # End step timing with success
        workflow_metrics.end_step_timing(workflow_id, step_id, success=True)


@router.delete("/workflow/{workflow_id}")
async def cancel_workflow(workflow_id: str):
    """Cancel an active workflow."""
    if workflow_id not in active_workflows:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow = active_workflows[workflow_id]
    workflow["status"] = "cancelled"
    workflow["cancelled_at"] = datetime.now().isoformat()

    # Cancel any pending approvals
    for key in list(pending_approvals.keys()):
        if key.startswith(workflow_id):
            future = pending_approvals.pop(key)
            if not future.done():
                future.cancel()

    await event_manager.publish(
        "workflow_cancelled",
        {"workflow_id": workflow_id, "user_message": workflow.get("user_message", "")},
    )

    return {"success": True, "message": "Workflow cancelled successfully"}


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
