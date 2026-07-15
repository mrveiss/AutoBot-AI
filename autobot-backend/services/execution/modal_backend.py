# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Modal Serverless Execution Backend (Issue #4343)

Executes tasks inside real Modal Sandbox isolated containers.
Supports cost tracking and automatic scaling.
"""

import asyncio
import os
from typing import Any, Dict, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc

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
    """Execute tasks inside Modal Sandbox isolated containers (Issue #4343).

    Each call to ``execute()`` spins up a fresh ``modal.Sandbox``, runs the
    task code with ``sandbox.exec("python", "-c", task.code)``, captures
    stdout/stderr, and terminates the sandbox in a ``finally`` block.

    Modal SDK calls are blocking; they are offloaded to a thread via
    ``asyncio.to_thread`` so the event loop is never blocked.
    """

    _APP_NAME = "autobot-code-execution"

    def __init__(self, api_token: str | None = None) -> None:
        """Initialize Modal backend.

        Args:
            api_token: Modal API token (default: read from MODAL_TOKEN_ID env var).

        Raises:
            RuntimeError: If the Modal SDK is not installed.
        """
        super().__init__(BackendType.MODAL)

        if modal is None:
            raise RuntimeError("modal package not installed. Install with: pip install modal")

        self.api_token = api_token
        self._function_cache: Dict[str, Any] = {}
        self._cost_estimate = 0.0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def execute(self, task: ExecutionTask) -> ExecutionResult:
        """Execute task inside a Modal Sandbox isolated container.

        Args:
            task: ExecutionTask with code and parameters.

        Returns:
            ExecutionResult with execution details.

        Raises:
            RuntimeError: If Modal backend is unhealthy or execution fails.
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

            output = await self._call_modal_function(task)

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
            logger.exception("Error executing task %s on Modal: %s", task.task_id, e)

        finally:
            result.completed_at = now_utc()
            if result.started_at:
                result.execution_time_ms = (result.completed_at - result.started_at).total_seconds() * 1000

        return result

    async def health_check(self) -> bool:
        """Return True when Modal is installed and credentials appear configured.

        Does NOT make a network call — checks only that the SDK is present and
        that at least one of the known token env vars is set (or ``api_token``
        was supplied at construction).  A real connectivity check happens lazily
        when ``execute()`` is first called.

        Returns:
            True if Modal can plausibly be reached.
        """
        if modal is None:
            return False
        if self.api_token:
            return True
        return bool(os.environ.get("MODAL_TOKEN_ID") or os.environ.get("MODAL_TOKEN_SECRET"))

    async def cleanup(self) -> None:
        """Clean up cached Modal resources."""
        self._function_cache.clear()

    async def verify_task_compatibility(self, task: ExecutionTask) -> Tuple[bool, str]:
        """Verify task can run on Modal (Python only).

        Args:
            task: Task to check.

        Returns:
            Tuple of (is_compatible, reason_if_not).
        """
        if task.language.lower() != "python":
            return False, f"Modal only supports Python. Got: {task.language}"
        return True, ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_app(self) -> Any:
        """Return a cached ``modal.App``, looking it up (or creating) on first call.

        Returns:
            A ``modal.App`` instance for ``_APP_NAME``.
        """
        if "app" not in self._function_cache:
            self._function_cache["app"] = modal.App.lookup(self._APP_NAME, create_if_missing=True)
        return self._function_cache["app"]

    def _run_in_sandbox(self, task: ExecutionTask) -> Dict[str, Any]:
        """Run ``task.code`` inside a real Modal Sandbox (blocking).

        This method is intentionally synchronous so it can be offloaded to a
        thread by ``_call_modal_function``.  It NEVER falls back to in-process
        ``exec``; if Modal is unavailable a ``RuntimeError`` propagates.

        Args:
            task: ExecutionTask with code, env_vars, and timeout.

        Returns:
            Dictionary with ``stdout``, ``stderr``, ``return_code``, ``run_id``,
            and ``cost`` keys.
        """
        if modal is None:
            raise RuntimeError("Modal SDK is not available; cannot execute task")

        sanitized_env = {k: v for k, v in safe_task_env({}, task.env_vars).items() if isinstance(v, str)}
        app = self._get_or_create_app()
        image = modal.Image.debian_slim(python_version="3.12")
        secrets = [modal.Secret.from_dict(sanitized_env)] if sanitized_env else []
        sandbox = modal.Sandbox.create(
            app=app,
            image=image,
            timeout=task.timeout_seconds or 300,
            secrets=secrets,
        )
        try:
            proc = sandbox.exec("python", "-c", task.code)
            stdout = proc.stdout.read()
            stderr = proc.stderr.read()
            proc.wait()
            rc = proc.returncode if proc.returncode is not None else 0
            run_id = getattr(sandbox, "object_id", "") or f"modal-{task.task_id}"
            return {"stdout": stdout, "stderr": stderr, "return_code": rc, "run_id": run_id, "cost": 0.0}
        finally:
            try:
                sandbox.terminate()
            except Exception:
                pass

    async def _call_modal_function(self, task: ExecutionTask) -> Dict[str, Any]:
        """Offload the blocking Modal Sandbox call to a thread.

        Args:
            task: ExecutionTask.

        Returns:
            Dictionary with ``stdout``, ``stderr``, ``return_code``, ``run_id``,
            and ``cost`` keys.

        Raises:
            RuntimeError: If Modal SDK is not available.
        """
        if modal is None:
            raise RuntimeError("Modal SDK is not available; cannot execute task")
        return await asyncio.to_thread(self._run_in_sandbox, task)
