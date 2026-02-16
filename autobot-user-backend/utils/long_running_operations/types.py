# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Long-Running Operations Types

Issue #381: Extracted from long_running_operations_framework.py god class refactoring.
Contains enums and dataclasses for long-running operations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from backend.constants.threshold_constants import TimingConstants


class OperationType(Enum):
    """Types of long-running operations"""

    # Code Analysis Operations
    CODEBASE_INDEXING = "codebase_indexing"
    CODE_ANALYSIS = "code_analysis"
    DEPENDENCY_ANALYSIS = "dependency_analysis"
    SECURITY_SCAN = "security_scan"
    PERFORMANCE_PROFILING = "performance_profiling"

    # Testing Operations
    COMPREHENSIVE_TEST_SUITE = "comprehensive_test_suite"
    INTEGRATION_TESTING = "integration_testing"
    PERFORMANCE_TESTING = "performance_testing"
    LOAD_TESTING = "load_testing"

    # Knowledge Base Operations
    KB_POPULATION = "kb_population"
    KB_OPTIMIZATION = "kb_optimization"
    VECTOR_INDEXING = "vector_indexing"
    SEMANTIC_ANALYSIS = "semantic_analysis"

    # System Operations
    BACKUP_OPERATION = "backup_operation"
    MIGRATION_OPERATION = "migration_operation"
    CLEANUP_OPERATION = "cleanup_operation"
    MONITORING_COLLECTION = "monitoring_collection"


