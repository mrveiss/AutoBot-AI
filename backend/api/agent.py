# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent API with basic orchestrator functionality and AI Stack multi-agent integration.

This module provides:
- Basic agent operations (goal execution, pause/resume, command approval)
- Enhanced AI Stack capabilities (multi-agent coordination, research tasks)
- Development analysis and optimization features

Consolidated from agent.py and agent_enhanced.py per Issue #708.
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.type_defs.common import Metadata
from backend.dependencies import get_config, get_knowledge_base
from backend.services.ai_stack_client import AIStackError, get_ai_stack_client
from backend.utils.chat_exceptions import (
    InternalError,
    SubprocessError,
)
from backend.utils.response_helpers import (
    create_success_response,
    handle_ai_stack_error,
)
from src.constants.threshold_constants import TimingConstants
from src.monitoring.prometheus_metrics import get_metrics_manager
from src.utils.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)

# Prometheus metrics instance
prometheus_metrics = get_metrics_manager()

# ====================================================================
# Constants for Enhanced Agent Operations (Issue #708 consolidation)
# ====================================================================

# Performance optimization: O(1) lookup for coordination keywords (Issue #326)
COORDINATION_KEYWORDS = {"analyze", "research", "comprehensive"}

# Performance optimization: O(1) lookup for research agent names (Issue #326)
RESEARCH_AGENT_NAMES = {"research", "web_research_assistant"}

# Issue #380: Module-level tuple for fallback agent list
_FALLBACK_AGENTS = ("chat", "rag", "research")

# Issue #380: Module-level tuple for development analysis agents
_DEV_AGENTS = ("development_speedup", "npu_code_search")

# Issue #281: Agent capability definitions extracted from list_available_agents
AGENT_CAPABILITIES = {
    "rag": {
        "description": "Retrieval-Augmented Generation for document synthesis",
        "capabilities": ["document_query", "reformulate_query", "analyze_documents"],
    },
    "chat": {
        "description": "Conversational interactions with context awareness",
        "capabilities": ["natural_conversation", "context_retention"],
    },
    "research": {
        "description": "Comprehensive research and analysis",
        "capabilities": ["research_queries", "source_analysis", "report_generation"],
    },
    "web_research_assistant": {
        "description": "Web-based research and content analysis",
        "capabilities": ["web_search", "content_extraction", "source_validation"],
    },
    "knowledge_extraction": {
        "description": "Structured knowledge extraction from content",
        "capabilities": ["entity_extraction", "fact_identification", "content_structuring"],
    },
    "classification": {
        "description": "Content and data classification",
        "capabilities": ["content_categorization", "sentiment_analysis", "topic_classification"],
    },
    "npu_code_search": {
        "description": "NPU-accelerated code search and analysis",
        "capabilities": ["code_search", "function_analysis", "pattern_detection"],
    },
    "development_speedup": {
        "description": "Development optimization and speedup analysis",
        "capabilities": ["performance_analysis", "optimization_suggestions", "code_quality_assessment"],
    },
    "system_knowledge_manager": {
        "description": "System-wide knowledge management",
        "capabilities": ["knowledge_coordination", "system_insights", "knowledge_synthesis"],
    },
}

# ====================================================================
# Request/Response Models
# ====================================================================


class GoalPayload(BaseModel):
    goal: str
    use_phi2: bool = False
    user_role: str = "user"


class CommandApprovalPayload(BaseModel):
    task_id: str
    approved: bool
    user_role: str = "user"


class EnhancedGoalPayload(BaseModel):
    """Enhanced goal payload with AI Stack integration (Issue #708 consolidation)."""

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
    """Multi-agent task coordination payload (Issue #708 consolidation)."""

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
    """Agent analysis request for development and optimization (Issue #708 consolidation)."""

    analysis_type: str = Field("comprehensive", description="Analysis type")
    target_path: Optional[str] = Field(None, description="Specific path to analyze")
    include_performance: bool = Field(True, description="Include performance analysis")
    include_optimization: bool = Field(
        True, description="Include optimization suggestions"
    )


