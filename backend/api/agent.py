import json
import logging
import time

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.constants.network_constants import NetworkConstants
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
    await event_manager.publish("user_message", {"message": goal})
    await event_manager.publish("goal_received", {"goal": goal, "use_phi2": use_phi2})

    # Track task execution start time for Prometheus metrics
    task_start_time = time.time()
    task_type = "goal_execution"
    agent_type = "orchestrator"

    orchestrator_result = await orchestrator.execute_goal(
        goal, [{"role": "user", "content": goal}]
    )

    if isinstance(orchestrator_result, dict):
        result_dict = orchestrator_result
    else:
        result_dict = {"message": str(orchestrator_result)}

    response_message = "An unexpected response format was received."
    tool_output_content = None
    tool_name = None

    tool_name = result_dict.get("tool_name")
    tool_args = result_dict.get("tool_args", {})

    # Ensure tool_args is a dictionary
    if not isinstance(tool_args, dict):
        tool_args = {}

    if tool_name == "respond_conversationally":
        default_text = "No response text provided."
        response_message = result_dict.get("response_text") or tool_args.get(
            "response_text", default_text
        )
        tool_output_content = None
    elif tool_name == "execute_system_command":
        command_output = tool_args.get("output", "")
        command_error = tool_args.get("error", "")
        command_status = tool_args.get("status", "unknown")

        if command_status == "success":
            response_message = (
                f"Command executed successfully.\nOutput:\n{command_output}"
            )
            tool_output_content = command_output
        else:
            response_message = (
                f"Command failed ({command_status}).\nError:\n{command_error}"
                f"\nOutput:\n{command_output}"
            )
            tool_output_content = (
                f"ERROR: {command_error}\nOUTPUT: {command_output}"
            )
    elif tool_name:
        tool_output_content = tool_args.get(
            "output", tool_args.get("message", str(tool_args))
        )
        response_message = f"Tool Used: {tool_name}\nOutput: {tool_output_content}"
    elif result_dict.get("output"):
        response_message = result_dict["output"]
        tool_output_content = result_dict["output"]
    elif result_dict.get("message"):
        response_message = result_dict["message"]
        tool_output_content = result_dict["message"]
    else:
        response_message = str(result_dict)
        tool_output_content = str(result_dict)

    if tool_output_content and tool_name != "respond_conversationally":
        await event_manager.publish("tool_output", {"output": tool_output_content})

    security_layer.audit_log(
        "submit_goal",
        user_role,
        "success",
        {"goal": goal, "result": response_message},
    )
    await event_manager.publish(
        "goal_completed", {"goal": goal, "result": response_message}
    )

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

    await orchestrator.pause_agent()
    security_layer.audit_log("agent_pause", user_role, "success", {})
    await event_manager.publish("agent_paused", {"message": "Agent operation paused."})
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

    await orchestrator.resume_agent()
    security_layer.audit_log("agent_resume", user_role, "success", {})
    await event_manager.publish(
        "agent_resumed", {"message": "Agent operation resumed."}
    )
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
        main_redis_client.publish(
            f"command_approval_{task_id}", json.dumps(approval_message)
        )
        logging.info(
            f"Published command approval for task {task_id}: Approved={approved}"
        )
        return {
            "message": "Approval status received and forwarded.",
            "task_id": task_id,
            "approved": approved,
        }
    else:
        error_message = (
            "Redis client not initialized. Cannot process command approval."
        )
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
    import asyncio

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

    await event_manager.publish("command_execution_start", {"command": command})
    logging.info(f"Executing command: {command}")

    process = await asyncio.create_subprocess_shell(
        command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    output = stdout.decode().strip()
    error = stderr.decode().strip()

    if process.returncode == 0:
        message = f"Command executed successfully.\nOutput:\n{output}"
        security_layer.audit_log(
            "execute_command",
            user_role,
            "success",
            {"command": command, "output": output},
        )
        await event_manager.publish(
            "command_execution_end",
            {"command": command, "status": "success", "output": output},
        )
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
