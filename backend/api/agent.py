# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import asyncio
import json
import logging
import time
from typing import Optional

import aiohttp
from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.utils.chat_exceptions import (
    InternalError,
    SubprocessError,
)
from src.constants.threshold_constants import TimingConstants
from src.monitoring.prometheus_metrics import get_metrics_manager
from src.utils.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)

# Prometheus metrics instance
prometheus_metrics = get_metrics_manager()


class GoalPayload(BaseModel):
    goal: str
    use_phi2: bool = False
    user_role: str = "user"


class CommandApprovalPayload(BaseModel):
    task_id: str
    approved: bool
    user_role: str = "user"


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
        logger.warning(f"Failed to publish {event_name} event: {e}")


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
        logger.error(f"Failed to create subprocess: {e}")
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


async def _publish_event_safe(event_manager, event_name: str, data: dict) -> None:
    """
    Publish event with error handling (non-critical operation).

    Issue #281: Extracted helper for safe event publishing.

    Args:
        event_manager: Event manager instance
        event_name: Name of event to publish
        data: Event data dictionary
    """
    try:
        await event_manager.publish(event_name, data)
    except Exception as e:
        logger.warning(f"Failed to publish {event_name} event: {e}")


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
        logger.error(f"Goal execution timed out: {goal[:100]}...")
        _record_goal_metrics(task_start_time, "timeout")
        raise InternalError(
            message="Goal execution timed out. Please try again.",
            details={"goal": goal[:100], "error_type": "timeout"},
        ) from e
    except aiohttp.ClientError as e:
        logger.error(f"Network error during goal execution: {e}")
        _record_goal_metrics(task_start_time, "network_error")
        raise InternalError(
            message="Network error during goal execution. Please try again.",
            details={"error_type": "network", "error": str(e)},
        ) from e
    except Exception as e:
        logger.error(f"Failed to execute goal: {e}", exc_info=True)
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
        logger.error(f"Failed to pause agent: {e}", exc_info=True)
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
        logger.warning(f"Failed to publish agent_paused event: {e}")
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
        logger.error(f"Failed to resume agent: {e}", exc_info=True)
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
        logger.warning(f"Failed to publish agent_resumed event: {e}")
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
            logger.error(f"Failed to publish command approval to Redis: {e}")
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