class ResearchTaskRequest(BaseModel):
    """Research task request using multiple research agents (Issue #708 consolidation)."""

    research_query: str = Field(..., min_length=1, description="Research query")
    research_depth: str = Field("comprehensive", description="Research depth")
    include_web: bool = Field(True, description="Include web research")
    include_code_search: bool = Field(False, description="Include code search")
    sources: Optional[List[str]] = Field(None, description="Specific sources")


async def _kill_timed_out_process(
    process: Optional[asyncio.subprocess.Process],
) -> None:
    """Kill a timed out subprocess safely (Issue #315: extracted)."""
    if not process:
        return
    try:
        process.kill()
        await process.wait()
    except ProcessLookupError:
        pass  # Process already terminated


def _validate_command_request(
    command: Optional[str], security_layer, user_role: str
) -> Optional[JSONResponse]:
    """
    Validate command request: check if command provided and user has permission.

    Issue #281: Extracted helper for command validation.

    Args:
        command: Command string to validate
        security_layer: Security layer for permission checks
        user_role: User's role

    Returns:
        JSONResponse with error if validation fails, None if valid
    """
    if not command:
        security_layer.audit_log(
            "execute_command",
            user_role,
            "failure",
            {"command": command, "reason": "no_command_provided"},
        )
        return JSONResponse(
            status_code=400, content={"message": "No command provided."}
        )

    if not security_layer.check_permission(
        user_role, "allow_shell_execute", resource=command
    ):
        security_layer.audit_log(
            "execute_command",
            user_role,
            "failure",
            {"command": command, "reason": "permission_denied"},
        )
        return JSONResponse(
            status_code=403,
            content={"message": "Permission denied to execute command."},
        )

    return None


async def _publish_event_safe(event_manager, event_name: str, data: dict) -> None:
    """
    Publish event with error handling (non-critical operation).

    Issue #281: Extracted helper for safe event publishing.

    Args:
        event_manager: Event manager instance
        event_name: Name of event to publish
        data: Event data
    """
    try:
        await event_manager.publish(event_name, data)
    except Exception as e:
        logger.warning("Failed to publish %s event: %s", event_name, e)


async def _run_subprocess(
    command: str, security_layer, user_role: str
) -> tuple:
    """
    Execute subprocess with timeout and error handling.

    Issue #281: Extracted helper for subprocess execution.

    Args:
        command: Command to execute
        security_layer: Security layer for audit logging
        user_role: User's role

    Returns:
        Tuple of (stdout, stderr, returncode)

    Raises:
        SubprocessError: If subprocess creation or execution fails
    """
    process: Optional[asyncio.subprocess.Process] = None
    try:
        process = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=TimingConstants.VERY_LONG_TIMEOUT,
        )
        return stdout, stderr, process.returncode
    except asyncio.TimeoutError:
        await _kill_timed_out_process(process)
        logger.error(
            f"Command timed out after {TimingConstants.VERY_LONG_TIMEOUT}s: {command[:100]}..."
        )
        security_layer.audit_log(
            "execute_command",
            user_role,
            "failure",
            {"command": command, "reason": "timeout"},
        )
        raise SubprocessError(
            message="Command execution timed out after 5 minutes",
            command=command[:200],
            return_code=None,
        )
    except OSError as e:
        logger.error("Failed to create subprocess: %s", e)
        security_layer.audit_log(
            "execute_command",
            user_role,
            "failure",
            {"command": command, "reason": "subprocess_creation_failed", "error": str(e)},
        )
        raise SubprocessError(
            message=f"Failed to execute command: {e}",
            command=command[:200],
        ) from e


def _build_success_response(
    command: str, output: str, security_layer, user_role: str
) -> dict:
    """
    Build success response and audit log.

    Issue #281: Extracted helper for success response building.

    Args:
        command: Executed command
        output: Command output
        security_layer: Security layer for audit logging
        user_role: User's role

    Returns:
        Success response dict
    """
    message = f"Command executed successfully.\nOutput:\n{output}"
    security_layer.audit_log(
        "execute_command",
        user_role,
        "success",
        {"command": command, "output": output},
    )
    logging.info(message)
    return {"message": message, "output": output, "status": "success"}


