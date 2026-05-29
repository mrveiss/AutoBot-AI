# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Docker Execution Backend (Issue #4343)

Executes tasks in isolated Docker containers with resource limits.
Provides CPU, memory, and timeout constraints.

GH#4452: Optional pre-warmed container pool for near-zero cold-start latency.
Enable it by passing ``use_pool=True`` (and optionally ``pool_size``) to the
constructor. The pool runs ``sleep infinity`` containers per image and uses
``exec_run`` instead of ``containers.run`` so callers skip image-layer spin-up.
"""

import asyncio
import os
from typing import Any, Dict, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc

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
from services.execution.container_pool import ContainerPoolRegistry

logger = get_logger(__name__)

_DEFAULT_POOL_SIZE = 3


class DockerBackend(ExecutionBackend):
    """Execute tasks in Docker containers (Issue #4343).

    When *use_pool* is ``True`` a :class:`ContainerPoolRegistry` keeps
    pre-started containers warm per image (GH#4452).  Each acquired container
    receives commands via ``exec_run``; after execution the container is
    destroyed and the pool is refilled asynchronously.
    """

    def __init__(
        self,
        docker_host: str | None = None,
        use_pool: bool | None = None,
        pool_size: int | None = None,
    ) -> None:
        """Initialize Docker backend.

        Args:
            docker_host: Docker daemon URL (default: unix socket)
            use_pool: Enable pre-warmed container pool (GH#4452).
                Overrides AUTOBOT_DOCKER_USE_POOL env var if provided.
            pool_size: Number of warm containers to maintain per image.
                Overrides AUTOBOT_DOCKER_POOL_SIZE env var if provided.

        Raises:
            RuntimeError: If Docker is not available or not configured
        """
        super().__init__(BackendType.DOCKER)
        if docker is None:
            raise RuntimeError("docker package not installed. " "Install with: pip install docker")

        try:
            self.client = docker.from_env(timeout=10)
            # Verify connection
            self.client.ping()
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Docker daemon: {e}")

        self._container_map: Dict[str, str] = {}  # task_id -> container_id
        self._default_image = "python:3.10-slim"

        # Pre-warmed pool (GH#4452)
        # Read from env vars if not explicitly provided
        if use_pool is None:
            use_pool = os.getenv("AUTOBOT_DOCKER_USE_POOL", "false").lower() == "true"
        if pool_size is None:
            try:
                pool_size = int(os.getenv("AUTOBOT_DOCKER_POOL_SIZE", str(_DEFAULT_POOL_SIZE)))
            except ValueError:
                logger.warning(
                    "Invalid AUTOBOT_DOCKER_POOL_SIZE env var, using default %d", _DEFAULT_POOL_SIZE
                )
                pool_size = _DEFAULT_POOL_SIZE

        self._use_pool = use_pool
        self._pool_size = pool_size
        self._pool_registry: ContainerPoolRegistry | None = None
        if use_pool:
            self._pool_registry = ContainerPoolRegistry(
                docker_client=self.client,
                pool_size=pool_size,
            )
            logger.info("Docker pool enabled with size %d (GH#4452)", pool_size)

    # ------------------------------------------------------------------
    # Pool lifecycle helpers
    # ------------------------------------------------------------------

    async def warm_pool(self, images: list[str] | None = None) -> None:
        """Pre-warm the container pool for the given images.

        Args:
            images: Docker images to pre-warm. Defaults to all supported images.
        """
        if self._pool_registry is None:
            return
        if images is None:
            images = list(self._get_image_map().values())
        await self._pool_registry.start(images)

    def get_pool_stats(self) -> Dict[str, Any]:
        """Return pool statistics for monitoring."""
        if self._pool_registry is None:
            return {}
        return self._pool_registry.get_stats()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(self, task: ExecutionTask) -> ExecutionResult:
        """Execute task in Docker container.

        Uses a warm container from the pool when *use_pool* is ``True``
        (GH#4452); otherwise falls back to the original cold-start path.

        Args:
            task: ExecutionTask with code and parameters

        Returns:
            ExecutionResult with captured output

        Raises:
            RuntimeError: If container creation or execution fails
        """
        if not await self.is_healthy():
            raise RuntimeError("Docker backend is not healthy")

        image = self._get_image_for_language(task.language)

        if self._use_pool and self._pool_registry is not None:
            pool = self._pool_registry.get_pool(image)
            if pool is not None:
                return await self._execute_pooled(task, image, pool)

        return await self._execute_cold(task, image)

    async def _execute_pooled(self, task: ExecutionTask, image: str, pool: Any) -> ExecutionResult:
        """Execute *task* using a pre-warmed container from *pool* (GH#4452).

        Acquires a warm container, runs the command with ``exec_run`` inside
        it, then releases (destroys) the container so the pool can refill.

        Args:
            task: ExecutionTask with code and parameters.
            image: Docker image name (used for logging).
            pool: WarmContainerPool to acquire from.

        Returns:
            ExecutionResult with captured output.
        """
        result = ExecutionResult(
            task_id=task.task_id,
            status=ExecutionStatus.PENDING,
            backend_type=self.backend_type.value,
        )

        container = None
        try:
            result.started_at = now_utc()
            result.status = ExecutionStatus.RUNNING

            container = await pool.acquire()
            self._container_map[task.task_id] = container.id

            cmd = self._prepare_command(task)
            env = {k: str(v) for k, v in (task.env_vars or {}).items()}

            exec_result = await asyncio.to_thread(
                container.exec_run,
                cmd,
                environment=env,
                demux=False,
            )

            output = (exec_result.output or b"").decode("utf-8", errors="replace")
            result.stdout = output
            result.stderr = ""
            result.return_code = exec_result.exit_code if exec_result.exit_code is not None else -1
            result.status = ExecutionStatus.SUCCESS if result.return_code == 0 else ExecutionStatus.FAILED

        except Exception as exc:
            logger.exception("Pooled execution error for task %s: %s", task.task_id, exc)
            result.status = ExecutionStatus.FAILED
            result.stderr = str(exc)
            result.return_code = -1

        finally:
            if container is not None:
                self._container_map.pop(task.task_id, None)
                await pool.release(container)

            result.completed_at = now_utc()
            if result.started_at:
                result.execution_time_ms = (result.completed_at - result.started_at).total_seconds() * 1000

        return result

    async def _execute_cold(self, task: ExecutionTask, image: str) -> ExecutionResult:
        """Original cold-start execution path: create a new container per task.

        Args:
            task: ExecutionTask with code and parameters.
            image: Docker image to use.

        Returns:
            ExecutionResult with captured output.
        """
        result = ExecutionResult(
            task_id=task.task_id,
            status=ExecutionStatus.PENDING,
            backend_type=self.backend_type.value,
        )

        container = None

        try:
            result.started_at = now_utc()
            result.status = ExecutionStatus.RUNNING

            cmd = self._prepare_command(task)

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

                try:
                    exit_code = container.wait(timeout=task.timeout_seconds)
                    result.return_code = exit_code["StatusCode"]

                except Exception as timeout_error:
                    logger.warning("Container %s timed out: %s", container.id, timeout_error)
                    container.kill()
                    result.status = ExecutionStatus.TIMEOUT
                    result.stderr = f"Container execution exceeded timeout of {task.timeout_seconds}s"
                    result.return_code = -1
                    return result

                try:
                    logs = container.logs(stdout=True, stderr=True)
                    output = logs.decode(encoding="utf-8", errors="replace")
                    result.stdout = output
                    result.stderr = ""
                except Exception as e:
                    logger.warning("Failed to capture container logs: %s", e)
                    result.stderr = f"Failed to capture logs: {str(e)}"

                result.status = ExecutionStatus.SUCCESS if result.return_code == 0 else ExecutionStatus.FAILED

            except Exception as e:
                result.status = ExecutionStatus.FAILED
                result.stderr = f"Container execution failed: {str(e)}"
                result.return_code = -1
                logger.exception("Error executing task %s: %s", task.task_id, e)

        finally:
            if container:
                try:
                    container.remove(force=True)
                    self._container_map.pop(task.task_id, None)
                except Exception as e:
                    logger.warning("Error removing container %s: %s", container.id, e)

            result.completed_at = now_utc()
            if result.started_at:
                result.execution_time_ms = (result.completed_at - result.started_at).total_seconds() * 1000

        return result

    # ------------------------------------------------------------------
    # Health / cleanup
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Check if Docker daemon is accessible.

        Returns:
            True if Docker is accessible
        """
        try:
            self.client.ping()
            return True
        except Exception as e:
            logger.warning("Docker health check failed: %s", e)
            return False

    async def cleanup(self) -> None:
        """Clean up active containers and stop the pool if running."""
        for task_id, container_id in list(self._container_map.items()):
            try:
                container = self.client.containers.get(container_id)
                if container.status == "running":
                    container.kill()
                container.remove(force=True)
            except Exception as e:
                logger.warning("Error cleaning up container %s: %s", container_id, e)

        if self._pool_registry is not None:
            await self._pool_registry.stop()

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
                f"Language '{task.language}' not supported in Docker. " f"Supported: {', '.join(supported_languages)}",
            )

        try:
            image = self._get_image_for_language(task.language)
            self.client.images.get(image)
        except Exception:
            pass

        return True, ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_image_map(self) -> Dict[str, str]:
        """Return the language-to-image mapping."""
        return {
            "python": "python:3.10-slim",
            "javascript": "node:18-slim",
            "bash": "bash:5.1",
            "shell": "bash:5.1",
        }

    def _get_image_for_language(self, language: str) -> str:
        """Get Docker image for language.

        Args:
            language: Programming language

        Returns:
            Docker image name
        """
        return self._get_image_map().get(language.lower(), self._default_image)

    def _prepare_command(self, task: ExecutionTask) -> list:
        """Prepare command for container execution.

        Args:
            task: ExecutionTask with code

        Returns:
            Command list for container.run() or exec_run()
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
