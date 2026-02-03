# Parallel Tool Execution System Design

**Issue**: #645 - Implement Industry-Standard Agent Architecture Patterns
**Author**: mrveiss
**Date**: 2025-12-28
**Status**: Draft

---

## 1. Overview

This document defines the design for a Parallel Tool Execution System inspired by the Cursor agent architecture. The system provides:

- Automatic dependency analysis between tool calls
- Parallel execution of independent operations
- Expected 3-5x performance improvement for multi-tool tasks
- Integration with the Event Stream for observability

---

## 2. Cursor Pattern Analysis

### 2.1 Core Principle

From the Cursor architecture:

> "DEFAULT TO PARALLEL: Unless output of A is required for input of B, always execute multiple tools simultaneously."

### 2.2 Parallel vs Sequential Rules

| Pattern | Execution | Example |
|---------|-----------|---------|
| **Always Parallel** | Independent operations | Multiple grep searches, file reads, web searches |
| **Always Sequential** | Dependent operations | Read file → Edit file, Search → Read → Edit chain |

### 2.3 Performance Impact

Cursor reports **3-5x faster** task completion with parallel execution.

---

## 3. Dependency Analysis

### 3.1 Tool Dependency Types

```python
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any

class DependencyType(Enum):
    """Types of dependencies between tool calls"""
    NONE = auto()           # No dependency, can run in parallel
    DATA = auto()           # Output of A is input to B
    RESOURCE = auto()       # Both access same resource (file, connection)
    ORDER = auto()          # Must run in specific order (create → use)
    TRANSACTIONAL = auto()  # Must complete together or rollback

@dataclass
class ToolCall:
    """Representation of a tool call for execution"""
    call_id: str
    tool_name: str
    arguments: dict
    priority: int = 0

    # Dependency tracking
    depends_on: list[str] = field(default_factory=list)  # Call IDs
    dependency_types: dict[str, DependencyType] = field(default_factory=dict)

    # Execution state
    status: str = "pending"  # pending, running, completed, failed
    result: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0

    # Parallel group
    parallel_group_id: str | None = None
```

### 3.2 Dependency Detection Rules

```python
class DependencyAnalyzer:
    """Analyzes dependencies between tool calls"""

    # Tools that read from resources
    READ_TOOLS = {
        "read_file", "grep_search", "file_search", "list_dir",
        "web_search", "query_database", "get_redis_value",
    }

    # Tools that write to resources
    WRITE_TOOLS = {
        "edit_file", "write_file", "delete_file",
        "execute_command", "set_redis_value", "insert_database",
    }

    # Tools that affect system state
    STATE_TOOLS = {
        "execute_command", "manage_service", "create_directory",
    }

    # Resource extraction patterns
    RESOURCE_EXTRACTORS = {
        "read_file": lambda args: args.get("file_path"),
        "edit_file": lambda args: args.get("file_path"),
        "write_file": lambda args: args.get("file_path"),
        "grep_search": lambda args: args.get("path"),
        "list_dir": lambda args: args.get("path"),
    }

    def analyze_dependencies(
        self,
        tool_calls: list[ToolCall],
    ) -> dict[str, list[str]]:
        """
        Analyze dependencies between tool calls.

        Returns:
            Dict mapping call_id to list of call_ids it depends on
        """
        dependencies: dict[str, list[str]] = {tc.call_id: [] for tc in tool_calls}

        for i, call_a in enumerate(tool_calls):
            for j, call_b in enumerate(tool_calls):
                if i >= j:  # Only check forward dependencies
                    continue

                dep_type = self._check_dependency(call_a, call_b)
                if dep_type != DependencyType.NONE:
                    dependencies[call_b.call_id].append(call_a.call_id)
                    call_b.dependency_types[call_a.call_id] = dep_type

        return dependencies

    def _check_dependency(
        self,
        call_a: ToolCall,
        call_b: ToolCall,
    ) -> DependencyType:
        """Check if call_b depends on call_a"""

        # Rule 1: Write → Read/Write on same resource
        if call_a.tool_name in self.WRITE_TOOLS:
            resource_a = self._extract_resource(call_a)
            resource_b = self._extract_resource(call_b)

            if resource_a and resource_b and self._resources_overlap(resource_a, resource_b):
                return DependencyType.RESOURCE

        # Rule 2: State-changing tools create order dependencies
        if call_a.tool_name in self.STATE_TOOLS:
            # Check if call_b might depend on state changed by call_a
            if self._might_depend_on_state(call_a, call_b):
                return DependencyType.ORDER

        # Rule 3: Explicit output → input dependency
        if self._has_data_dependency(call_a, call_b):
            return DependencyType.DATA

        return DependencyType.NONE

    def _extract_resource(self, call: ToolCall) -> str | None:
        """Extract resource identifier from tool call"""
        extractor = self.RESOURCE_EXTRACTORS.get(call.tool_name)
        if extractor:
            return extractor(call.arguments)
        return None

    def _resources_overlap(self, resource_a: str, resource_b: str) -> bool:
        """Check if two resources might conflict"""
        # Same file
        if resource_a == resource_b:
            return True

        # Parent-child directory relationship
        if resource_a.startswith(resource_b) or resource_b.startswith(resource_a):
            return True

        return False

    def _might_depend_on_state(
        self,
        state_call: ToolCall,
        dependent_call: ToolCall,
    ) -> bool:
        """Check if dependent_call might need state from state_call"""
        # Example: create_directory → write_file in that directory
        if state_call.tool_name == "create_directory":
            dir_path = state_call.arguments.get("path", "")
            file_path = dependent_call.arguments.get("file_path", "")
            if file_path.startswith(dir_path):
                return True

        return False

    def _has_data_dependency(
        self,
        call_a: ToolCall,
        call_b: ToolCall,
    ) -> bool:
        """Check if call_b uses output from call_a as input"""
        # This requires semantic analysis or explicit markers
        # For now, return False and rely on explicit depends_on
        return False
```