def _build_error_response(
    command: str, output: str, error: str, returncode: int, security_layer, user_role: str
) -> JSONResponse:
    """
    Build error response and audit log.

    Issue #281: Extracted helper for error response building.

    Args:
        command: Executed command
        output: Command stdout
        error: Command stderr
        returncode: Process return code
        security_layer: Security layer for audit logging
        user_role: User's role

    Returns:
        JSONResponse with error details
    """
    message = (
        f"Command failed with exit code {returncode}."
        f"\nError:\n{error}\nOutput:\n{output}"
    )
    security_layer.audit_log(
        "execute_command",
        user_role,
        "failure",
        {"command": command, "error": error, "returncode": returncode},
    )
    logging.error(message)
    return JSONResponse(
        status_code=500,
        content={
            "message": message,
            "error": error,
            "output": output,
            "status": "error",
        },
    )


def _process_tool_result(result_dict: dict) -> tuple:
    """Process orchestrator result and extract message/output (Issue #315: extracted).

    Returns:
        Tuple of (response_message, tool_output_content, tool_name)
    """
    tool_name = result_dict.get("tool_name")
    tool_args = result_dict.get("tool_args", {})

    # Ensure tool_args is a dictionary
    if not isinstance(tool_args, dict):
        tool_args = {}

    # Handle respond_conversationally tool
    if tool_name == "respond_conversationally":
        default_text = "No response text provided."
        response_message = result_dict.get("response_text") or tool_args.get(
            "response_text", default_text
        )
        return response_message, None, tool_name

    # Handle execute_system_command tool
    if tool_name == "execute_system_command":
        command_output = tool_args.get("output", "")
        command_error = tool_args.get("error", "")
        command_status = tool_args.get("status", "unknown")

        if command_status == "success":
            response_message = (
                f"Command executed successfully.\nOutput:\n{command_output}"
            )
            return response_message, command_output, tool_name
        else:
            response_message = (
                f"Command failed ({command_status}).\nError:\n{command_error}"
                f"\nOutput:\n{command_output}"
            )
            tool_output = f"ERROR: {command_error}\nOUTPUT: {command_output}"
            return response_message, tool_output, tool_name

    # Handle other named tools
    if tool_name:
        tool_output_content = tool_args.get(
            "output", tool_args.get("message", str(tool_args))
        )
        response_message = f"Tool Used: {tool_name}\nOutput: {tool_output_content}"
        return response_message, tool_output_content, tool_name

    # Handle output/message fallbacks
    if result_dict.get("output"):
        return result_dict["output"], result_dict["output"], None

    if result_dict.get("message"):
        return result_dict["message"], result_dict["message"], None

    # Default fallback
    return str(result_dict), str(result_dict), None


def _record_goal_metrics(task_start_time: float, status: str) -> None:
    """
    Record Prometheus metrics for goal execution.

    Issue #281: Extracted helper for metrics recording.

    Args:
        task_start_time: Start timestamp
        status: Execution status (success, timeout, network_error, error)
    """
    prometheus_metrics.record_task_execution(
        task_type="goal_execution",
        agent_type="orchestrator",
        status=status,
        duration=time.time() - task_start_time,
    )


