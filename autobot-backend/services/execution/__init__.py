# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Pluggable Execution Backends (Issue #4343)

This package provides a unified interface for executing tasks on multiple backends:
- Local: Direct subprocess execution
- Docker: Isolated container execution
- SSH: Remote machine execution
- Modal: Serverless cloud execution

Example usage:
    from services.execution.execution_manager import get_execution_manager
    from services.execution.base_backend import ExecutionTask, BackendType

    manager = get_execution_manager()
    manager.register_backend(BackendType.LOCAL, LocalBackend())

    task = ExecutionTask(
        task_id="task-1",
        code="print('Hello World')",
        language="python",
    )

    result = await manager.execute(task)
    print(result.stdout)
"""

from services.execution.base_backend import (
    BackendType,
    ExecutionBackend,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTask,
    ResourceLimits,
)
from services.execution.claude_code_backend import (
    CLAUDE_CODE_BACKEND,
    ClaudeCodeBackend,
    build_claude_code_backend,
)
from services.execution.docker_backend import DockerBackend
from services.execution.execution_manager import (
    ExecutionManager,
    get_execution_manager,
)
from services.execution.local_backend import LocalBackend
from services.execution.modal_backend import ModalBackend
from services.execution.ssh_backend import SSHBackend

__all__ = [
    "BackendType",
    "ExecutionBackend",
    "ExecutionResult",
    "ExecutionStatus",
    "ExecutionTask",
    "ResourceLimits",
    "LocalBackend",
    "DockerBackend",
    "SSHBackend",
    "ModalBackend",
    "ExecutionManager",
    "get_execution_manager",
    # Claude Code / Agent SDK execution provider (Issue #10550)
    "CLAUDE_CODE_BACKEND",
    "ClaudeCodeBackend",
    "build_claude_code_backend",
]