---

## 4. Parallel Execution Engine

### 4.1 Execution Graph

```python
from dataclasses import dataclass, field
import asyncio
from typing import Callable, Any
import logging

logger = logging.getLogger(__name__)

@dataclass
class ExecutionGraph:
    """Dependency graph for parallel execution"""

    calls: dict[str, ToolCall] = field(default_factory=dict)
    dependencies: dict[str, list[str]] = field(default_factory=dict)

    def add_call(self, call: ToolCall) -> None:
        """Add a tool call to the graph"""
        self.calls[call.call_id] = call
        self.dependencies[call.call_id] = call.depends_on.copy()

    def get_ready_calls(self) -> list[ToolCall]:
        """Get calls that are ready to execute (all dependencies satisfied)"""
        completed = {
            call_id for call_id, call in self.calls.items()
            if call.status == "completed"
        }

        ready = []
        for call_id, call in self.calls.items():
            if call.status != "pending":
                continue

            deps = self.dependencies.get(call_id, [])
            if all(dep_id in completed for dep_id in deps):
                ready.append(call)

        return ready

    def get_parallel_groups(self) -> list[list[ToolCall]]:
        """
        Group calls that can run in parallel.

        Returns ordered list of groups, where each group can run concurrently,
        but groups must run sequentially.
        """
        groups = []
        remaining = set(self.calls.keys())
        completed = set()

        while remaining:
            # Find calls with all dependencies completed
            ready = []
            for call_id in remaining:
                deps = self.dependencies.get(call_id, [])
                if all(dep_id in completed for dep_id in deps):
                    ready.append(self.calls[call_id])

            if not ready:
                # Circular dependency or error
                logger.error("Circular dependency detected in tool calls")
                break

            groups.append(ready)
            for call in ready:
                remaining.remove(call.call_id)
                completed.add(call.call_id)

        return groups

    def mark_completed(self, call_id: str, result: Any) -> None:
        """Mark a call as completed"""
        if call_id in self.calls:
            self.calls[call_id].status = "completed"
            self.calls[call_id].result = result

    def mark_failed(self, call_id: str, error: str) -> None:
        """Mark a call as failed"""
        if call_id in self.calls:
            self.calls[call_id].status = "failed"
            self.calls[call_id].error = error
```

### 4.2 Parallel Executor