async def _execute_goal_with_error_handling(
    orchestrator, goal: str, task_start_time: float
) -> dict:
    """
    Execute goal with comprehensive error handling.

    Issue #281: Extracted helper for goal execution with error handling.

    Args:
        orchestrator: Orchestrator instance
        goal: Goal string to execute
        task_start_time: Start timestamp for metrics

    Returns:
        Result dictionary from orchestrator

    Raises:
        InternalError: On timeout, network, or general execution errors
    """
    try:
        orchestrator_result = await orchestrator.execute_goal(
            goal, [{"role": "user", "content": goal}]
        )
    except asyncio.TimeoutError as e:
        logger.error("Goal execution timed out: %s...", goal[:100])
        _record_goal_metrics(task_start_time, "timeout")
        raise InternalError(
            message="Goal execution timed out. Please try again.",
            details={"goal": goal[:100], "error_type": "timeout"},
        ) from e
    except aiohttp.ClientError as e:
        logger.error("Network error during goal execution: %s", e)
        _record_goal_metrics(task_start_time, "network_error")
        raise InternalError(
            message="Network error during goal execution. Please try again.",
            details={"error_type": "network", "error": str(e)},
        ) from e
    except Exception as e:
        logger.error("Failed to execute goal: %s", e, exc_info=True)
        _record_goal_metrics(task_start_time, "error")
        raise InternalError(
            message=f"Goal execution failed: {str(e)}",
            details={"goal": goal[:100], "error_type": type(e).__name__},
        ) from e

    if isinstance(orchestrator_result, dict):
        return orchestrator_result
    return {"message": str(orchestrator_result)}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="receive_goal",
    error_code_prefix="AGENT",
)
@router.post("/goal")
async def receive_goal(request: Request, payload: GoalPayload):
    """
    Receives a goal from the user to be executed by the orchestrator.

    Issue #281: Refactored from 130 lines to use extracted helper methods.

    Args:
        payload (GoalPayload): The payload containing the goal, whether to
            use Phi-2 model, and user role.

    Returns:
        dict: The result of the goal execution.

    Raises:
        JSONResponse: Returns a 403 error if permission is denied, or a 500
            error if an internal error occurs.
    """
    from src.event_manager import event_manager

    orchestrator = request.app.state.orchestrator
    security_layer = request.app.state.security_layer

    goal = payload.goal
    use_phi2 = payload.use_phi2
    user_role = payload.user_role

    if not security_layer.check_permission(user_role, "allow_goal_submission"):
        security_layer.audit_log(
            "submit_goal",
            user_role,
            "denied",
            {"goal": goal, "reason": "permission_denied"},
        )
        return JSONResponse(
            status_code=403, content={"message": "Permission denied to submit goal"}
        )

    logging.info(f"Received goal via API: {goal}")

    # Publish events (Issue #281: uses helper)
    await _publish_event_safe(event_manager, "user_message", {"message": goal})
    await _publish_event_safe(event_manager, "goal_received", {"goal": goal, "use_phi2": use_phi2})

    # Track task execution start time for Prometheus metrics
    task_start_time = time.time()

    # Execute goal (Issue #281: uses helper)
    result_dict = await _execute_goal_with_error_handling(orchestrator, goal, task_start_time)

    # Process tool result using helper (Issue #315: reduced nesting)
    response_message, tool_output_content, tool_name = _process_tool_result(result_dict)

    if tool_output_content and tool_name != "respond_conversationally":
        await _publish_event_safe(event_manager, "tool_output", {"output": tool_output_content})

    security_layer.audit_log(
        "submit_goal",
        user_role,
        "success",
        {"goal": goal, "result": response_message},
    )

    await _publish_event_safe(
        event_manager, "goal_completed", {"goal": goal, "result": response_message}
    )

    # Record Prometheus task execution metric (success)
    _record_goal_metrics(task_start_time, "success")

    return {"message": response_message}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="pause_agent",
    error_code_prefix="AGENT",
)
@router.post("/pause")
async def pause_agent_api(request: Request, user_role: str = Form("user")):
    """
    Pauses the agent's current operation.
    Note: This is currently a placeholder and returns a success status
    without actual functionality. Full implementation will be added with
    backend integration.
    """
    from src.event_manager import event_manager

    security_layer = request.app.state.security_layer
    orchestrator = request.app.state.orchestrator
    if not security_layer.check_permission(user_role, "allow_agent_control"):
        security_layer.audit_log(
            "agent_pause", user_role, "denied", {"reason": "permission_denied"}
        )
        return JSONResponse(
            status_code=403, content={"message": "Permission denied to pause agent."}
        )

    try:
        await orchestrator.pause_agent()
    except Exception as e:
        logger.error("Failed to pause agent: %s", e, exc_info=True)
        security_layer.audit_log(
            "agent_pause", user_role, "failure", {"error": str(e)}
        )
        raise InternalError(
            message=f"Failed to pause agent: {str(e)}",
            details={"error_type": type(e).__name__},
        ) from e

    security_layer.audit_log("agent_pause", user_role, "success", {})
    # Publish event (non-critical)
    try:
        await event_manager.publish("agent_paused", {"message": "Agent operation paused."})
    except Exception as e:
        logger.warning("Failed to publish agent_paused event: %s", e)
    return {"message": "Agent paused successfully."}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="resume_agent",
    error_code_prefix="AGENT",
)
@router.post("/resume")
async def resume_agent_api(request: Request, user_role: str = Form("user")):
    """
    Resumes the agent's operation if paused.
    Note: This is currently a placeholder and returns a success status without
    actual functionality.
    Full implementation will be added with backend integration.
    """
    from src.event_manager import event_manager

    security_layer = request.app.state.security_layer
    orchestrator = request.app.state.orchestrator
    if not security_layer.check_permission(user_role, "allow_agent_control"):
        security_layer.audit_log(
            "agent_resume", user_role, "denied", {"reason": "permission_denied"}
        )
        return JSONResponse(
            status_code=403, content={"message": "Permission denied to resume agent."}
        )

    try:
        await orchestrator.resume_agent()
    except Exception as e:
        logger.error("Failed to resume agent: %s", e, exc_info=True)
        security_layer.audit_log(
            "agent_resume", user_role, "failure", {"error": str(e)}
        )
        raise InternalError(
            message=f"Failed to resume agent: {str(e)}",
            details={"error_type": type(e).__name__},
        ) from e

    security_layer.audit_log("agent_resume", user_role, "success", {})
    # Publish event (non-critical)
    try:
        await event_manager.publish(
            "agent_resumed", {"message": "Agent operation resumed."}
        )
    except Exception as e:
        logger.warning("Failed to publish agent_resumed event: %s", e)
    return {"message": "Agent resumed successfully."}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="command_approval",
    error_code_prefix="AGENT",
)
@router.post("/command_approval")
async def command_approval(request: Request, payload: CommandApprovalPayload):
    """
    Receives user approval/denial for a command execution.
    """
    security_layer = request.app.state.security_layer
    main_redis_client = request.app.state.main_redis_client

    task_id = payload.task_id
    approved = payload.approved
    user_role = payload.user_role

    if not security_layer.check_permission(user_role, "allow_command_approval"):
        security_layer.audit_log(
            "command_approval",
            user_role,
            "denied",
            {"task_id": task_id, "approved": approved, "reason": "permission_denied"},
        )
        return JSONResponse(
            status_code=403,
            content={"message": "Permission denied to approve/deny commands."},
        )

    if main_redis_client:
        approval_message = {"task_id": task_id, "approved": approved}
        try:
            # Issue #361 - avoid blocking
            await asyncio.to_thread(
                main_redis_client.publish,
                f"command_approval_{task_id}",
                json.dumps(approval_message),
            )
        except Exception as e:
            logger.error("Failed to publish command approval to Redis: %s", e)
            security_layer.audit_log(
                "command_approval",
                user_role,
                "failure",
                {"task_id": task_id, "approved": approved, "error": str(e)},
            )
            raise InternalError(
                message="Failed to forward command approval. Please try again.",
                details={"task_id": task_id, "error_type": "redis_publish_failed"},
            ) from e
        logging.info(
            f"Published command approval for task {task_id}: Approved={approved}"
        )
        return {
            "message": "Approval status received and forwarded.",
            "task_id": task_id,
            "approved": approved,
        }
    else:
        error_message = "Redis client not initialized. Cannot process command approval."
        logging.error(error_message)
        return JSONResponse(status_code=500, content={"message": error_message})


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_command",
    error_code_prefix="AGENT",
)
@router.post("/execute_command")
async def execute_command(
    request: Request, command_data: dict, user_role: str = Form("user")
):
    """
    Executes a shell command and returns its output.

    Issue #281: Refactored from 151 lines to use extracted helper methods.

    Args:
        command_data (dict): A dictionary containing the command to execute.
        user_role (str): The role of the user executing the command.

    Returns:
        dict: A dictionary containing the result of the command execution.

    Raises:
        JSONResponse: Returns a 400 error if no command is provided,
                      a 403 error if permission is denied,
                      or a 500 error if an internal error occurs.
    """
    from src.event_manager import event_manager

    security_layer = request.app.state.security_layer
    command = command_data.get("command")

    # Validate command request (Issue #281: uses helper)
    validation_error = _validate_command_request(command, security_layer, user_role)
    if validation_error:
        if not command:
            await _publish_event_safe(
                event_manager, "error", {"message": "No command provided for execution."}
            )
        return validation_error

    # Publish start event (Issue #281: uses helper)
    await _publish_event_safe(
        event_manager, "command_execution_start", {"command": command}
    )
    logging.info(f"Executing command: {command}")

    # Execute subprocess (Issue #281: uses helper)
    stdout, stderr, returncode = await _run_subprocess(
        command, security_layer, user_role
    )

    output = stdout.decode(errors="replace").strip()
    error = stderr.decode(errors="replace").strip()

    # Build and return response based on result (Issue #281: uses helpers)
    if returncode == 0:
        response = _build_success_response(command, output, security_layer, user_role)
        await _publish_event_safe(
            event_manager,
            "command_execution_end",
            {"command": command, "status": "success", "output": output},
        )
        return response
    else:
        response = _build_error_response(
            command, output, error, returncode, security_layer, user_role
        )
        await _publish_event_safe(
            event_manager,
            "command_execution_end",
            {
                "command": command,
                "status": "error",
                "error": error,
                "output": output,
                "returncode": returncode,
            },
        )
        return response


