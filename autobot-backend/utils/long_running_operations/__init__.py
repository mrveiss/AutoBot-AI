# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Long-Running Operations Package

Issue #381: Extracted from long_running_operations_framework.py god class refactoring.
Provides comprehensive management for long-running operations with:
- Dynamic timeout profiles based on operation type
- Checkpoint/resume capabilities for resilience
- Real-time progress tracking with WebSocket broadcasting
- Background operation management with concurrency control

This package contains:
- types: Enums and dataclasses for operations
- checkpoint_manager: Checkpoint save/load/resume functionality
- progress_tracker: Real-time progress tracking and broadcasting
- operation_manager: Main operation lifecycle management
"""

from .checkpoint_manager import OperationCheckpointManager
from .operation_manager import LongRunningOperationManager, OperationExecutionContext
from .progress_tracker import OperationProgressTracker
from .types import (
    LongRunningOperation,
    LongRunningTimeoutConfig,
    OperationCheckpoint,
    OperationPriority,
    OperationProgress,
    OperationStatus,
    OperationType,
)

__all__ = [
    # Types and dataclasses
    "LongRunningOperation",
    "LongRunningTimeoutConfig",
    "OperationCheckpoint",
    "OperationPriority",
    "OperationProgress",
    "OperationStatus",
    "OperationType",
    # Managers
    "LongRunningOperationManager",
    "OperationCheckpointManager",
    "OperationExecutionContext",
    "OperationProgressTracker",
]
