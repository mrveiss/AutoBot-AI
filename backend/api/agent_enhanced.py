# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Agent API with AI Stack Multi-Agent Integration.

This module provides enhanced agent capabilities by integrating with the AI Stack VM's
comprehensive multi-agent orchestration system, enabling intelligent task routing,
coordination, and execution across multiple specialized AI agents.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.type_defs.common import Metadata

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.dependencies import get_config, get_knowledge_base
from backend.services.ai_stack_client import AIStackError, get_ai_stack_client
from backend.utils.response_helpers import (
    create_error_response,
    create_success_response,
    handle_ai_stack_error,
)
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["agent-enhanced"])

# ====================================================================
# Request/Response Models
# ====================================================================


class EnhancedGoalPayload(BaseModel):
    """Enhanced goal payload with AI Stack integration."""

    goal: str = Field(
        ..., min_length=1, max_length=10000, description="Goal description"
    )
    agents: Optional[List[str]] = Field(None, description="Specific agents to use")
    coordination_mode: str = Field(
        "intelligent",
        description="Coordination mode (parallel, sequential, intelligent)",
    )
    priority: str = Field(
        "normal", description="Task priority (low, normal, high, urgent)"
    )
    context: Optional[str] = Field(None, description="Additional context")
    use_knowledge_base: bool = Field(True, description="Use knowledge base for context")
    include_reasoning: bool = Field(False, description="Include reasoning steps")
    max_execution_time: int = Field(
        300, ge=30, le=1800, description="Max execution time in seconds"
    )


class MultiAgentTaskPayload(BaseModel):
    """Multi-agent task coordination payload."""

    task: str = Field(..., min_length=1, description="Task description")
    agents: List[str] = Field(..., min_items=1, description="Agents to coordinate")
    coordination_strategy: str = Field("adaptive", description="Coordination strategy")
    subtasks: Optional[List[Metadata]] = Field(
        None, description="Predefined subtasks"
    )
    dependencies: Optional[List[Dict[str, str]]] = Field(
        None, description="Task dependencies"
    )


class AgentAnalysisRequest(BaseModel):
    """Agent analysis request for development and optimization."""

    analysis_type: str = Field("comprehensive", description="Analysis type")
    target_path: Optional[str] = Field(None, description="Specific path to analyze")
    include_performance: bool = Field(True, description="Include performance analysis")
    include_optimization: bool = Field(
        True, description="Include optimization suggestions"
    )


class ResearchTaskRequest(BaseModel):
    """Research task request using multiple research agents."""

    research_query: str = Field(..., min_length=1, description="Research query")
    research_depth: str = Field("comprehensive", description="Research depth")
    include_web: bool = Field(True, description="Include web research")
    include_code_search: bool = Field(False, description="Include code search")
    sources: Optional[List[str]] = Field(None, description="Specific sources")


# ====================================================================
# Utility Functions - Now imported from backend.utils.response_helpers
# (Issue #292: Duplicate code elimination)
# ====================================================================


async def get_optimal_agents_for_goal(
    goal: str, available_agents: List[str]
) -> List[str]:
    """
    Intelligently select optimal agents for a given goal.

    This function analyzes the goal and suggests the best agent combination.
    """
    goal_lower = goal.lower()
    selected_agents = []

    # Define agent capabilities and use cases
    agent_capabilities = {
        "rag": ["search", "retrieval", "document", "knowledge", "information"],
        "chat": ["conversation", "question", "explain", "discuss", "help"],
        "research": ["investigate", "analyze", "study", "explore", "find"],
        "web_research_assistant": ["web", "online", "internet", "browse", "website"],
        "knowledge_extraction": ["extract", "parse", "structure", "organize"],
        "classification": ["classify", "categorize", "identify", "tag"],
        "npu_code_search": ["code", "function", "programming", "development"],
        "development_speedup": ["optimize", "improve", "enhance", "performance"],
        "system_knowledge_manager": ["system", "infrastructure", "architecture"],
    }

    # Score agents based on goal relevance
    agent_scores = {}
    for agent, keywords in agent_capabilities.items():
        if agent in available_agents:
            score = sum(1 for keyword in keywords if keyword in goal_lower)
            if score > 0:
                agent_scores[agent] = score

    # Select top agents (max 3 for efficiency)
    selected_agents = sorted(
        agent_scores.keys(), key=lambda x: agent_scores[x], reverse=True
    )[:3]

    # Ensure we have at least one agent
    if not selected_agents and available_agents:
        # Default fallback: use chat agent if available, otherwise first available
        if "chat" in available_agents:
            selected_agents = ["chat"]
        else:
            selected_agents = [available_agents[0]]

    logger.info(f"Selected agents for goal '{goal[:50]}...': {selected_agents}")
    return selected_agents