```python
import asyncio
import time
from typing import Callable, Awaitable

from src.events.stream_manager import EventStreamManager
from src.events.types import AgentEvent, EventType

class ParallelToolExecutor:
    """Executes tool calls with automatic parallelization"""

    def __init__(
        self,
        tool_dispatcher: Callable[[str, dict], Awaitable[Any]],
        event_stream: EventStreamManager,
        max_parallel: int = 10,
    ):
        self.dispatch = tool_dispatcher
        self.event_stream = event_stream
        self.max_parallel = max_parallel
        self.analyzer = DependencyAnalyzer()

    async def execute_batch(
        self,
        tool_calls: list[ToolCall],
        task_id: str,
    ) -> dict[str, Any]:
        """
        Execute a batch of tool calls with automatic parallelization.

        Returns:
            Dict mapping call_id to result
        """
        if not tool_calls:
            return {}

        # Analyze dependencies
        dependencies = self.analyzer.analyze_dependencies(tool_calls)
        for call in tool_calls:
            call.depends_on = dependencies.get(call.call_id, [])

        # Build execution graph
        graph = ExecutionGraph()
        for call in tool_calls:
            graph.add_call(call)

        # Get parallel groups
        groups = graph.get_parallel_groups()

        logger.info(
            "Executing %d tool calls in %d groups (max parallel: %d)",
            len(tool_calls), len(groups), self.max_parallel
        )

        results: dict[str, Any] = {}

        # Execute groups sequentially, calls within groups in parallel
        for group_idx, group in enumerate(groups):
            logger.debug(
                "Executing group %d/%d with %d calls",
                group_idx + 1, len(groups), len(group)
            )

            # Assign parallel group ID
            group_id = f"group-{group_idx}"
            for call in group:
                call.parallel_group_id = group_id

            # Execute group in parallel (with limit)
            semaphore = asyncio.Semaphore(self.max_parallel)
            tasks = [
                self._execute_with_semaphore(call, task_id, semaphore)
                for call in group
            ]

            group_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for call, result in zip(group, group_results):
                if isinstance(result, Exception):
                    graph.mark_failed(call.call_id, str(result))
                    results[call.call_id] = {"error": str(result)}
                else:
                    graph.mark_completed(call.call_id, result)
                    results[call.call_id] = result

        return results

    async def _execute_with_semaphore(
        self,
        call: ToolCall,
        task_id: str,
        semaphore: asyncio.Semaphore,
    ) -> Any:
        """Execute a single tool call with semaphore limiting"""
        async with semaphore:
            return await self._execute_single(call, task_id)

    async def _execute_single(
        self,
        call: ToolCall,
        task_id: str,
    ) -> Any:
        """Execute a single tool call with event tracking"""
        call.status = "running"

        # Publish ACTION event
        action_event = AgentEvent(
            event_type=EventType.ACTION,
            content={
                "tool_name": call.tool_name,
                "arguments": call.arguments,
                "tool_id": call.call_id,
                "is_parallel": call.parallel_group_id is not None,
                "parallel_group_id": call.parallel_group_id,
                "depends_on": call.depends_on,
            },
            source="agent",
            task_id=task_id,
        )
        await self.event_stream.publish(action_event)

        # Execute
        start_time = time.monotonic()
        try:
            result = await self.dispatch(call.tool_name, call.arguments)
            success = True
            error = None
        except Exception as e:
            result = None
            success = False
            error = str(e)
            logger.error("Tool %s failed: %s", call.tool_name, e)

        execution_time = (time.monotonic() - start_time) * 1000
        call.execution_time_ms = execution_time

        # Publish OBSERVATION event
        await self.event_stream.publish(AgentEvent(
            event_type=EventType.OBSERVATION,
            content={
                "action_id": action_event.event_id,
                "tool_name": call.tool_name,
                "success": success,
                "result": result if success else None,
                "error": error,
                "execution_time_ms": execution_time,
            },
            source="tool",
            task_id=task_id,
            parent_event_id=action_event.event_id,
        ))

        if not success:
            raise RuntimeError(error)

        return result
```

---

## 5. Batching Strategies

### 5.1 Auto-Batching for Common Patterns

