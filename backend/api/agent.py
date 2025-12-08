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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="receive_goal",
    error_code_prefix="AGENT",
)
@router.post("/goal")
async def receive_goal(request: Request, payload: GoalPayload):
    """
    Receives a goal from the user to be executed by the orchestrator.

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

    # Publish events with error handling (non-critical, log and continue)
    try:
        await event_manager.publish("user_message", {"message": goal})
        await event_manager.publish("goal_received", {"goal": goal, "use_phi2": use_phi2})
    except Exception as e:
        logger.warning(f"Failed to publish goal events: {e}")
        # Continue execution - event publishing is non-critical

    # Track task execution start time for Prometheus metrics
    task_start_time = time.time()
    task_type = "goal_execution"
    agent_type = "orchestrator"

    try:
        orchestrator_result = await orchestrator.execute_goal(
            goal, [{"role": "user", "content": goal}]
        )
    except asyncio.TimeoutError as e:
        logger.error(f"Goal execution timed out: {goal[:100]}...")
        prometheus_metrics.record_task_execution(
            task_type=task_type,
            agent_type=agent_type,
            status="timeout",
            duration=time.time() - task_start_time,
        )
        raise InternalError(
            message="Goal execution timed out. Please try again.",
            details={"goal": goal[:100], "error_type": "timeout"},
        ) from e
    except aiohttp.ClientError as e:
        logger.error(f"Network error during goal execution: {e}")
        prometheus_metrics.record_task_execution(
            task_type=task_type,
            agent_type=agent_type,
            status="network_error",
            duration=time.time() - task_start_time,
        )
        raise InternalError(
            message="Network error during goal execution. Please try again.",
            details={"error_type": "network", "error": str(e)},
        ) from e
    except Exception as e:
        logger.error(f"Failed to execute goal: {e}", exc_info=True)
        prometheus_metrics.record_task_execution(
            task_type=task_type,
            agent_type=agent_type,
            status="error",
            duration=time.time() - task_start_time,
        )
        raise InternalError(
            message=f"Goal execution failed: {str(e)}",
            details={"goal": goal[:100], "error_type": type(e).__name__},
        ) from e

    if isinstance(orchestrator_result, dict):
        result_dict = orchestrator_result
    else:
        result_dict = {"message": str(orchestrator_result)}

    # Process tool result using helper (Issue #315: reduced nesting)
    response_message, tool_output_content, tool_name = _process_tool_result(result_dict)

    if tool_output_content and tool_name != "respond_conversationally":
        # Publish event (non-critical, log and continue)
        try:
            await event_manager.publish("tool_output", {"output": tool_output_content})
        except Exception as e:
            logger.warning(f"Failed to publish tool_output event: {e}")

    security_layer.audit_log(
        "submit_goal",
        user_role,
        "success",
        {"goal": goal, "result": response_message},
    )
    # Publish event (non-critical, log and continue)
    try:
        await event_manager.publish(
            "goal_completed", {"goal": goal, "result": response_message}
        )
    except Exception as e:
        logger.warning(f"Failed to publish goal_completed event: {e}")

    # Record Prometheus task execution metric (success)
    duration = time.time() - task_start_time
    prometheus_metrics.record_task_execution(
        task_type=task_type,
        agent_type=agent_type,
        status="success",
        duration=duration,
    )

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
    if not command:
        security_layer.audit_log(
            "execute_command",
            user_role,
            "failure",
            {"command": command, "reason": "no_command_provided"},
        )
        await event_manager.publish(
            "error", {"message": "No command provided for execution."}
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

    # Publish event with error handling (non-critical)
    try:
        await event_manager.publish("command_execution_start", {"command": command})
    except Exception as e:
        logger.warning(f"Failed to publish command_execution_start event: {e}")

    logging.info(f"Executing command: {command}")

    # Execute subprocess with proper error handling
    process: Optional[asyncio.subprocess.Process] = None
    try:
        process = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=300.0,  # 5 minute timeout for command execution
        )
    except asyncio.TimeoutError:
        await _kill_timed_out_process(process)
        logger.error(f"Command timed out after 300s: {command[:100]}...")
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

    output = stdout.decode(errors="replace").strip()
    error = stderr.decode(errors="replace").strip()

    if process.returncode == 0:
        message = f"Command executed successfully.\nOutput:\n{output}"
        security_layer.audit_log(
            "execute_command",
            user_role,
            "success",
            {"command": command, "output": output},
        )
        # Publish event (non-critical, log and continue)
        try:
            await event_manager.publish(
                "command_execution_end",
                {"command": command, "status": "success", "output": output},
            )
        except Exception as e:
            logger.warning(f"Failed to publish command_execution_end event: {e}")
        logging.info(message)
        return {"message": message, "output": output, "status": "success"}
    else:
        message = (
            f"Command failed with exit code {process.returncode}."
            f"\nError:\n{error}\nOutput:\n{output}"
        )
        security_layer.audit_log(
            "execute_command",
            user_role,
            "failure",
            {"command": command, "error": error, "returncode": process.returncode},
        )
        # Publish event (non-critical, log and continue)
        try:
            await event_manager.publish(
                "command_execution_end",
                {
                    "command": command,
                    "status": "error",
                    "error": error,
                    "output": output,
                    "returncode": process.returncode,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to publish command_execution_end event: {e}")
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