# ====================================================================
# Enhanced Agent Goal Execution
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_enhanced_goal",
    error_code_prefix="AGENT_ENHANCED",
)
@router.post("/goal/enhanced")
async def execute_enhanced_goal(
    payload: EnhancedGoalPayload,
    request: Request,
    config=Depends(get_config),
    knowledge_base=Depends(get_knowledge_base),
):
    """
    Execute goal using enhanced AI Stack multi-agent coordination.

    This endpoint provides intelligent agent selection, task coordination,
    and knowledge base integration for superior goal achievement.
    """
    ai_client = await get_ai_stack_client()

    # Get available agents
    try:
        agents_info = await ai_client.list_available_agents()
        available_agents = agents_info.get("agents", [])
    except Exception as e:
        logger.warning(f"Could not get agent list: {e}")
        available_agents = ["chat", "rag", "research"]  # Fallback

    # Determine which agents to use
    if payload.agents:
        # Use specified agents (filtered by availability)
        selected_agents = [
            agent for agent in payload.agents if agent in available_agents
        ]
        if not selected_agents:
            raise HTTPException(
                status_code=400,
                detail=f"None of the specified agents are available. Available: {available_agents}",
            )
    else:
        # Intelligently select agents based on goal
        selected_agents = await get_optimal_agents_for_goal(
            payload.goal, available_agents
        )

    # Enhance context with knowledge base if requested
    enhanced_context = payload.context
    if payload.use_knowledge_base and knowledge_base:
        try:
            kb_results = await knowledge_base.search(query=payload.goal, top_k=5)
            if kb_results:
                kb_context = "\n".join(
                    [f"- {item.get('content', '')[:200]}..." for item in kb_results[:3]]
                )
                enhanced_context = (
                    f"{payload.context or ''}\n\nRelevant knowledge:\n{kb_context}"
                )
        except Exception as e:
            logger.warning(f"Knowledge base context enhancement failed: {e}")

    # Execute multi-agent goal
    execution_start = datetime.utcnow()

    if payload.coordination_mode == "intelligent":
        # Use intelligent coordination based on goal complexity
        if len(selected_agents) == 1:
            coordination_mode = "single"
        elif any(
            word in payload.goal.lower()
            for word in ["analyze", "research", "comprehensive"]
        ):
            coordination_mode = "sequential"
        else:
            coordination_mode = "parallel"
    else:
        coordination_mode = payload.coordination_mode

    # Execute using AI Stack multi-agent orchestration
    try:
        result = await ai_client.multi_agent_query(
            query=payload.goal,
            agents=selected_agents,
            coordination_mode=coordination_mode,
        )

        execution_end = datetime.utcnow()
        execution_time = (execution_end - execution_start).total_seconds()

        return create_success_response(
            {
                "goal": payload.goal,
                "agents_used": selected_agents,
                "coordination_mode": coordination_mode,
                "execution_time": execution_time,
                "priority": payload.priority,
                "result": result,
                "enhanced_context_used": enhanced_context is not None,
                "knowledge_base_integrated": payload.use_knowledge_base,
                "timestamp": execution_end.isoformat(),
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "Enhanced goal execution")


# ====================================================================
# Multi-Agent Task Coordination
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="coordinate_multi_agent_task",
    error_code_prefix="AGENT_ENHANCED",
)
@router.post("/multi-agent/coordinate")
async def coordinate_multi_agent_task(payload: MultiAgentTaskPayload, request: Request):
    """
    Coordinate complex multi-agent tasks with dependency management.

    This endpoint enables sophisticated multi-agent coordination with
    task dependencies, subtask management, and adaptive strategies.
    """
    try:
        ai_client = await get_ai_stack_client()

        # Validate agent availability
        agents_info = await ai_client.list_available_agents()
        available_agents = agents_info.get("agents", [])

        unavailable_agents = [
            agent for agent in payload.agents if agent not in available_agents
        ]
        if unavailable_agents:
            raise HTTPException(
                status_code=400,
                detail=f"Agents not available: {unavailable_agents}. Available: {available_agents}",
            )

        # Execute coordinated task
        coordination_start = datetime.utcnow()

        # Use AI Stack's multi-agent orchestration
        coordination_result = await ai_client.multi_agent_query(
            query=payload.task,
            agents=payload.agents,
            coordination_mode=payload.coordination_strategy,
        )

        coordination_end = datetime.utcnow()
        coordination_time = (coordination_end - coordination_start).total_seconds()

        return create_success_response(
            {
                "task": payload.task,
                "agents": payload.agents,
                "coordination_strategy": payload.coordination_strategy,
                "coordination_time": coordination_time,
                "subtasks_count": len(payload.subtasks) if payload.subtasks else 0,
                "dependencies_count": (
                    len(payload.dependencies) if payload.dependencies else 0
                ),
                "result": coordination_result,
                "timestamp": coordination_end.isoformat(),
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "Multi-agent coordination")


# ====================================================================
# Specialized Agent Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="comprehensive_research_task",
    error_code_prefix="AGENT_ENHANCED",
)
@router.post("/research/comprehensive")
async def comprehensive_research_task(
    request_data: ResearchTaskRequest, knowledge_base=Depends(get_knowledge_base)
):
    """
    Execute comprehensive research using multiple specialized agents.
    """
    try:
        ai_client = await get_ai_stack_client()

        research_agents = ["research"]
        if request_data.include_web:
            research_agents.append("web_research_assistant")
        if request_data.include_code_search:
            research_agents.append("npu_code_search")

        # Add knowledge base context
        enhanced_query = request_data.research_query
        if knowledge_base:
            try:
                kb_results = await knowledge_base.search(
                    query=request_data.research_query, top_k=3
                )
                if kb_results:
                    kb_context = "\n".join(
                        [f"- {item.get('content', '')[:150]}..." for item in kb_results]
                    )
                    enhanced_query = (
                        f"{request_data.research_query}\n\nExisting"
                        f"knowledge:\n{kb_context}"
                    )

            except Exception as e:
                logger.warning(f"KB context failed: {e}")

        # Execute research using multiple agents
        research_result = await ai_client.multi_agent_query(
            query=enhanced_query, agents=research_agents, coordination_mode="sequential"
        )

        return create_success_response(
            {
                "research_query": request_data.research_query,
                "research_depth": request_data.research_depth,
                "agents_used": research_agents,
                "include_web": request_data.include_web,
                "include_code_search": request_data.include_code_search,
                "sources": request_data.sources,
                "result": research_result,
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "Comprehensive research")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_development_task",
    error_code_prefix="AGENT_ENHANCED",
)
@router.post("/development/analyze")
async def analyze_development_task(request_data: AgentAnalysisRequest):
    """
    Analyze codebase using development-focused AI agents.
    """
    try:
        ai_client = await get_ai_stack_client()

        # Use development-focused agents
        dev_agents = ["development_speedup", "npu_code_search"]

        # Execute development analysis
        analysis_result = await ai_client.analyze_development_speedup(
            code_path=request_data.target_path, analysis_type=request_data.analysis_type
        )

        return create_success_response(
            {
                "analysis_type": request_data.analysis_type,
                "target_path": request_data.target_path,
                "include_performance": request_data.include_performance,
                "include_optimization": request_data.include_optimization,
                "agents_used": dev_agents,
                "result": analysis_result,
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "Development analysis")


# ====================================================================
# Agent Management and Status
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_available_agents",
    error_code_prefix="AGENT_ENHANCED",
)
@router.get("/agents/available")
async def list_available_agents():
    """List all available AI Stack agents with their capabilities."""
    try:
        ai_client = await get_ai_stack_client()
        agents_info = await ai_client.list_available_agents()

        # Enhance with capability descriptions
        enhanced_agents = {
            "rag": {
                "description": "Retrieval-Augmented Generation for document synthesis",
                "capabilities": [
                    "document_query",
                    "reformulate_query",
                    "analyze_documents",
                ],
            },
            "chat": {
                "description": "Conversational interactions with context awareness",
                "capabilities": ["natural_conversation", "context_retention"],
            },
            "research": {
                "description": "Comprehensive research and analysis",
                "capabilities": [
                    "research_queries",
                    "source_analysis",
                    "report_generation",
                ],
            },
            "web_research_assistant": {
                "description": "Web-based research and content analysis",
                "capabilities": [
                    "web_search",
                    "content_extraction",
                    "source_validation",
                ],
            },
            "knowledge_extraction": {
                "description": "Structured knowledge extraction from content",
                "capabilities": [
                    "entity_extraction",
                    "fact_identification",
                    "content_structuring",
                ],
            },
            "classification": {
                "description": "Content and data classification",
                "capabilities": [
                    "content_categorization",
                    "sentiment_analysis",
                    "topic_classification",
                ],
            },
            "npu_code_search": {
                "description": "NPU-accelerated code search and analysis",
                "capabilities": [
                    "code_search",
                    "function_analysis",
                    "pattern_detection",
                ],
            },
            "development_speedup": {
                "description": "Development optimization and speedup analysis",
                "capabilities": [
                    "performance_analysis",
                    "optimization_suggestions",
                    "code_quality_assessment",
                ],
            },
            "system_knowledge_manager": {
                "description": "System-wide knowledge management",
                "capabilities": [
                    "knowledge_coordination",
                    "system_insights",
                    "knowledge_synthesis",
                ],
            },
        }

        # Combine available agents with capability info
        available_list = agents_info.get("agents", [])
        enhanced_list = []

        for agent in available_list:
            agent_info = enhanced_agents.get(
                agent,
                {
                    "description": f"AI agent: {agent}",
                    "capabilities": ["general_processing"],
                },
            )
            agent_info["name"] = agent
            agent_info["status"] = "available"
            enhanced_list.append(agent_info)

        return create_success_response(
            {
                "total_agents": len(enhanced_list),
                "agents": enhanced_list,
                "coordination_modes": ["parallel", "sequential", "intelligent"],
                "multi_agent_support": True,
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "List available agents")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agents_status",
    error_code_prefix="AGENT_ENHANCED",
)
@router.get("/agents/status")
async def get_agents_status():
    """Get comprehensive status of all AI Stack agents."""
    try:
        ai_client = await get_ai_stack_client()

        # Get basic health
        health_status = await ai_client.health_check()

        # Get available agents
        agents_info = await ai_client.list_available_agents()

        return create_success_response(
            {
                "ai_stack_status": health_status["status"],
                "total_agents": len(agents_info.get("agents", [])),
                "available_agents": agents_info.get("agents", []),
                "multi_agent_coordination": True,
                "npu_acceleration": "npu_code_search" in agents_info.get("agents", []),
                "research_capabilities": any(
                    agent in agents_info.get("agents", [])
                    for agent in ["research", "web_research_assistant"]
                ),
                "development_tools": (
                    "development_speedup" in agents_info.get("agents", [])
                ),
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "Agent status check")


# ====================================================================
# Backward Compatibility Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="receive_goal_compat",
    error_code_prefix="AGENT_ENHANCED",
)
@router.post("/goal")
async def receive_goal_compat(
    goal: str = Form(...),
    use_phi2: bool = Form(False),
    user_role: str = Form("user"),
    request: Request = None,
):
    """
    Backward compatibility endpoint for goal execution.

    This maintains compatibility with the original agent API while
    providing enhanced AI Stack capabilities when available.
    """
    # Convert to enhanced payload
    enhanced_payload = EnhancedGoalPayload(
        goal=goal,
        coordination_mode="intelligent",
        use_knowledge_base=True,
        include_reasoning=False,
    )

    try:
        # Try enhanced execution first
        result = await execute_enhanced_goal(enhanced_payload, request)

        # Convert response to legacy format
        if isinstance(result, dict) and result.get("success"):
            data = result.get("data", {})
            ai_result = data.get("result", {})

            # Extract main response content
            if isinstance(ai_result, dict) and "results" in ai_result:
                # Multi-agent results - use list + join (O(n)) instead of += (O(n²))
                content_parts = [
                    agent_result["content"]
                    for agent_result in ai_result["results"].values()
                    if isinstance(agent_result, dict) and "content" in agent_result
                ]
                main_content = "\n".join(content_parts)
                response_message = main_content.strip() or "Task completed successfully"
            else:
                response_message = (
                    str(ai_result) if ai_result else "Task completed successfully"
                )

            return {"message": response_message}

    except Exception as e:
        logger.warning(f"Enhanced goal execution failed, falling back: {e}")

        # Fallback to basic response
        return {
            "message": (
                f"Goal received: {goal}. Enhanced AI capabilities temporarily unavailable."
            )
        }


# ====================================================================
# Health and Status Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_agent_health",
    error_code_prefix="AGENT_ENHANCED",
)
@router.get("/health/enhanced")
async def enhanced_agent_health():
    """Enhanced health check for agent services."""
    try:
        ai_client = await get_ai_stack_client()
        health_status = await ai_client.health_check()

        return {
            "status": health_status["status"],
            "ai_stack_available": health_status["status"] == "healthy",
            "multi_agent_coordination": health_status["status"] == "healthy",
            "enhanced_capabilities": health_status["status"] == "healthy",
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        return {
            "status": "degraded",
            "ai_stack_available": False,
            "multi_agent_coordination": False,
            "enhanced_capabilities": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }
