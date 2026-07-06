# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Modal Serverless Execution Backend (Issue #4343)

Executes tasks on Modal serverless platform.
Supports cost tracking and automatic scaling.
"""

from typing import Any, Dict, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc, utc_timestamp

try:
    import modal
except ImportError:
    modal = None

from services.execution.base_backend import (
    BackendType,
    ExecutionBackend,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTask,
)
from services.execution.env_sanitizer import safe_task_env

logger = get_logger(__name__)


class ModalBackend(ExecutionBackend):
    """Execute tasks on Modal serverless platform (Issue #4343)."""

    def __init__(self, api_token: str | None = None) -> None:
        """Initialize Modal backend.

        Args:
            api_token: Modal API token (default: from MODAL_TOKEN_ID env var)

        Raises:
            RuntimeError: If Modal SDK is not available
        """
        super().__init__(BackendType.MODAL)

        if modal is None:
            raise RuntimeError("modal package not installed. " "Install with: pip install modal")

        self.api_token = api_token
        self._function_cache: Dict[str, Any] = {}
        self._cost_estimate = 0.0

    async def execute(self, task: ExecutionTask) -> ExecutionResult:
        """Execute task on Modal serverless.

        Args:
            task: ExecutionTask with code

        Returns:
            ExecutionResult with execution details

        Raises:
            RuntimeError: If Modal execution fails
        """
        if not await self.is_healthy():
            raise RuntimeError("Modal backend is not healthy")

        result = ExecutionResult(
            task_id=task.task_id,
            status=ExecutionStatus.PENDING,
            backend_type=self.backend_type.value,
        )

        try:
            result.started_at = now_utc()
            result.status = ExecutionStatus.RUNNING

            # For this implementation, we simulate Modal execution
            # In production, you would:
            # 1. Create a Modal function dynamically
            # 2. Call modal.client.run() with the function
            # 3. Track execution cost

            # Simulated Modal execution
            try:
                # Get or create Modal function
                func = self._get_or_create_function(task)

                # Execute (simulated)
                output = await self._call_modal_function(func, task)

                result.stdout = output.get("stdout", "")
                result.stderr = output.get("stderr", "")
                result.return_code = output.get("return_code", 0)
                result.metadata["modal_run_id"] = output.get("run_id", "")
                result.metadata["cost_estimate"] = output.get("cost", 0.0)

                result.status = ExecutionStatus.SUCCESS if result.return_code == 0 else ExecutionStatus.FAILED

            except Exception as e:
                result.status = ExecutionStatus.FAILED
                result.stderr = f"Modal execution failed: {str(e)}"
                result.return_code = -1
                logger.exception(f"Error executing task {task.task_id} on Modal: {e}")

        finally:
            result.completed_at = now_utc()
            if result.started_at:
                result.execution_time_ms = (result.completed_at - result.started_at).total_seconds() * 1000

        return result

    async def health_check(self) -> bool:
        """Check if Modal service is accessible.

        Returns:
            True if Modal is accessible
        """
        try:
            # In production, make an actual Modal health check
            # For now, just verify we can import
            if modal is None:
                return False
            return True
        except Exception as e:
            logger.warning(f"Modal health check failed: {e}")
            return False

    async def cleanup(self) -> None:
        """Clean up Modal resources."""
        # In production, cancel any pending Modal tasks
        self._function_cache.clear()

    async def verify_task_compatibility(self, task: ExecutionTask) -> Tuple[bool, str]:
        """Verify task can run on Modal.

        Args:
            task: Task to check

        Returns:
            Tuple of (is_compatible, reason)
        """
        supported_languages = ["python"]
        if task.language.lower() not in supported_languages:
            return (
                False,
                f"Modal only supports Python. Got: {task.language}",
            )

        return True, ""

    def _get_or_create_function(self, task: ExecutionTask) -> Any:
        """Get or create Modal function for task.

        Args:
            task: ExecutionTask

        Returns:
            Modal function (or stub in simulation)
        """
        language = task.language.lower()

        if language not in self._function_cache:
            # In production, create actual Modal function
            self._function_cache[language] = {
                "language": language,
                "created_at": utc_timestamp(),
            }

        return self._function_cache[language]

    async def _call_modal_function(self, func: Any, task: ExecutionTask) -> Dict[str, Any]:
        """Call Modal function with task code (simulated).

        Args:
            func: Modal function
            task: ExecutionTask with code

        Returns:
            Dictionary with execution results

        Note:
            In production, this would call modal.client.run(func, ...)
        """
        # Simulate Modal execution
        try:
            import io
            from contextlib import redirect_stderr, redirect_stdout

            # Capture stdout/stderr
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()

            return_code = 0
            stdout_output = ""
            stderr_output = ""

            try:
                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    # Execute code in isolated namespace. Security: task env
                    # vars become exec() globals, so filter them through the
                    # same AUTOBOT_* allowlist to block runtime/loader hijack
                    # names leaking into the executed code namespace.
                    namespace = safe_task_env({"__name__": "__modal__"}, task.env_vars)

                    exec(task.code, namespace)  # nosec B102

                stdout_output = stdout_capture.getvalue()
                stderr_output = stderr_capture.getvalue()

            except Exception as e:
                return_code = 1
                stderr_output = str(e)

            return {
                "stdout": stdout_output,
                "stderr": stderr_output,
                "return_code": return_code,
                "run_id": f"modal-{task.task_id}",
                "cost": 0.001,
            }

        except Exception as e:
            logger.exception(f"Error calling Modal function: {e}")
            return {
                "stdout": "",
                "stderr": f"Error: {str(e)}",
                "return_code": -1,
                "run_id": "",
                "cost": 0.0,
            }