class OperationStatus(Enum):
    """Operation execution status"""

    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    CHECKPOINT_SAVED = "checkpoint_saved"
    RESUMING = "resuming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class OperationPriority(Enum):
    """Operation priority levels"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class OperationCheckpoint:
    """Checkpoint data for operation resume"""

    checkpoint_id: str
    operation_id: str
    checkpoint_time: datetime
    progress_percent: float
    state_data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OperationProgress:
    """Real-time progress tracking for operations"""

    operation_id: str
    current_step: str
    progress_percent: float
    estimated_remaining: float  # seconds
    items_processed: int
    total_items: int
    last_update: datetime = field(default_factory=datetime.now)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LongRunningOperation:
    """Comprehensive long-running operation definition"""

    operation_id: str
    operation_type: OperationType
    name: str
    description: str
    priority: OperationPriority = OperationPriority.NORMAL
    status: OperationStatus = OperationStatus.QUEUED
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: OperationProgress = None
    checkpoints: List[OperationCheckpoint] = field(default_factory=list)
    result: Any = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    _operation_function: Optional[Callable] = field(default=None, repr=False)

    def __post_init__(self):
        """Initialize progress tracking if not provided."""
        if self.progress is None:
            self.progress = OperationProgress(
                operation_id=self.operation_id,
                current_step="Initializing",
                progress_percent=0.0,
                estimated_remaining=0.0,
                items_processed=0,
                total_items=0,
            )

    def to_response_dict(self) -> Dict[str, Any]:
        """Convert operation to API response dictionary."""
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type.value,
            "name": self.name,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "progress": {
                "current_step": self.progress.current_step,
                "progress_percent": self.progress.progress_percent,
                "estimated_remaining": self.progress.estimated_remaining,
                "items_processed": self.progress.items_processed,
                "total_items": self.progress.total_items,
                "details": self.progress.details,
            },
            "checkpoints_count": len(self.checkpoints),
            "error_message": self.error_message,
            "metadata": self.metadata,
        }

    def start_execution(self) -> None:
        """Mark operation as started."""
        self.started_at = datetime.now()
        self.status = OperationStatus.RUNNING

    def mark_completed(self, result: Any = None) -> None:
        """Mark operation as completed."""
        self.completed_at = datetime.now()
        self.status = OperationStatus.COMPLETED
        self.result = result

    def mark_timeout(self, timeout_seconds: float) -> None:
        """Mark operation as timed out."""
        self.status = OperationStatus.TIMEOUT
        self.error_message = f"Operation timed out after {timeout_seconds} seconds"

    def mark_failed(self, error_message: str) -> None:
        """Mark operation as failed."""
        self.status = OperationStatus.FAILED
        self.error_message = error_message

    def mark_cancelled(self, reason: str = "User cancelled") -> None:
        """Mark operation as cancelled."""
        self.status = OperationStatus.CANCELLED
        self.error_message = reason

    def get_timeout_seconds(self) -> float:
        """Get timeout for this operation type."""
        return LongRunningTimeoutConfig.get_timeout_config(self.operation_type)[
            "timeout_seconds"
        ]

    def get_checkpoint_interval(self) -> float:
        """Get checkpoint interval for this operation type."""
        return LongRunningTimeoutConfig.get_timeout_config(self.operation_type)[
            "checkpoint_interval"
        ]

    def get_progress_interval(self) -> float:
        """Get progress report interval for this operation type."""
        return LongRunningTimeoutConfig.get_timeout_config(self.operation_type)[
            "progress_interval"
        ]

    def get_operation_function(self) -> Optional[Callable]:
        """Get the operation function if set."""
        return self._operation_function


class LongRunningTimeoutConfig:
    """
    Centralized timeout configuration for different operation types.

    Maps operation types to intelligent timeout profiles considering:
    - Typical execution duration
    - Checkpoint/resume support
    - Progress reporting intervals
    - Graceful failure handling
    """

    # Timeout profiles (in seconds unless noted)
    TIMEOUT_PROFILES: Dict[OperationType, Dict[str, float]] = {
        # Code Analysis - can run for hours on large codebases
        OperationType.CODEBASE_INDEXING: {
            "timeout_seconds": 14400,  # 4 hours
            "checkpoint_interval": 300,  # Every 5 minutes
            "progress_interval": 30,  # Report every 30 seconds
        },
        OperationType.CODE_ANALYSIS: {
            "timeout_seconds": 7200,  # 2 hours
            "checkpoint_interval": 180,  # Every 3 minutes
            "progress_interval": 20,
        },
        OperationType.DEPENDENCY_ANALYSIS: {
            "timeout_seconds": 3600,  # 1 hour
            "checkpoint_interval": 120,
            "progress_interval": 15,
        },
        OperationType.SECURITY_SCAN: {
            "timeout_seconds": 7200,  # 2 hours - thorough scans take time
            "checkpoint_interval": 180,
            "progress_interval": 30,
        },
        OperationType.PERFORMANCE_PROFILING: {
            "timeout_seconds": 3600,
            "checkpoint_interval": 120,
            "progress_interval": 15,
        },
        # Testing Operations
        OperationType.COMPREHENSIVE_TEST_SUITE: {
            "timeout_seconds": 10800,  # 3 hours
            "checkpoint_interval": 300,
            "progress_interval": 30,
        },
        OperationType.INTEGRATION_TESTING: {
            "timeout_seconds": 3600,
            "checkpoint_interval": 180,
            "progress_interval": 20,
        },
        OperationType.PERFORMANCE_TESTING: {
            "timeout_seconds": 7200,
            "checkpoint_interval": 300,
            "progress_interval": 30,
        },
        OperationType.LOAD_TESTING: {
            "timeout_seconds": 14400,  # 4 hours for comprehensive load tests
            "checkpoint_interval": 600,
            "progress_interval": 60,
        },
        # Knowledge Base Operations
        OperationType.KB_POPULATION: {
            "timeout_seconds": 7200,  # 2 hours
            "checkpoint_interval": 180,
            "progress_interval": 20,
        },
        OperationType.KB_OPTIMIZATION: {
            "timeout_seconds": 3600,
            "checkpoint_interval": 300,
            "progress_interval": 30,
        },
        OperationType.VECTOR_INDEXING: {
            "timeout_seconds": 10800,  # 3 hours for large indexes
            "checkpoint_interval": 300,
            "progress_interval": 30,
        },
        OperationType.SEMANTIC_ANALYSIS: {
            "timeout_seconds": 7200,
            "checkpoint_interval": 180,
            "progress_interval": 20,
        },
        # System Operations
        OperationType.BACKUP_OPERATION: {
            "timeout_seconds": 7200,
            "checkpoint_interval": 300,
            "progress_interval": 30,
        },
        OperationType.MIGRATION_OPERATION: {
            "timeout_seconds": 14400,  # 4 hours for large migrations
            "checkpoint_interval": 600,
            "progress_interval": 60,
        },
        OperationType.CLEANUP_OPERATION: {
            "timeout_seconds": 3600,
            "checkpoint_interval": 180,
            "progress_interval": 20,
        },
        OperationType.MONITORING_COLLECTION: {
            "timeout_seconds": 1800,  # 30 minutes
            "checkpoint_interval": 120,
            "progress_interval": 10,
        },
    }

    @classmethod
    def get_timeout_config(
        cls, operation_type: OperationType
    ) -> Dict[str, float]:
        """Get timeout configuration for an operation type."""
        return cls.TIMEOUT_PROFILES.get(
            operation_type,
            {
                "timeout_seconds": float(TimingConstants.STANDARD_TIMEOUT),
                "checkpoint_interval": 300,
                "progress_interval": 30,
            },
        )
