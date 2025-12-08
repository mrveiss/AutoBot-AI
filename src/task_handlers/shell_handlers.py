# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shell Command Task Handlers
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict

from src.utils.command_validator import command_validator

from .base import TaskHandler

if TYPE_CHECKING:
    from src.worker_node import WorkerNode

logger = logging.getLogger(__name__)


class ExecuteShellCommandHandler(TaskHandler):
    """Handler for execute_shell_command tasks with security validation"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """Execute validated shell command with security checks."""
        command = task_payload["command"]

        # CRITICAL SECURITY: Validate command before execution
        validation_result = command_validator.validate_command(command)

        if not validation_result["valid"]:
            # Command validation failed - SECURITY BLOCK
            result = {
                "status": "error",
                "message": (
                    f"Command blocked for security: {validation_result['reason']}"
                ),
            }
            worker.security_layer.audit_log(
                "execute_shell_command",
                user_role,
                "blocked",
                {
                    "task_id": task_id,
                    "command": command,
                    "reason": validation_result["reason"],
                    "security_event": "shell_injection_attempt_blocked",
                },
            )
            logger.warning(f"SECURITY: Blocked potentially dangerous command: {command}")
            return result

        # Command validated - proceed with secure execution
        try:
            parsed_command = validation_result["parsed_command"]
            use_shell = validation_result["use_shell"]

            if use_shell:
                # Use shell=True for commands that require it (safe because validated)
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                # Use shell=False for maximum security (preferred method)
                process = await asyncio.create_subprocess_exec(
                    *parsed_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            stdout, stderr = await process.communicate()
            output = stdout.decode().strip()
            error = stderr.decode().strip()

            if process.returncode == 0:
                result = {
                    "status": "success",
                    "message": "Command executed securely.",
                    "output": output,
                }
                worker.security_layer.audit_log(
                    "execute_shell_command",
                    user_role,
                    "success",
                    {
                        "task_id": task_id,
                        "command": command,
                        "validation_passed": True,
                        "shell_used": use_shell,
                    },
                )
            else:
                result = {
                    "status": "error",
                    "message": "Command failed.",
                    "error": error,
                    "output": output,
                    "returncode": process.returncode,
                }
                worker.security_layer.audit_log(
                    "execute_shell_command",
                    user_role,
                    "failure",
                    {
                        "task_id": task_id,
                        "command": command,
                        "error": error,
                        "validation_passed": True,
                        "shell_used": use_shell,
                    },
                )

        except Exception as e:
            result = {
                "status": "error",
                "message": f"Command execution error: {str(e)}",
            }
            worker.security_layer.audit_log(
                "execute_shell_command",
                user_role,
                "error",
                {
                    "task_id": task_id,
                    "command": command,
                    "error": str(e),
                    "validation_passed": True,
                },
            )

        return result
