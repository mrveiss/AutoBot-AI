# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Orchestration API

Advanced multi-agent orchestration endpoints with improved coordination and strategies.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.auth_middleware import get_current_user
from src.enhanced_multi_agent_orchestrator import (
    create_and_execute_workflow,
    enhanced_orchestrator,
)
from src.utils.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)


class WorkflowRequest(BaseModel):
    goal: str
    strategy: Optional[str] = None  # Let system decide if not specified
    context: Optional[dict] = None
    max_parallel_tasks: Optional[int] = 5


class AgentRecommendationRequest(BaseModel):
    task_type: str
    capabilities_needed: list[str]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_workflow",
    error_code_prefix="ORCHESTRATION",
)
@router.post("/workflow/execute")
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
    """
    try:
        logger.info("Executing workflow for goal: %s", request.goal)

        # Update max parallel tasks if specified
        if request.max_parallel_tasks:
            enhanced_orchestrator.max_parallel_tasks = request.max_parallel_tasks

        # Create and execute workflow
        result = await create_and_execute_workflow(request.goal, request.context)

        # Check if workflow was executed (has multiple steps/tasks)
        has_multiple_tasks = len(result.get("results", {})) > 1

        if has_multiple_tasks:
            # Format as workflow orchestration response that frontend expects
            workflow_preview = []
            for task_id, task_result in result.get("results", {}).items():
                description = task_result.get("description", f"Task {task_id}")
                workflow_preview.append(description)

            return JSONResponse(
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
        else:
            # Single task execution - return as direct result for simpler processing
            task_results = list(result.get("results", {}).values())
            if task_results:
                task_result = task_results[0]
                response_text = task_result.get(
                    "response", task_result.get("result", "Task completed")
                )
            else:
                response_text = "Task completed successfully"

            return JSONResponse(
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

    except Exception as e:
        logger.error("Workflow execution error: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Workflow execution failed: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_workflow_plan",
    error_code_prefix="ORCHESTRATION",
)
@router.post("/workflow/plan")
async def create_workflow_plan(
    request: WorkflowRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Create a workflow plan without executing it.

    Useful for previewing what actions will be taken before execution.

    Issue #744: Requires authenticated user.
    """
    try:
        logger.info("Creating workflow plan for: %s", request.goal)

        # Create plan
        plan = await enhanced_orchestrator.create_workflow_plan(
            request.goal, request.context
        )

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
                    "capabilities_required": [
                        cap.value for cap in task.capabilities_required
                    ],
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
        raise HTTPException(status_code=500, detail=f"Plan creation failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_performance",
    error_code_prefix="ORCHESTRATION",
)
@router.get("/agents/performance")
async def get_agent_performance(
    current_user: dict = Depends(get_current_user),
):
    """
    Get performance metrics for all agents.

    Includes success rates, average execution times, and reliability scores.

    Issue #744: Requires authenticated user.
    """
    try:
        report = enhanced_orchestrator.get_performance_report()

        return JSONResponse(
            status_code=200, content={"status": "success", "performance_data": report}
        )

    except Exception as e:
        logger.error("Performance report error: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to get performance report: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="recommend_agents",
    error_code_prefix="ORCHESTRATION",
)
@router.post("/agents/recommend")
async def recommend_agents(
    request: AgentRecommendationRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Get agent recommendations for a specific task type and capabilities.

    Returns a ranked list of suitable agents based on capabilities and performance.

    Issue #744: Requires authenticated user.
    """
    try:
        from src.enhanced_multi_agent_orchestrator import AgentCapability

        # Convert capability strings to enums
        capabilities_needed = set()
        for cap_str in request.capabilities_needed:
            try:
                capabilities_needed.add(AgentCapability(cap_str))
            except ValueError:
                logger.warning("Unknown capability: %s", cap_str)

        if not capabilities_needed:
            raise HTTPException(
                status_code=400, detail="No valid capabilities specified"
            )

        # Get recommendations
        recommendations = await enhanced_orchestrator.get_agent_recommendations(
            request.task_type, capabilities_needed
        )

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
        raise HTTPException(
            status_code=500, detail=f"Failed to get recommendations: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_active_workflows",
    error_code_prefix="ORCHESTRATION",
)
@router.get("/workflow/active")
async def get_active_workflows(
    current_user: dict = Depends(get_current_user),
):
    """
    Get list of currently active workflows.

    Issue #744: Requires authenticated user.
    """
    try:
        active_workflows = []

        for workflow_id, plan in enhanced_orchestrator.active_workflows.items():
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
        raise HTTPException(
            status_code=500, detail=f"Failed to get active workflows: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_execution_strategies",
    error_code_prefix="ORCHESTRATION",
)
@router.get("/strategies")
async def get_execution_strategies():
    """
    Get available execution strategies and their descriptions.
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

    return JSONResponse(
        status_code=200, content={"strategies": strategies, "default": "adaptive"}
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_capabilities",
    error_code_prefix="ORCHESTRATION",
)
@router.get("/capabilities")
async def get_agent_capabilities(
    current_user: dict = Depends(get_current_user),
):
    """
    Get all available agent capabilities and coverage.

    Issue #744: Requires authenticated user.
    """
    try:
        # Get capability coverage
        coverage = enhanced_orchestrator._calculate_capability_coverage()

        # Get detailed agent capabilities
        agent_details = {}
        for agent, caps in enhanced_orchestrator.agent_capabilities.items():
            agent_details[agent] = {
                "capabilities": [cap.value for cap in caps],
                "performance": {
                    "reliability": (
                        enhanced_orchestrator.agent_performance[agent].reliability_score
                    ),
                    "total_tasks": (
                        enhanced_orchestrator.agent_performance[agent].total_tasks
                    ),
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
        raise HTTPException(
            status_code=500, detail=f"Failed to get capabilities: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_orchestration_status",
    error_code_prefix="ORCHESTRATION",
)
@router.get("/status")
async def get_orchestration_status():
    """
    Get overall orchestration system status.
    """
    try:
        performance_report = enhanced_orchestrator.get_performance_report()

        return JSONResponse(
            status_code=200,
            content={
                "status": "operational",
                "active_workflows": performance_report.get("active_workflows", 0),
                "max_parallel_tasks": enhanced_orchestrator.max_parallel_tasks,
                "total_agents": len(enhanced_orchestrator.agent_capabilities),
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
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_orchestration_examples",
    error_code_prefix="ORCHESTRATION",
)
@router.get("/examples")
async def get_orchestration_examples():
    """
    Get example workflows and usage patterns.
    """
    return JSONResponse(
        status_code=200,
        content={
            "examples": {
                "parallel_research": {
                    "goal": (
                        "Research the latest developments in quantum computing and AI"
                    ),
                    "strategy": "parallel",
                    "description": (
                        "Multiple research agents work simultaneously on different aspects"
                    ),
                },
                "sequential_installation": {
                    "goal": "Install Docker, configure it, and deploy a test container",
                    "strategy": "sequential",
                    "description": "Installation steps must be performed in order",
                },
                "collaborative_analysis": {
                    "goal": (
                        "Analyze this codebase for security vulnerabilities and performance issues"
                    ),
                    "strategy": "collaborative",
                    "description": (
                        "Security and performance agents share findings in real-time"
                    ),
                },
                "pipeline_processing": {
                    "goal": (
                        "Extract data from documents, transform it, and generate a report"
                    ),
                    "strategy": "pipeline",
                    "description": "Each stage processes and passes data to the next",
                },
                "adaptive_complex": {
                    "goal": (
                        "Help me refactor this legacy application to use microservices"
                    ),
                    "strategy": "adaptive",
                    "description": (
                        "Strategy adapts based on codebase complexity and progress"
                    ),
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
