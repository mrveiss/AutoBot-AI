# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Enhanced Orchestration API

Advanced multi-agent orchestration endpoints with improved coordination and strategies.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from api.schemas_workflows import AgentRecommendationRequest, WorkflowRequest
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.logging_manager import get_logger
from autobot_shared.missing_dep import optional_import

# Issue #5040: Single Orchestrator conductor; provides all multi-agent workflow
# methods (create_workflow_plan, execute_workflow, get_performance_report, etc.).
_orch = optional_import("orchestrator", ["create_and_execute_workflow", "get_orchestrator_sync"])
create_and_execute_workflow = _orch["create_and_execute_workflow"]  # type: ignore[assignment]
if _orch["get_orchestrator_sync"]:
    orchestrator = _orch["get_orchestrator_sync"]()  # type: ignore[assignment]
    _ORCHESTRATOR_AVAILABLE = True
else:
    orchestrator = _orch["get_orchestrator_sync"]  # MissingDep stub  # type: ignore[assignment]
    _ORCHESTRATOR_AVAILABLE = False
    get_logger(__name__).warning("orchestrator module not available")

from api.schemas_common import DataResponse
from api.schemas_workflows import (
    OrchestrationActiveWorkflowsResponse,
    OrchestrationAgentPerformanceResponse,
    OrchestrationAgentRecommendResponse,
    OrchestrationCapabilitiesResponse,
    OrchestrationExamplesResponse,
    OrchestrationStatusResponse,
    OrchestrationStrategiesResponse,
    OrchestrationWorkflowPlanResponse,
)
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = get_logger(__name__)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_workflow",
    error_code_prefix="ORCHESTRATION",
)
def _build_multi_task_response(result: dict) -> JSONResponse:
    """Build response for workflows with multiple tasks. Issue #620."""
    workflow_preview = []
    for task_id, task_result in result.get("results", {}).items():
        description = task_result.get("description", f"Task {task_id}")
        workflow_preview.append(description)

    return JSONResponse(  # codeql[py/stack-trace-exposure]
        status_code=200,
        content={
            "type": "workflow_orchestration",
            "workflow_id": result.get("plan_id"),
            "workflow_response": {
                "workflow_preview": workflow_preview,
                "strategy_used": result.get("strategy_used"),
                "execution_time": result.get("execution_time"),
            },
            "details": result,
        },
    )


def _build_single_task_response(result: dict) -> JSONResponse:
    """Build response for single task execution. Issue #620."""
    task_results = list(result.get("results", {}).values())
    if task_results:
        task_result = task_results[0]
        response_text = task_result.get("response", task_result.get("result", "Task completed"))
    else:
        response_text = "Task completed successfully"

    return JSONResponse(  # codeql[py/stack-trace-exposure]
        status_code=200,
        content={
            "type": "direct_execution",
            "result": {
                "response": response_text,
                "response_text": response_text,
                "messageType": "response",
            },
            "workflow_id": result.get("plan_id"),
            "details": result,
        },
    )


@router.post("/workflow/execute", response_model=None)  # Returns JSONResponse directly — no Pydantic schema
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_workflow",
    error_code_prefix="ORCHESTRATION",
)
async def execute_workflow(
    request: WorkflowRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Execute a workflow with enhanced multi-agent orchestration.

    Features:
    - Intelligent task distribution based on agent capabilities
    - Multiple execution strategies (parallel, sequential, pipeline, collaborative, adaptive)
    - Real-time progress tracking
    - Automatic failover and retry logic

    Issue #744: Requires authenticated user.
    Issue #620: Refactored to extract _build_multi_task_response and _build_single_task_response.
    """
    if not _ORCHESTRATOR_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Orchestrator module not available",
        )
    try:
        logger.info("Executing workflow for goal: %s", request.goal)

        # Update max parallel tasks if specified
        if request.max_parallel_tasks:
            orchestrator.config.max_parallel_tasks = request.max_parallel_tasks

        # Create and execute workflow
        result = await create_and_execute_workflow(request.goal, request.context)

        # Check if workflow has multiple tasks (Issue #620: uses helpers)
        has_multiple_tasks = len(result.get("results", {})) > 1

        if has_multiple_tasks:
            return _build_multi_task_response(result)
        else:
            return _build_single_task_response(result)

    except Exception as e:
        logger.error("Workflow execution error: %s", e)
        raise HTTPException(status_code=500, detail="Workflow execution failed")


@router.post("/workflow/plan", response_model=DataResponse[OrchestrationWorkflowPlanResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_workflow_plan",
    error_code_prefix="ORCHESTRATION",
)
async def create_workflow_plan(
    request: WorkflowRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Create a workflow plan without executing it.

    Useful for previewing what actions will be taken before execution.

    Issue #744: Requires authenticated user.
    """
    if not _ORCHESTRATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Orchestrator module not available")
    try:
        logger.info("Creating workflow plan for: %s", request.goal)

        # Create plan
        plan = await orchestrator.create_workflow_plan(request.goal, request.context)

        # Convert to serializable format
        plan_dict = {
            "plan_id": plan.plan_id,
            "goal": plan.goal,
            "strategy": plan.strategy.value,
            "estimated_duration": plan.estimated_duration,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "agent_type": task.agent_type,
                    "action": task.action,
                    "priority": task.priority,
                    "dependencies": task.dependencies,
                    "capabilities_required": [cap.value for cap in task.capabilities_required],
                }
                for task in plan.tasks
            ],
            "success_criteria": plan.success_criteria,
            "resource_requirements": plan.resource_requirements,
        }

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "plan": plan_dict,
                "task_count": len(plan.tasks),
                "message": "Workflow plan created successfully",
            },
        )

    except Exception as e:
        logger.error("Plan creation error: %s", e)
        raise HTTPException(status_code=500, detail="Plan creation failed")