```python
class ToolBatcher:
    """Automatically batches similar tool calls for efficiency"""

    # Tools that can be batched
    BATCHABLE_TOOLS = {
        "grep_search": "queries",
        "file_search": "queries",
        "read_file": "file_paths",
        "web_search": "queries",
    }

    def batch_calls(
        self,
        tool_calls: list[ToolCall],
    ) -> list[ToolCall]:
        """
        Batch similar tool calls together.

        Example: 3 separate grep_search calls → 1 batched call with 3 patterns
        """
        batched = []
        batch_groups: dict[str, list[ToolCall]] = {}

        for call in tool_calls:
            if call.tool_name in self.BATCHABLE_TOOLS:
                key = call.tool_name
                if key not in batch_groups:
                    batch_groups[key] = []
                batch_groups[key].append(call)
            else:
                batched.append(call)

        # Create batched calls
        for tool_name, calls in batch_groups.items():
            if len(calls) == 1:
                batched.append(calls[0])
            else:
                batched.append(self._create_batch_call(tool_name, calls))

        return batched

    def _create_batch_call(
        self,
        tool_name: str,
        calls: list[ToolCall],
    ) -> ToolCall:
        """Create a single batched call from multiple similar calls"""
        batch_key = self.BATCHABLE_TOOLS[tool_name]

        # Combine arguments
        combined_args = calls[0].arguments.copy()
        batch_values = [call.arguments.get(batch_key) for call in calls]

        # For grep_search, combine patterns
        if tool_name == "grep_search":
            combined_args["patterns"] = batch_values
            del combined_args.get("pattern", None)

        return ToolCall(
            call_id=f"batch-{calls[0].call_id}",
            tool_name=f"{tool_name}_batch",
            arguments=combined_args,
            depends_on=[],
        )
```

---

## 6. Integration with Tool Registry

### 6.1 Enhanced Tool Registry

```python
# In src/tools/tool_registry.py

class ToolRegistry:
    def __init__(
        self,
        event_stream: EventStreamManager,
        max_parallel: int = 10,
    ):
        self.event_stream = event_stream
        self.parallel_executor = ParallelToolExecutor(
            tool_dispatcher=self._dispatch_tool,
            event_stream=event_stream,
            max_parallel=max_parallel,
        )
        self.batcher = ToolBatcher()

    async def execute_tools(
        self,
        tool_calls: list[dict],
        task_id: str,
        auto_parallel: bool = True,
    ) -> dict[str, Any]:
        """
        Execute multiple tool calls with automatic parallelization.

        Args:
            tool_calls: List of {tool_name, arguments} dicts
            task_id: Current task ID
            auto_parallel: Whether to automatically parallelize

        Returns:
            Dict mapping call IDs to results
        """
        # Convert to ToolCall objects
        calls = [
            ToolCall(
                call_id=str(uuid.uuid4()),
                tool_name=tc["tool_name"],
                arguments=tc["arguments"],
            )
            for tc in tool_calls
        ]

        if auto_parallel and len(calls) > 1:
            # Batch similar calls
            calls = self.batcher.batch_calls(calls)

            # Execute with parallelization
            return await self.parallel_executor.execute_batch(calls, task_id)
        else:
            # Sequential execution
            results = {}
            for call in calls:
                try:
                    result = await self._dispatch_tool(call.tool_name, call.arguments)
                    results[call.call_id] = result
                except Exception as e:
                    results[call.call_id] = {"error": str(e)}
            return results

    async def _dispatch_tool(self, tool_name: str, arguments: dict) -> Any:
        """Dispatch to actual tool implementation"""
        # Existing dispatch table logic
        handler = self._get_handler(tool_name)
        return await handler(**arguments)
```

---

## 7. Configuration

```python
@dataclass
class ParallelExecutionConfig:
    """Parallel execution configuration"""
    enabled: bool = True
    max_parallel_calls: int = 10
    auto_batch: bool = True
    dependency_check: bool = True

    # Timeouts
    per_call_timeout_ms: int = 30000
    group_timeout_ms: int = 60000

    # Retry
    retry_failed: bool = True
    max_retries: int = 2
```

---

## 8. Performance Metrics

```python
@dataclass
class ParallelExecutionMetrics:
    """Metrics for parallel execution analysis"""
    total_calls: int = 0
    parallel_groups: int = 0
    sequential_calls: int = 0  # Calls that couldn't be parallelized

    total_time_ms: float = 0.0
    sequential_time_ms: float = 0.0  # Time if run sequentially
    parallel_time_ms: float = 0.0    # Actual parallel time

    speedup_factor: float = 1.0  # sequential_time / parallel_time

    def calculate_speedup(self) -> float:
        """Calculate speedup from parallelization"""
        if self.parallel_time_ms > 0:
            self.speedup_factor = self.sequential_time_ms / self.parallel_time_ms
        return self.speedup_factor
```

