# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Local Execution Backend (Issue #4343)

Executes tasks directly on the local machine using subprocess.
Supports Python, shell, and other system commands.
"""

import asyncio
import os
import sys
from typing import Dict, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from services.execution.base_backend import (
    BackendType,
    ExecutionBackend,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTask,
)

logger = get_logger(__name__)


class LocalBackend(ExecutionBackend):
    """Execute tasks locally using subprocess (Issue #4343)."""

    def __init__(self) -> None:
        """Initialize local backend."""
        super().__init__(BackendType.LOCAL)
        self._max_processes = 10
        self._active_processes: Dict[str, asyncio.subprocess.Process] = {}

    async def execute(self, task: ExecutionTask) -> ExecutionResult:
        """Execute task locally via subprocess.

        Args:
            task: ExecutionTask with code and parameters

        Returns:
            ExecutionResult with captured output

        Raises:
            RuntimeError: If execution fails or backend is unhealthy
        """
        if not await self.is_healthy():
            raise RuntimeError("Local backend is not healthy")

        result = ExecutionResult(
            task_id=task.task_id,
            status=ExecutionStatus.PENDING,
            backend_type=self.backend_type.value,
        )

        try:
            # Prepare environment
            env = os.environ.copy()
            env.update(task.env_vars)

            # Prepare command based on language
            cmd = self._prepare_command(task, env)

            result.started_at = now_utc()
            result.status = ExecutionStatus.RUNNING

            # Execute with timeout
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    cwd=None,
                )

                self._active_processes[task.task_id] = process

                try:
                    stdout_data, stderr_data = await asyncio.wait_for(
                        process.communicate(),
                        timeout=task.timeout_seconds,
                    )
                    result.stdout = stdout_data.decode(encoding="utf-8", errors="replace")
                    result.stderr = stderr_data.decode(encoding="utf-8", errors="replace")
                    result.return_code = process.returncode or 0

                    result.status = ExecutionStatus.SUCCESS if result.return_code == 0 else ExecutionStatus.FAILED

                except asyncio.TimeoutError:
                    process.kill()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        process.kill()
                    result.status = ExecutionStatus.TIMEOUT
                    result.stderr = f"Task exceeded timeout of {task.timeout_seconds}s"
                    result.return_code = -1

                finally:
                    self._active_processes.pop(task.task_id, None)

            except Exception as e:
                result.status = ExecutionStatus.FAILED
                result.stderr = f"Execution error: {str(e)}"
                result.return_code = -1
                logger.exception(f"Error executing task {task.task_id}: {e}")

        finally:
            result.completed_at = now_utc()
            if result.started_at:
                result.execution_time_ms = (result.completed_at - result.started_at).total_seconds() * 1000

        return result

    async def health_check(self) -> bool:
        """Check if local backend is healthy.

        Returns:
            True if system can execute processes
        """
        try:
            # Simple check: can we execute a basic command?
            process = await asyncio.create_subprocess_exec(
                "true",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(process.wait(), timeout=5)
            return True
        except Exception as e:
            logger.warning(f"Local backend health check failed: {e}")
            return False

    async def cleanup(self) -> None:
        """Clean up active processes."""
        for task_id, process in list(self._active_processes.items()):
            if process and not process.returncode:
                try:
                    process.kill()
                    await asyncio.wait_for(process.wait(), timeout=5)
                except Exception as e:
                    logger.warning(f"Error killing process {task_id}: {e}")

    async def verify_task_compatibility(self, task: ExecutionTask) -> Tuple[bool, str]:
        """Verify task can run locally.

        Args:
            task: Task to check

        Returns:
            Tuple of (is_compatible, reason)
        """
        # Check supported languages
        supported_languages = ["python", "shell", "bash", "sh"]
        if task.language.lower() not in supported_languages:
            return (
                False,
                f"Language '{task.language}' not supported locally. " f"Supported: {', '.join(supported_languages)}",
            )

        # Check active process limit
        if len(self._active_processes) >= self._max_processes:
            return False, f"Reached max concurrent processes ({self._max_processes})"

        return True, ""

    def _prepare_command(self, task: ExecutionTask, env: Dict[str, str]) -> list:
        """Prepare command based on task language.

        Args:
            task: ExecutionTask with code
            env: Environment variables

        Returns:
            Command list for subprocess.exec
        """
        language = task.language.lower()

        if language == "python":
            return [sys.executable, "-c", task.code]
        elif language in ("shell", "bash", "sh"):
            return ["/bin/bash", "-c", task.code]
        else:
            # Fallback to shell
            return ["/bin/bash", "-c", task.code]
