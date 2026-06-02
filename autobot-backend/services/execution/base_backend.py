# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Execution Backend Abstraction Layer (Issue #4343)

Base interface for pluggable execution backends supporting local, Docker, SSH, and Modal.
Provides unified API for task execution with resource limits, health checks, and result capture.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc

logger = get_logger(__name__)


class ExecutionStatus(str, Enum):
    """Execution task status enum."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class BackendType(str, Enum):
    """Supported execution backend types."""

    LOCAL = "local"
    DOCKER = "docker"
    SSH = "ssh"
    MODAL = "modal"


@dataclass
class ResourceLimits:
    """Resource constraints for task execution."""

    cpu_cores: float = 1.0
    memory_mb: int = 512
    timeout_seconds: int = 300
    disk_mb: int | None = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ExecutionResult:
    """Result of a task execution."""

    task_id: str
    status: ExecutionStatus
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    execution_time_ms: float = 0.0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    backend_type: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with serializable datetime."""
        data = asdict(self)
        if self.started_at:
            data["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            data["completed_at"] = self.completed_at.isoformat()
        return data


@dataclass
class ExecutionTask:
    """Task to be executed on a backend."""

    task_id: str
    code: str
    language: str = "python"
    env_vars: Dict[str, str] = field(default_factory=dict)
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    timeout_seconds: int | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize task."""
        if not self.task_id:
            raise ValueError("task_id is required")
        if not self.code:
            raise ValueError("code is required")
        # Use explicit timeout if provided, otherwise use resource limit
        if self.timeout_seconds is None:
            self.timeout_seconds = self.resource_limits.timeout_seconds


class ExecutionBackend(ABC):
    """Abstract base class for execution backends (Issue #4343)."""

    def __init__(self, backend_type: BackendType) -> None:
        """Initialize backend with type.

        Args:
            backend_type: Type of backend (LOCAL, DOCKER, SSH, MODAL)
        """
        self.backend_type = backend_type
        self._health_status = True
        self._last_health_check = now_utc()

    @abstractmethod
    async def execute(self, task: ExecutionTask) -> ExecutionResult:
        """Execute a task on this backend.

        Args:
            task: ExecutionTask with code and parameters

        Returns:
            ExecutionResult with stdout, stderr, and status

        Raises:
            RuntimeError: If backend is unhealthy or execution fails
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if backend is healthy and available.

        Returns:
            True if backend is operational, False otherwise
        """

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up resources (containers, connections, etc).

        Should be called during shutdown.
        """

    async def is_healthy(self) -> bool:
        """Check cached health status with periodic refresh.

        Returns:
            True if backend is healthy
        """
        # Refresh health check every 30 seconds
        now = now_utc()
        elapsed = (now - self._last_health_check).total_seconds()
        if elapsed > 30:
            self._health_status = await self.health_check()
            self._last_health_check = now
        return self._health_status

    async def verify_task_compatibility(self, task: ExecutionTask) -> Tuple[bool, str]:
        """Verify task can run on this backend.

        Args:
            task: Task to verify

        Returns:
            Tuple of (is_compatible, reason_if_not)
        """
        # Default: accept all tasks
        return True, ""

    def get_backend_info(self) -> Dict[str, Any]:
        """Return backend information for debugging/monitoring.

        Returns:
            Dictionary with backend details
        """
        return {
            "type": self.backend_type.value,
            "healthy": self._health_status,
            "last_health_check": self._last_health_check.isoformat(),
        }

    async def snapshot(
        self, container_id: str, session_id: str = "", user_id: str = ""
    ) -> Any:
        """Create a snapshot of an execution environment.

        Args:
            container_id: ID or name of the execution environment to snapshot.
            session_id: Optional identifier for the agent session.
            user_id: ID of the authenticated user creating the snapshot.
                When non-empty, enables ownership validation on restore/delete.

        Returns:
            Backend-specific snapshot record with snapshot_id and metadata.

        Raises:
            NotImplementedError: If this backend does not support snapshots.
            RuntimeError: If snapshot creation fails.
        """
        raise NotImplementedError(
            f"{self.backend_type.value} backend does not support snapshots"
        )

    async def restore(self, snapshot_id: str, caller_user_id: str) -> str:
        """Restore an execution environment from a snapshot.

        Args:
            snapshot_id: ID returned by a prior snapshot() call.
            caller_user_id: ID of the user requesting restore.
                Must match the snapshot's user_id when ownership validation is enabled.

        Returns:
            ID of the restored execution environment.

        Raises:
            NotImplementedError: If this backend does not support snapshots.
            KeyError: If snapshot_id is not found.
            PermissionError: If caller_user_id does not own the snapshot.
            RuntimeError: If restore fails.
        """
        raise NotImplementedError(
            f"{self.backend_type.value} backend does not support snapshots"
        )

    async def delete_snapshot(self, snapshot_id: str, caller_user_id: str) -> bool:
        """Delete a snapshot and its associated resources.

        Args:
            snapshot_id: ID returned by a prior snapshot() call.
            caller_user_id: ID of the user requesting deletion.
                Must match the snapshot's user_id when ownership validation is enabled.

        Returns:
            True if the snapshot was found and removed, False if not found.

        Raises:
            NotImplementedError: If this backend does not support snapshots.
            PermissionError: If caller_user_id does not own the snapshot.
        """
        raise NotImplementedError(
            f"{self.backend_type.value} backend does not support snapshots"
        )

    async def get_snapshots_for_session(self, session_id: str) -> list:
        """List all snapshots for a given session.

        Args:
            session_id: Session identifier to query snapshots for.

        Returns:
            List of backend-specific snapshot records for the session.
            Returns empty list if no snapshots found.

        Raises:
            NotImplementedError: If this backend does not support snapshots.
        """
        raise NotImplementedError(
            f"{self.backend_type.value} backend does not support snapshots"
        )
