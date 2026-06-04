# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Execution Manager (Issue #4343)

Routes tasks to appropriate backends based on characteristics.
Handles health checks, resource management, and routing decisions.
"""

from typing import Dict, List

from autobot_shared.logging_manager import get_logger
from services.execution.base_backend import (
    BackendType,
    ExecutionBackend,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTask,
)

logger = get_logger(__name__)


class ExecutionManager:
    """Manages multiple execution backends with intelligent routing (Issue #4343)."""

    def __init__(self) -> None:
        """Initialize execution manager with available backends."""
        self.backends: Dict[BackendType, ExecutionBackend] = {}
        self._enabled_backends: set = set()
        self._routing_policy = "first_available"

    def register_backend(self, backend_type: BackendType, backend: ExecutionBackend) -> None:
        """Register an execution backend.

        Args:
            backend_type: Type of backend
            backend: ExecutionBackend instance
        """
        self.backends[backend_type] = backend
        self._enabled_backends.add(backend_type)
        logger.info(f"Registered {backend_type.value} backend")

    def enable_backend(self, backend_type: BackendType) -> None:
        """Enable a backend for task routing.

        Args:
            backend_type: Type of backend to enable
        """
        if backend_type in self.backends:
            self._enabled_backends.add(backend_type)
            logger.info(f"Enabled {backend_type.value} backend")

    def disable_backend(self, backend_type: BackendType) -> None:
        """Disable a backend from task routing.

        Args:
            backend_type: Type of backend to disable
        """
        self._enabled_backends.discard(backend_type)
        logger.info(f"Disabled {backend_type.value} backend")

    async def execute(
        self,
        task: ExecutionTask,
        preferred_backend: BackendType | None = None,
    ) -> ExecutionResult:
        """Execute task on most suitable backend.

        Args:
            task: ExecutionTask to execute
            preferred_backend: Preferred backend type (will be tried first)

        Returns:
            ExecutionResult with output and status

        Raises:
            RuntimeError: If no suitable backend is available
        """
        # Get backends in order of preference
        backends_to_try = self._get_backend_order(task, preferred_backend)

        if not backends_to_try:
            raise RuntimeError(f"No suitable backends available for task {task.task_id}")

        result = None
        last_error = None

        for backend_type in backends_to_try:
            try:
                backend = self.backends[backend_type]

                # Check health
                if not await backend.is_healthy():
                    logger.warning(f"{backend_type.value} backend is unhealthy, skipping")
                    continue

                # Check compatibility
                is_compatible, reason = await backend.verify_task_compatibility(task)
                if not is_compatible:
                    logger.info(f"Task incompatible with {backend_type.value}: {reason}")
                    continue

                # Execute
                logger.info(f"Executing task {task.task_id} on {backend_type.value}")
                result = await backend.execute(task)
                return result

            except Exception as e:
                last_error = e
                logger.warning(f"Error executing on {backend_type.value}: {e}, trying next backend")
                continue

        # All backends failed
        if result is None:
            error_msg = f"All backends failed for task {task.task_id}. " f"Last error: {str(last_error)}"
            logger.error(error_msg)

            result = ExecutionResult(
                task_id=task.task_id,
                status=ExecutionStatus.FAILED,
                stderr=error_msg,
                return_code=-1,
            )

        return result

    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all backends.

        Returns:
            Dictionary mapping backend names to health status
        """
        health_status = {}

        for backend_type, backend in self.backends.items():
            try:
                is_healthy = await backend.health_check()
                health_status[backend_type.value] = is_healthy
                status_str = "healthy" if is_healthy else "unhealthy"
                logger.info(f"{backend_type.value} backend is {status_str}")
            except Exception as e:
                logger.error(f"Error checking {backend_type.value} health: {e}")
                health_status[backend_type.value] = False

        return health_status

    async def cleanup_all(self) -> None:
        """Clean up all backends.

        Should be called during shutdown.
        """
        for backend_type, backend in self.backends.items():
            try:
                await backend.cleanup()
                logger.info(f"Cleaned up {backend_type.value} backend")
            except Exception as e:
                logger.warning(f"Error cleaning up {backend_type.value}: {e}")

    def get_backend_info(self) -> Dict[str, any]:
        """Get information about all registered backends.

        Returns:
            Dictionary with backend details
        """
        return {
            backend_type.value: {
                **backend.get_backend_info(),
                "enabled": backend_type in self._enabled_backends,
            }
            for backend_type, backend in self.backends.items()
        }

    def _get_backend_order(
        self,
        task: ExecutionTask,
        preferred_backend: BackendType | None = None,
    ) -> List[BackendType]:
        """Determine order of backends to try.

        Args:
            task: ExecutionTask with characteristics
            preferred_backend: Preferred backend type

        Returns:
            List of BackendType in priority order
        """
        enabled = [bt for bt in self._enabled_backends if bt in self.backends]

        if not enabled:
            return []

        # If preferred backend is enabled, put it first
        if preferred_backend and preferred_backend in enabled:
            candidates = [preferred_backend] + [b for b in enabled if b != preferred_backend]
        else:
            candidates = enabled

        # Sort by routing policy
        if self._routing_policy == "smart":
            candidates = self._smart_route(task, candidates)

        return candidates

    def _smart_route(self, task: ExecutionTask, candidates: List[BackendType]) -> List[BackendType]:
        """Intelligent routing based on task characteristics.

        Args:
            task: ExecutionTask to route
            candidates: Available backend types

        Returns:
            Sorted list of backends by suitability

        Note:
            Routes long-running tasks to Modal, compute-heavy to Docker,
            default to local.
        """
        # For now, simple heuristic based on task metadata
        timeout = task.resource_limits.timeout_seconds

        # Long-running (>300s) → Modal
        # Heavy compute (>2 cores) → Docker
        # Default → Local

        if timeout > 300 and BackendType.MODAL in candidates:
            # Put Modal first for long-running
            return [BackendType.MODAL] + [b for b in candidates if b != BackendType.MODAL]
        elif task.resource_limits.cpu_cores > 2 and BackendType.DOCKER in candidates:
            # Put Docker first for heavy compute
            return [BackendType.DOCKER] + [b for b in candidates if b != BackendType.DOCKER]
        else:
            # Default order
            return candidates

    def set_routing_policy(self, policy: str) -> None:
        """Set task routing policy.

        Args:
            policy: "first_available" or "smart"
        """
        if policy in ("first_available", "smart"):
            self._routing_policy = policy
        else:
            raise ValueError(f"Unknown routing policy: {policy}")


# Global singleton instance
_execution_manager: ExecutionManager | None = None


def get_execution_manager() -> ExecutionManager:
    """Get or create global execution manager.

    Returns:
        ExecutionManager singleton
    """
    global _execution_manager
    if _execution_manager is None:
        _execution_manager = ExecutionManager()
    return _execution_manager
