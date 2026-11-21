# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Parallel Tool Execution System

Automatic parallelization of independent tool operations.
Inspired by Cursor's "DEFAULT TO PARALLEL" pattern.

Components:
- analyzer: Dependency analysis between tool calls
- executor: Parallel execution engine
- types: Tool call data structures

Usage:
    from tools.parallel import ParallelToolExecutor, ParallelToolCall

    executor = ParallelToolExecutor(dispatch_func, event_stream)

    calls = [
        ParallelToolCall(tool_name="grep_search", arguments={"pattern": "TODO"}),
        ParallelToolCall(tool_name="grep_search", arguments={"pattern": "FIXME"}),
    ]

    results = await executor.execute_batch(calls, task_id="task-123")
"""

from tools.parallel.analyzer import DependencyAnalyzer
from tools.parallel.executor import ExecutionGraph, ParallelToolExecutor
from tools.parallel.types import DependencyType, ParallelToolCall

__all__ = [
    "ParallelToolCall",
    "DependencyType",
    "DependencyAnalyzer",
    "ParallelToolExecutor",
    "ExecutionGraph",
]
