# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
    from tools.parallel import ParallelToolExecutor, ToolCall

    executor = ParallelToolExecutor(dispatch_func, event_stream)

    calls = [
        ToolCall(tool_name="grep_search", arguments={"pattern": "TODO"}),
        ToolCall(tool_name="grep_search", arguments={"pattern": "FIXME"}),
    ]

    results = await executor.execute_batch(calls, task_id="task-123")
"""

from backend.tools.parallel.types import ToolCall, DependencyType
from backend.tools.parallel.analyzer import DependencyAnalyzer
from backend.tools.parallel.executor import ParallelToolExecutor, ExecutionGraph

__all__ = [
    "ToolCall",
    "DependencyType",
    "DependencyAnalyzer",
    "ParallelToolExecutor",
    "ExecutionGraph",
]