# ====================================================================
# Enhanced Agent Functions with AI Stack Integration (Issue #708 consolidation)
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

    logger.info("Selected agents for goal '%s...': %s", goal[:50], selected_agents)
    return selected_agents


async def _select_agents_for_goal(ai_client, payload, available_agents: list) -> list:
    """Select agents for goal execution (Issue #398: extracted).

    Args:
        ai_client: AI Stack client instance
        payload: Goal payload with optional agent specification
        available_agents: List of available agent names

    Returns:
        List of selected agent names

    Raises:
        HTTPException: If no specified agents are available
    """
    if payload.agents:
        selected = [agent for agent in payload.agents if agent in available_agents]
        if not selected:
            raise HTTPException(
                status_code=400,
                detail=f"None of the specified agents are available. Available: {available_agents}",
            )
        return selected
    return await get_optimal_agents_for_goal(payload.goal, available_agents)


async def _enhance_context_with_kb(payload, knowledge_base) -> str | None:
    """Enhance context with knowledge base results (Issue #398: extracted).

    Args:
        payload: Goal payload with context and KB settings
        knowledge_base: Knowledge base instance or None

    Returns:
        Enhanced context string or original context
    """
    if not (payload.use_knowledge_base and knowledge_base):
        return payload.context

    try:
        kb_results = await knowledge_base.search(query=payload.goal, top_k=5)
        if kb_results:
            kb_context = "\n".join([f"- {item.get('content', '')[:200]}..." for item in kb_results[:3]])
            return f"{payload.context or ''}\n\nRelevant knowledge:\n{kb_context}"
    except Exception as e:
        logger.warning("Knowledge base context enhancement failed: %s", e)
    return payload.context


