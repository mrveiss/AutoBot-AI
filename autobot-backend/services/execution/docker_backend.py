# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Docker Execution Backend (Issue #4343)

Executes tasks in isolated Docker containers with resource limits.
Provides CPU, memory, and timeout constraints.
"""

import asyncio
import json
import logging
from datetime import datetime
from autobot_shared.time_utils import now_utc
from typing import Any, Dict, Optional, Tuple

try:
    import docker
    from docker.errors import DockerException
except ImportError:
    docker = None
    DockerException = Exception

from services.execution.base_backend import (
    BackendType,
    ExecutionBackend,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTask,
)

logger = logging.getLogger(__name__)


class DockerBackend(ExecutionBackend):
    """Execute tasks in Docker containers (Issue #4343)."""

    def __init__(self, docker_host: Optional[str] = None):
        """Initialize Docker backend.

        Args:
            docker_host: Docker daemon URL (default: unix socket)

        Raises:
            RuntimeError: If Docker is not available or not configured
        """
        super().__init__(BackendType.DOCKER)
        if docker is None:
            raise RuntimeError(
                "docker package not installed. "
                "Install with: pip install docker"
            )

        try:
            self.client = docker.from_env(timeout=10)
            # Verify connection
            self.client.ping()
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Docker daemon: {e}")

        self._container_map: Dict[str, str] = {}  # task_id -> container_id
        self._default_image = "python:3.10-slim"

    async def execute(self, task: ExecutionTask) -> ExecutionResult:
        """Execute task in Docker container.

        Args:
            task: ExecutionTask with code and parameters

        Returns:
            ExecutionResult with captured output

        Raises:
            RuntimeError: If container creation or execution fails
        """
        if not await self.is_healthy():
            raise RuntimeError("Docker backend is not healthy")

        result = ExecutionResult(
            task_id=task.task_id,
            status=ExecutionStatus.PENDING,
            backend_type=self.backend_type.value,
        )

        container = None

        try:
            result.started_at = now_utc()
            result.status = ExecutionStatus.RUNNING

            # Prepare image and command
            image = self._get_image_for_language(task.language)
            cmd = self._prepare_command(task)

            # Create container with resource limits
            try:
                container = self.client.containers.run(
                    image,
                    cmd,
                    detach=True,
                    mem_limit=f"{task.resource_limits.memory_mb}m",
                    cpus=task.resource_limits.cpu_cores,
                    environment=task.env_vars,
                    stdout=True,
                    stderr=True,
                    remove=False,
                )

                self._container_map[task.task_id] = container.id

                # Wait for container with timeout
                try:
                    exit_code = container.wait(timeout=task.timeout_seconds)
                    result.return_code = exit_code["StatusCode"]

                except Exception as timeout_error:
                    logger.warning(
                        f"Container {container.id} timed out: {timeout_error}"
                    )
                    container.kill()
                    result.status = ExecutionStatus.TIMEOUT
                    result.stderr = (
                        f"Container execution exceeded timeout of "
                        f"{task.timeout_seconds}s"
                    )
                    result.return_code = -1
                    return result

                # Capture output
                try:
                    logs = container.logs(stdout=True, stderr=True)
                    output = logs.decode(encoding="utf-8", errors="replace")
                    # Simple heuristic: if container has stderr, assume it's there
                    result.stdout = output
                    result.stderr = ""
                except Exception as e:
                    logger.warning(f"Failed to capture container logs: {e}")
                    result.stderr = f"Failed to capture logs: {str(e)}"

                # Determine status
                result.status = (
                    ExecutionStatus.SUCCESS
                    if result.return_code == 0
                    else ExecutionStatus.FAILED
                )

            except Exception as e:
                result.status = ExecutionStatus.FAILED
                result.stderr = f"Container execution failed: {str(e)}"
                result.return_code = -1
                logger.exception(f"Error executing task {task.task_id}: {e}")

        finally:
            # Clean up container
            if container:
                try:
                    container.remove(force=True)
                    self._container_map.pop(task.task_id, None)
                except Exception as e:
                    logger.warning(
                        f"Error removing container {container.id}: {e}"
                    )

            result.completed_at = now_utc()
            if result.started_at:
                result.execution_time_ms = (
                    result.completed_at - result.started_at
                ).total_seconds() * 1000

        return result

    async def health_check(self) -> bool:
        """Check if Docker daemon is accessible.

        Returns:
            True if Docker is accessible
        """
        try:
            self.client.ping()
            return True
        except Exception as e:
            logger.warning(f"Docker health check failed: {e}")
            return False

    async def cleanup(self) -> None:
        """Clean up active containers."""
        for task_id, container_id in list(self._container_map.items()):
            try:
                container = self.client.containers.get(container_id)
                if container.status == "running":
                    container.kill()
                container.remove(force=True)
            except Exception as e:
                logger.warning(
                    f"Error cleaning up container {container_id}: {e}"
                )

    async def verify_task_compatibility(self, task: ExecutionTask) -> Tuple[bool, str]:
        """Verify task can run in Docker.

        Args:
            task: Task to check

        Returns:
            Tuple of (is_compatible, reason)
        """
        supported_languages = ["python", "javascript", "bash", "shell"]
        if task.language.lower() not in supported_languages:
            return (
                False,
                f"Language '{task.language}' not supported in Docker. "
                f"Supported: {', '.join(supported_languages)}",
            )

        # Check if image is available
        try:
            image = self._get_image_for_language(task.language)
            self.client.images.get(image)
        except Exception:
            # Image not available locally, but can be pulled
            pass

        return True, ""

    def _get_image_for_language(self, language: str) -> str:
        """Get Docker image for language.

        Args:
            language: Programming language

        Returns:
            Docker image name
        """
        language = language.lower()
        images = {
            "python": "python:3.10-slim",
            "javascript": "node:18-slim",
            "bash": "bash:5.1",
            "shell": "bash:5.1",
        }
        return images.get(language, self._default_image)

    def _prepare_command(self, task: ExecutionTask) -> list:
        """Prepare command for container execution.

        Args:
            task: ExecutionTask with code

        Returns:
            Command list for container.run()
        """
        language = task.language.lower()

        if language == "python":
            return ["python", "-c", task.code]
        elif language == "javascript":
            return ["node", "-e", task.code]
        elif language in ("bash", "shell"):
            return ["bash", "-c", task.code]
        else:
            return ["bash", "-c", task.code]
