# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shell Command Task Handlers

Issue #322: Refactored to use TaskExecutionContext to eliminate data clump pattern.
"""

import asyncio
import logging
from typing import Any, Dict

from backend.models.task_context import TaskExecutionContext
from backend.utils.command_validator import command_validator

from .base import TaskHandler

logger = logging.getLogger(__name__)


class ExecuteShellCommandHandler(TaskHandler):
    """Handler for execute_shell_command tasks with security validation"""

    def _handle_validation_failure(
        self,
        ctx: TaskExecutionContext,
        command: str,
        validation_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle command validation failure and log security event.

        Issue #281: Extracted helper for validation failure handling.
        Issue #322: Refactored to use TaskExecutionContext.

        Args:
            ctx: TaskExecutionContext with worker, user_role, task_id
            command: Original command that failed validation
            validation_result: Validation result with reason

        Returns:
            Error result dict with security block message
        """
        result = {
            "status": "error",
            "message": (f"Command blocked for security: {validation_result['reason']}"),
        }
        ctx.audit_log(
            "execute_shell_command",
            "blocked",
            {
                "command": command,
                "reason": validation_result["reason"],
                "security_event": "shell_injection_attempt_blocked",
            },
        )
        logger.warning("SECURITY: Blocked potentially dangerous command: %s", command)
        return result

    async def _run_subprocess(
        self,
        command: str,
        parsed_command: list,
        use_shell: bool,
    ) -> tuple:
        """
        Run command as subprocess and return output.

        Issue #281: Extracted helper for subprocess execution.

        Args:
            command: Original command string
            parsed_command: Parsed command list
            use_shell: Whether to use shell=True

        Returns:
            Tuple of (returncode, stdout, stderr)
        """
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
        return (
            process.returncode,
            stdout.decode().strip(),
            stderr.decode().strip(),
        )

    def _build_success_result(
        self,
        ctx: TaskExecutionContext,
        output: str,
        command: str,
        use_shell: bool,
    ) -> Dict[str, Any]:
        """
        Build success result dict and log audit entry.

        Issue #620.

        Args:
            ctx: TaskExecutionContext with worker, user_role, task_id
            output: Stdout content
            command: Original command
            use_shell: Whether shell was used

        Returns:
            Success result dict
        """
        ctx.audit_log(
            "execute_shell_command",
            "success",
            {"command": command, "validation_passed": True, "shell_used": use_shell},
        )
        return {
            "status": "success",
            "message": "Command executed securely.",
            "output": output,
        }

    def _build_error_result(
        self,
        ctx: TaskExecutionContext,
        output: str,
        error: str,
        returncode: int,
        command: str,
        use_shell: bool,
    ) -> Dict[str, Any]:
        """
        Build error result dict and log audit entry.

        Issue #620.

        Args:
            ctx: TaskExecutionContext with worker, user_role, task_id
            output: Stdout content
            error: Stderr content
            returncode: Process return code
            command: Original command
            use_shell: Whether shell was used

        Returns:
            Error result dict
        """
        ctx.audit_log(
            "execute_shell_command",
            "failure",
            {
                "command": command,
                "error": error,
                "validation_passed": True,
                "shell_used": use_shell,
            },
        )
        return {
            "status": "error",
            "message": "Command failed.",
            "error": error,
            "output": output,
            "returncode": returncode,
        }

    def _build_result_and_log(
        self,
        ctx: TaskExecutionContext,
        returncode: int,
        output: str,
        error: str,
        command: str,
        use_shell: bool,
    ) -> Dict[str, Any]:
        """
        Build result dict and log audit based on return code.

        Issue #281: Extracted helper for result building and audit logging.
        Issue #322: Refactored to use TaskExecutionContext.
        Issue #620: Further extraction to _build_success_result/_build_error_result.

        Args:
            ctx: TaskExecutionContext with worker, user_role, task_id
            returncode: Process return code
            output: Stdout content
            error: Stderr content
            command: Original command
            use_shell: Whether shell was used

        Returns:
            Result dict with status and output
        """
        if returncode == 0:
            return self._build_success_result(ctx, output, command, use_shell)
        return self._build_error_result(
            ctx, output, error, returncode, command, use_shell
        )

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """
        Execute validated shell command with security checks.

        Issue #281: Refactored from 115 lines to use extracted helper methods.
        Issue #322: Refactored to use TaskExecutionContext.
        """
        command = ctx.require_payload_value("command")

        # CRITICAL SECURITY: Validate command before execution
        validation_result = command_validator.validate_command(command)

        if not validation_result["valid"]:
            # Issue #281: uses helper, Issue #322: uses context
            return self._handle_validation_failure(ctx, command, validation_result)

        # Command validated - proceed with secure execution
        try:
            parsed_command = validation_result["parsed_command"]
            use_shell = validation_result["use_shell"]

            # Issue #281: uses helper
            returncode, output, error = await self._run_subprocess(
                command, parsed_command, use_shell
            )

            # Issue #281: uses helper, Issue #322: uses context
            return self._build_result_and_log(
                ctx, returncode, output, error, command, use_shell
            )

        except Exception as e:
            result = {
                "status": "error",
                "message": f"Command execution error: {str(e)}",
            }
            ctx.audit_log(
                "execute_shell_command",
                "error",
                {
                    "command": command,
                    "error": str(e),
                    "validation_passed": True,
                },
            )
            return result
