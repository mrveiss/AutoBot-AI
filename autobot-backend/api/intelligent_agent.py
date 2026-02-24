# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Intelligent Agent API Endpoints

Provides REST and WebSocket endpoints for the intelligent agent system.
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Dict, List

from auth_middleware import check_admin_permission, get_current_user
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from type_defs.common import Metadata

if TYPE_CHECKING:
    from intelligence.intelligent_agent import IntelligentAgent

from monitoring.prometheus_metrics import get_metrics_manager

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

# CRITICAL FIX: Use lazy loading to prevent startup deadlock
logger = logging.getLogger(__name__)

# Prometheus metrics instance
prometheus_metrics = get_metrics_manager()

# Global agent instance with module-level lock to prevent race condition on lock initialization
_agent_instance = None
_agent_initialization_lock = (
    asyncio.Lock()
)  # Issue #395: Initialize at module level to prevent race


def get_lazy_dependencies():
    """Lazy import of heavy dependencies to prevent startup blocking"""
    try:
        from intelligence.intelligent_agent import IntelligentAgent
        from knowledge_base import KnowledgeBase
        from llm_interface import LLMInterface
        from utils.command_validator import CommandValidator
        from worker_node import WorkerNode

        return (
            IntelligentAgent,
            KnowledgeBase,
            LLMInterface,
            CommandValidator,
            WorkerNode,
        )
    except ImportError as e:
        logger.error("Failed to import intelligent agent dependencies: %s", e)
        raise HTTPException(
            status_code=503, detail="Intelligent agent dependencies not available"
        )


async def get_agent() -> "IntelligentAgent":
    """Get or create the global intelligent agent instance with lazy loading.

    Issue #395: Lock is now initialized at module level to prevent race condition.
    """
    global _agent_instance

    if _agent_instance is not None:
        return _agent_instance

    # Use module-level lock for thread-safe initialization
    async with _agent_initialization_lock:
        if _agent_instance is not None:
            return _agent_instance

        try:
            logger.info("Lazy loading intelligent agent dependencies...")
            (
                IntelligentAgent,
                KnowledgeBase,
                LLMInterface,
                CommandValidator,
                WorkerNode,
            ) = get_lazy_dependencies()

            logger.info(
                "Initializing intelligent agent with lazy-loaded dependencies..."
            ),
            _agent_instance = IntelligentAgent(
                LLMInterface(), KnowledgeBase(), WorkerNode(), CommandValidator()
            )
            await _agent_instance.initialize()
            logger.info(
                "✅ Intelligent agent initialized successfully with lazy loading"
            )
            return _agent_instance

        except Exception as e:
            logger.error("Failed to initialize intelligent agent: %s", e)
            raise HTTPException(
                status_code=503,
                detail=f"Intelligent agent initialization failed: {str(e)}",
            )


# Pydantic models for API
class GoalRequest(BaseModel):
    """Request model for natural language goals."""

    goal: str
    context: Metadata = {}


class GoalResponse(BaseModel):
    """Response model for processed goals."""

    success: bool
    result: str
    execution_time: float
    metadata: Metadata = {}


class SystemInfoResponse(BaseModel):
    """Response model for system information."""

    os_type: str
    distro: str = ""
    user: str
    capabilities: List[str]
    available_tools: List[str]


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    components: Dict[str, str]
    uptime: float