def _determine_coordination_mode(payload, selected_agents: list) -> str:
    """Determine coordination mode for multi-agent execution (Issue #398: extracted)."""
    if payload.coordination_mode != "intelligent":
        return payload.coordination_mode

    if len(selected_agents) == 1:
        return "single"
    elif any(word in payload.goal.lower() for word in COORDINATION_KEYWORDS):
        return "sequential"
    return "parallel"


# ====================================================================
# Enhanced Agent Endpoints (Issue #708 consolidation)
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_enhanced_goal",
    error_code_prefix="AGENT",
)
@router.post("/goal/enhanced")
async def execute_enhanced_goal(
    payload: EnhancedGoalPayload,
    request: Request,
    config=Depends(get_config),
    knowledge_base=Depends(get_knowledge_base),
):
    """Execute goal using enhanced AI Stack multi-agent coordination (Issue #398: refactored)."""
    ai_client = await get_ai_stack_client()

    # Get available agents
    try:
        agents_info = await ai_client.list_available_agents()
        available_agents = agents_info.get("agents", [])
    except Exception as e:
        logger.warning("Could not get agent list: %s", e)
        available_agents = list(_FALLBACK_AGENTS)

    # Issue #398: Use extracted helpers
    selected_agents = await _select_agents_for_goal(ai_client, payload, available_agents)
    enhanced_context = await _enhance_context_with_kb(payload, knowledge_base)
    coordination_mode = _determine_coordination_mode(payload, selected_agents)

    execution_start = datetime.utcnow()

    try:
        result = await ai_client.multi_agent_query(
            query=payload.goal,
            agents=selected_agents,
            coordination_mode=coordination_mode,
        )

        execution_time = (datetime.utcnow() - execution_start).total_seconds()

        return create_success_response({
            "goal": payload.goal,
            "agents_used": selected_agents,
            "coordination_mode": coordination_mode,
            "execution_time": execution_time,
            "priority": payload.priority,
            "result": result,
            "enhanced_context_used": enhanced_context is not None,
            "knowledge_base_integrated": payload.use_knowledge_base,
            "timestamp": datetime.utcnow().isoformat(),
        })

    except AIStackError as e:
        await handle_ai_stack_error(e, "Enhanced goal execution")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="coordinate_multi_agent_task",
    error_code_prefix="AGENT",
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="comprehensive_research_task",
    error_code_prefix="AGENT",
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
                logger.warning("KB context failed: %s", e)

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
    error_code_prefix="AGENT",
)
@router.post("/development/analyze")
async def analyze_development_task(request_data: AgentAnalysisRequest):
    """
    Analyze codebase using development-focused AI agents.
    """
    try:
        ai_client = await get_ai_stack_client()

        # Issue #380: Use module-level constant for dev agents
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
                "agents_used": _DEV_AGENTS,  # Issue #380: use module constant
                "result": analysis_result,
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "Development analysis")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_available_agents",
    error_code_prefix="AGENT",
)
@router.get("/agents/available")
async def list_available_agents():
    """
    List all available AI Stack agents with their capabilities.

    Issue #281: Refactored to use module-level AGENT_CAPABILITIES constant.
    """
    try:
        ai_client = await get_ai_stack_client()
        agents_info = await ai_client.list_available_agents()

        # Issue #281: Use module-level constant for agent capabilities
        # Combine available agents with capability info
        available_list = agents_info.get("agents", [])
        enhanced_list = []

        for agent in available_list:
            # Get capabilities from module constant, with fallback for unknown agents
            agent_info = AGENT_CAPABILITIES.get(
                agent,
                {
                    "description": f"AI agent: {agent}",
                    "capabilities": ["general_processing"],
                },
            ).copy()  # Copy to avoid modifying the constant
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
    error_code_prefix="AGENT",
)
@router.get("/agents/status")
async def get_agents_status():
    """Get comprehensive status of all AI Stack agents."""
    try:
        ai_client = await get_ai_stack_client()

        # Issue #664: Parallelize independent AI Stack queries
        health_status, agents_info = await asyncio.gather(
            ai_client.health_check(),
            ai_client.list_available_agents(),
        )

        return create_success_response(
            {
                "ai_stack_status": health_status["status"],
                "total_agents": len(agents_info.get("agents", [])),
                "available_agents": agents_info.get("agents", []),
                "multi_agent_coordination": True,
                "npu_acceleration": "npu_code_search" in agents_info.get("agents", []),
                "research_capabilities": any(
                    agent in agents_info.get("agents", [])
                    for agent in RESEARCH_AGENT_NAMES
                ),
                "development_tools": (
                    "development_speedup" in agents_info.get("agents", [])
                ),
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "Agent status check")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_agent_health",
    error_code_prefix="AGENT",
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