---

## 9. Examples

### 9.1 Parallel Grep Searches

```python
# Before: Sequential (3x slower)
for pattern in ["TODO", "FIXME", "BUG"]:
    await tool_registry.execute("grep_search", {"pattern": pattern})

# After: Automatic parallel
await tool_registry.execute_tools([
    {"tool_name": "grep_search", "arguments": {"pattern": "TODO"}},
    {"tool_name": "grep_search", "arguments": {"pattern": "FIXME"}},
    {"tool_name": "grep_search", "arguments": {"pattern": "BUG"}},
], task_id="search-task", auto_parallel=True)
# Runs all 3 concurrently
```

### 9.2 Dependency-Aware Execution

```python
# Read → Edit chain (must be sequential)
tool_calls = [
    ToolCall(call_id="1", tool_name="read_file", arguments={"file_path": "config.py"}),
    ToolCall(call_id="2", tool_name="edit_file", arguments={"file_path": "config.py", ...}),
]

# Analyzer detects resource dependency
# Execution: Group 1 [read], Group 2 [edit]
```

### 9.3 Mixed Parallel/Sequential

```python
tool_calls = [
    # Independent reads (parallel)
    ToolCall(call_id="1", tool_name="read_file", arguments={"file_path": "a.py"}),
    ToolCall(call_id="2", tool_name="read_file", arguments={"file_path": "b.py"}),
    ToolCall(call_id="3", tool_name="read_file", arguments={"file_path": "c.py"}),

    # Dependent edit (after reads)
    ToolCall(call_id="4", tool_name="edit_file", arguments={"file_path": "a.py"}, depends_on=["1"]),
]

# Execution:
# Group 1: [read a.py, read b.py, read c.py] - parallel
# Group 2: [edit a.py] - after read completes
```

---

## 10. File Structure

```
src/tools/
├── __init__.py
├── tool_registry.py       # Enhanced with parallel execution
├── parallel/
│   ├── __init__.py
│   ├── analyzer.py        # DependencyAnalyzer
│   ├── executor.py        # ParallelToolExecutor
│   ├── graph.py           # ExecutionGraph
│   ├── batcher.py         # ToolBatcher
│   └── metrics.py         # ParallelExecutionMetrics
└── handlers/              # Individual tool handlers
```

---

## 11. Testing Strategy

```python
async def test_independent_calls_parallel():
    """Test that independent calls run in parallel"""
    executor = ParallelToolExecutor(...)

    calls = [
        ToolCall(call_id="1", tool_name="grep_search", arguments={"pattern": "a"}),
        ToolCall(call_id="2", tool_name="grep_search", arguments={"pattern": "b"}),
        ToolCall(call_id="3", tool_name="grep_search", arguments={"pattern": "c"}),
    ]

    start = time.monotonic()
    results = await executor.execute_batch(calls, "test-task")
    elapsed = (time.monotonic() - start) * 1000

    # All should complete
    assert len(results) == 3

    # Should be faster than 3x single call
    single_call_time = 100  # ms
    assert elapsed < single_call_time * 2  # Allow some overhead

async def test_dependent_calls_sequential():
    """Test that dependent calls run sequentially"""
    executor = ParallelToolExecutor(...)

    calls = [
        ToolCall(call_id="1", tool_name="read_file", arguments={"file_path": "x.py"}),
        ToolCall(call_id="2", tool_name="edit_file", arguments={"file_path": "x.py"}, depends_on=["1"]),
    ]

    results = await executor.execute_batch(calls, "test-task")

    # Verify order from execution times
    assert calls[0].execution_time_ms < calls[1].execution_time_ms
```

---

## 12. References

- Cursor Agent Prompt: `docs/external_apps/.../Cursor Prompts/Agent Prompt.txt`
- Current tool registry: `src/tools/tool_registry.py`
- asyncio.gather documentation: https://docs.python.org/3/library/asyncio-task.html