# Router - no prefix needed as it's added when mounting
router = APIRouter(tags=["intelligent-agent"])


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="process_natural_language_goal",
    error_code_prefix="INTELLIGENT_AGENT",
)
@router.post("/process", response_model=GoalResponse)
async def process_natural_language_goal(
    request: GoalRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Process a natural language goal and return the complete result.

    This endpoint processes the goal completely and returns the final result.
    For real-time streaming, use the WebSocket endpoint instead.

    Issue #744: Requires authenticated user.
    """
    # Task type and agent type for Prometheus metrics
    task_type = "natural_language_goal"
    agent_type = "intelligent_agent"

    agent = await get_agent()

    start_time = time.time()

    # Collect all chunks into a complete result
    result_chunks = []
    metadata = {}

    async for chunk in agent.process_natural_language_goal(
        request.goal, context=request.context
    ):
        result_chunks.append(f"[{chunk.chunk_type}] {chunk.content}")

        # Collect metadata from chunks
        if hasattr(chunk, "metadata") and chunk.metadata:
            metadata.update(chunk.metadata)

    execution_time = time.time() - start_time
    result = "\n".join(result_chunks)

    # Record Prometheus task execution metric (success)
    prometheus_metrics.record_task_execution(
        task_type=task_type,
        agent_type=agent_type,
        status="success",
        duration=execution_time,
    )

    return GoalResponse(
        success=True,
        result=result,
        execution_time=execution_time,
        metadata=metadata,
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_info",
    error_code_prefix="INTELLIGENT_AGENT",
)
@router.get("/system-info", response_model=SystemInfoResponse)
async def get_system_info(
    current_user: dict = Depends(get_current_user),
):
    """
    Get comprehensive system information and capabilities.

    Issue #744: Requires authenticated user.
    """
    agent = await get_agent()
    system_info = await agent.get_system_status()

    # Handle both initialized and uninitialized states
    if system_info.get("status") == "not_initialized":
        return SystemInfoResponse(
            os_type="unknown",
            distro="",
            user="",
            capabilities=[],
            available_tools=[],
        )

    # Extract from nested os_info
    os_info = system_info.get("os_info", {})
    capabilities_info = system_info.get("capabilities", {})

    return SystemInfoResponse(
        os_type=os_info.get("os_type", "unknown"),
        distro=os_info.get("distro", ""),
        user=os_info.get("user", ""),
        capabilities=list(capabilities_info.get("available_tools", {}).keys()),
        available_tools=list(capabilities_info.get("installed_tools", [])),
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="health_check",
    error_code_prefix="INTELLIGENT_AGENT",
)
@router.get("/health", response_model=HealthResponse)
async def health_check(
    current_user: dict = Depends(get_current_user),
):
    """
    Health check for the intelligent agent system.

    Issue #744: Requires authenticated user.
    """
    try:
        await get_agent()

        # Check component health
        components = {
            "agent": "healthy",
            "os_detector": "healthy",
            "goal_processor": "healthy",
            "tool_selector": "healthy",
            "streaming_executor": "healthy",
        }

        # Get uptime (placeholder - would need to track actual start time)
        uptime = 0.0
        return HealthResponse(status="healthy", components=components, uptime=uptime)

    except Exception as e:
        logger.error("Health check failed: %s", e)
        return HealthResponse(
            status="unhealthy", components={"error": str(e)}, uptime=0.0
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reload_agent",
    error_code_prefix="INTELLIGENT_AGENT",
)
@router.post("/reload")
async def reload_agent(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Reload the intelligent agent (development endpoint, thread-safe).

    Issue #744: Requires admin authentication.
    """
    global _agent_instance
    # Issue #481: Use lock when modifying global state to prevent race conditions
    async with _agent_initialization_lock:
        _agent_instance = None
    await get_agent()

    return {"status": "reloaded", "message": "Agent reloaded successfully"}


@router.websocket("/stream")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="websocket_stream",
    error_code_prefix="INTELLIGENT_AGENT",
)
async def websocket_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time streaming interaction with the agent.

    Clients can send natural language goals and receive real-time updates
    as the agent processes and executes commands.
    """
    await websocket.accept()
    logger.info("WebSocket connection established")
    try:
        agent = await get_agent()

        while True:
            # Receive goal from client
            data = await websocket.receive_json()
            goal = data.get("goal", "")
            context = data.get("context", {})

            if not goal:
                await websocket.send_json(
                    {"type": "error", "content": "No goal provided"}
                )
                continue
            logger.info("Processing WebSocket goal: %s", goal)
            try:
                # Stream chunks back to client
                async for chunk in agent.process_natural_language_goal(
                    goal, context=context
                ):
                    await websocket.send_json(
                        {
                            "type": chunk.chunk_type,
                            "content": chunk.content,
                            "metadata": getattr(chunk, "metadata", {}),
                        }
                    )
                # Send completion signal
                await websocket.send_json(
                    {"type": "complete", "content": "Goal processing completed"}
                )
            except Exception as e:
                logger.error("Error processing WebSocket goal: %s", e)
                await websocket.send_json(
                    {"type": "error", "content": f"Error processing goal: {str(e)}"}
                )
    except WebSocketDisconnect:
        logger.info("WebSocket connection closed")
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        try:
            await websocket.send_json(
                {"type": "error", "content": f"WebSocket error: {str(e)}"}
            )
        except Exception as conn_error:
            logger.debug("Connection error: %s", conn_error)  # Connection closed