@router.get("/agents/performance", response_model=DataResponse[OrchestrationAgentPerformanceResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_performance",
    error_code_prefix="ORCHESTRATION",
)
async def get_agent_performance(
    current_user: dict = Depends(get_current_user),
):
    """
    Get performance metrics for all agents.

    Includes success rates, average execution times, and reliability scores.

    Issue #744: Requires authenticated user.
    """
    if not _ORCHESTRATOR_AVAILABLE:
        return JSONResponse(
            status_code=200,
            content={"status": "success", "performance_data": {}},
        )
    try:
        report = orchestrator.get_performance_report()

        return JSONResponse(status_code=200, content={"status": "success", "performance_data": report})

    except Exception as e:
        logger.error("Performance report error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get performance report")


@router.post("/agents/recommend", response_model=DataResponse[OrchestrationAgentRecommendResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="recommend_agents",
    error_code_prefix="ORCHESTRATION",
)
async def recommend_agents(
    request: AgentRecommendationRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Get agent recommendations for a specific task type and capabilities.

    Returns a ranked list of suitable agents based on capabilities and performance.

    Issue #744: Requires authenticated user.
    """
    if not _ORCHESTRATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Orchestrator module not available")
    try:
        from orchestration import AgentCapability  # noqa: PLC0415

        # Convert capability strings to enums
        capabilities_needed = set()
        for cap_str in request.capabilities_needed:
            try:
                capabilities_needed.add(AgentCapability(cap_str))
            except ValueError:
                logger.warning("Unknown capability: %s", cap_str)

        if not capabilities_needed:
            raise HTTPException(status_code=400, detail="No valid capabilities specified")

        # Get recommendations
        recommendations = await orchestrator.get_agent_recommendations(capabilities_needed)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "task_type": request.task_type,
                "capabilities_requested": request.capabilities_needed,
                "recommended_agents": recommendations,
                "agent_count": len(recommendations),
            },
        )

    except Exception as e:
        logger.error("Agent recommendation error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get recommendations")


@router.get("/workflow/active", response_model=DataResponse[OrchestrationActiveWorkflowsResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_active_workflows",
    error_code_prefix="ORCHESTRATION",
)
async def get_active_workflows(
    current_user: dict = Depends(get_current_user),
):
    """
    Get list of currently active workflows.

    Issue #744: Requires authenticated user.
    """
    if not _ORCHESTRATOR_AVAILABLE:
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "active_count": 0,
                "workflows": [],
            },
        )
    try:
        active_workflows = []

        for workflow_id, plan in orchestrator.active_workflows.items():
            active_workflows.append(
                {
                    "workflow_id": workflow_id,
                    "goal": plan.goal,
                    "strategy": plan.strategy.value,
                    "task_count": len(plan.tasks),
                    "estimated_duration": plan.estimated_duration,
                }
            )

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "active_count": len(active_workflows),
                "workflows": active_workflows,
            },
        )

    except Exception as e:
        logger.error("Active workflows error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get active workflows")


@router.get("/strategies", response_model=DataResponse[OrchestrationStrategiesResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_execution_strategies",
    error_code_prefix="ORCHESTRATION",
)
async def get_execution_strategies(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get available execution strategies and their descriptions.

    Issue #744: Requires admin authentication.
    """
    strategies = {
        "sequential": {
            "name": "Sequential",
            "description": "Execute tasks one after another in dependency order",
            "best_for": "Tasks with strict dependencies or limited resources",
        },
        "parallel": {
            "name": "Parallel",
            "description": "Execute independent tasks simultaneously",
            "best_for": "Tasks with no dependencies that can run concurrently",
        },
        "pipeline": {
            "name": "Pipeline",
            "description": "Output from one stage feeds into the next stage",
            "best_for": "Data transformation or multi-stage processing tasks",
        },
        "collaborative": {
            "name": "Collaborative",
            "description": "Agents work together sharing insights in real-time",
            "best_for": "Complex analysis requiring multiple perspectives",
        },
        "adaptive": {
            "name": "Adaptive",
            "description": "Strategy changes based on progress and performance",
            "best_for": "Unpredictable tasks or when optimal strategy is unknown",
        },
    }

    return JSONResponse(status_code=200, content={"strategies": strategies, "default": "adaptive"})


@router.get("/capabilities", response_model=DataResponse[OrchestrationCapabilitiesResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_capabilities",
    error_code_prefix="ORCHESTRATION",
)
async def get_agent_capabilities(
    current_user: dict = Depends(get_current_user),
):
    """
    Get all available agent capabilities and coverage.

    Issue #744: Requires authenticated user.
    """
    if not _ORCHESTRATOR_AVAILABLE:
        return JSONResponse(
            status_code=200,
            content={
                "capability_coverage": {},
                "agents": {},
                "total_agents": 0,
            },
        )
    try:
        # Post-#5058 refactor: capability_coverage and agent_performance live on
        # the orchestrator's collaborators (WorkflowRunner / PerformanceTracker),
        # not on the Orchestrator itself.
        runner = getattr(orchestrator, "_runner", None)
        perf_tracker = getattr(orchestrator, "_perf", None)

        if runner is not None:
            try:
                coverage = runner.get_performance_report().get("capabilities_coverage", {})
            except Exception:
                coverage = {}
        else:
            coverage = {}

        agent_perf = getattr(perf_tracker, "agent_performance", {}) if perf_tracker else {}

        # Get detailed agent capabilities
        agent_details = {}
        for agent, caps in orchestrator.agent_capabilities.items():
            perf = agent_perf.get(agent)
            agent_details[agent] = {
                "capabilities": [cap.value for cap in caps],
                "performance": {
                    "reliability": getattr(perf, "reliability_score", 1.0),
                    "total_tasks": getattr(perf, "total_tasks", 0),
                },
            }

        return JSONResponse(
            status_code=200,
            content={
                "capability_coverage": coverage,
                "agents": agent_details,
                "total_agents": len(agent_details),
            },
        )

    except Exception as e:
        logger.error("Capabilities error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get capabilities")


@router.get("/status", response_model=DataResponse[OrchestrationStatusResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_orchestration_status",
    error_code_prefix="ORCHESTRATION",
)
async def get_orchestration_status(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get overall orchestration system status.

    Issue #744: Requires admin authentication.
    """
    if not _ORCHESTRATOR_AVAILABLE:
        return JSONResponse(
            status_code=200,
            content={
                "status": "unavailable",
                "active_workflows": 0,
                "max_parallel_tasks": 0,
                "total_agents": 0,
            },
        )
    try:
        performance_report = orchestrator.get_performance_report()

        return JSONResponse(
            status_code=200,
            content={
                "status": "operational",
                "active_workflows": performance_report.get("active_workflows", 0),
                "max_parallel_tasks": orchestrator.config.max_parallel_tasks,
                "total_agents": len(orchestrator.agent_capabilities),
                "capabilities": {
                    "execution_strategies": [
                        "sequential",
                        "parallel",
                        "pipeline",
                        "collaborative",
                        "adaptive",
                    ],
                    "agent_coordination": True,
                    "performance_tracking": True,
                    "automatic_failover": True,
                    "resource_optimization": True,
                },
            },
        )

    except Exception as e:
        logger.error("Status error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get status")


@router.get("/examples", response_model=DataResponse[OrchestrationExamplesResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_orchestration_examples",
    error_code_prefix="ORCHESTRATION",
)
async def get_orchestration_examples(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get example workflows and usage patterns.

    Issue #744: Requires admin authentication.
    """
    return JSONResponse(
        status_code=200,
        content={
            "examples": {
                "parallel_research": {
                    "goal": ("Research the latest developments in quantum computing and AI"),
                    "strategy": "parallel",
                    "description": ("Multiple research agents work simultaneously on different aspects"),
                },
                "sequential_installation": {
                    "goal": "Install Docker, configure it, and deploy a test container",
                    "strategy": "sequential",
                    "description": "Installation steps must be performed in order",
                },
                "collaborative_analysis": {
                    "goal": ("Analyze this codebase for security vulnerabilities and performance issues"),
                    "strategy": "collaborative",
                    "description": ("Security and performance agents share findings in real-time"),
                },
                "pipeline_processing": {
                    "goal": ("Extract data from documents, transform it, and generate a report"),
                    "strategy": "pipeline",
                    "description": "Each stage processes and passes data to the next",
                },
                "adaptive_complex": {
                    "goal": ("Help me refactor this legacy application to use microservices"),
                    "strategy": "adaptive",
                    "description": ("Strategy adapts based on codebase complexity and progress"),
                },
            },
            "usage_tips": [
                "Use 'adaptive' strategy when unsure - it automatically adjusts",
                "Parallel execution speeds up independent tasks significantly",
                "Collaborative mode is best for complex analysis requiring multiple viewpoints",
                "Pipeline mode excels at data transformation workflows",
                "Monitor performance metrics to optimize agent selection over time",
            ],
        },
    )
