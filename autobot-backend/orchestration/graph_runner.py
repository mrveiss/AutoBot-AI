# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
UnifiedGraph / AutoBotGraph — shared graph execution model.

Issue #3228: unify DAG workflow executor and chat LangGraph into a single
graph model so checkpoint, retry, and step-event logic are implemented once.
Issue #6826: #3228 was closed prematurely; GraphRunner is the intended
**future canonical engine** for DAG and chat workflows.  It is used in tests
and via DAGGraphAdapter but not yet wired into production WorkflowExecutor
(missing parallel fan-out support — see #6826).

Design
------
The issue identifies three viable approaches.  This module implements the
**thin-adapter** strategy: both the DAG workflow executor and LangGraph chat
workflow remain intact but share a common ``GraphRunner`` engine that handles
cross-cutting concerns:

- Step-event emission (structured log entries emitted before/after each node)
- Checkpoint read/write so execution can resume from failure
- Retry with configurable back-off per node
- Conditional edge routing via a pure ``EdgeRouter``

``AutoBotGraph`` is the builder/registry that holds nodes and edges, validates
the graph, and returns an executor.  It intentionally mirrors the LangGraph
``StateGraph`` builder API so the chat workflow migration in a follow-up PR
requires only a mechanical substitution.

Migration path for chat/LangGraph
----------------------------------
``chat_workflow/graph.py`` currently builds a LangGraph ``StateGraph``.
That graph can be migrated in three steps once this module stabilises:

1.  Replace ``from langgraph.graph import StateGraph`` with
    ``from orchestration.graph_runner import AutoBotGraph``.
2.  Replace ``builder = StateGraph(ChatState)`` with
    ``builder = AutoBotGraph(ChatState)``.
3.  Replace ``builder.add_node`` / ``builder.add_edge`` /
    ``builder.add_conditional_edges`` calls with the equivalent
    ``AutoBotGraph`` calls (identical signatures).
4.  Remove the ``AsyncRedisSaver`` checkpointer wiring — ``GraphRunner``
    handles checkpointing internally via ``WorkflowCheckpointManager``.

The ``interrupt()`` mechanism used for command approval would be replaced by
a first-class ``GraphRunner.pause()`` / ``GraphRunner.resume()`` pair
(tracked in issue #6826 as a future enhancement; #3228 was closed prematurely).

Public surface
--------------
- ``NodeRunner``            — protocol a node callable must satisfy
- ``EdgeRouter``            — pure function that resolves the next node name
- ``GraphStepEvent``        — structured event emitted around each node
- ``StepEventEmitter``      — emits step events to pluggable sinks
- ``NodeRetryConfig``       — per-node retry/back-off configuration
- ``AutoBotGraph``          — builder: add nodes, edges, conditional edges
- ``GraphRunner``           — executes a compiled graph, emits events
- ``CompiledGraph``         — result of ``AutoBotGraph.compile()``
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    Generic,
    List,
    Protocol,
    Set,
    Tuple,
    Type,
    TypeVar,
    runtime_checkable,
)

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Sentinel values (mirror LangGraph convention)
# ---------------------------------------------------------------------------

#: Sentinel string used as the implicit start node name.
START: str = "__start__"
#: Sentinel string used as the implicit end node name.
END: str = "__end__"


# ---------------------------------------------------------------------------
# State type variable
# ---------------------------------------------------------------------------

StateT = TypeVar("StateT", bound=dict)


# ---------------------------------------------------------------------------
# Node / edge types
# ---------------------------------------------------------------------------


@runtime_checkable
class NodeRunner(Protocol[StateT]):
    """Protocol that every graph node must satisfy.

    A node is any async callable that accepts the current state dict and
    returns a (possibly partial) state dict.  The runner **merges** the
    returned dict into the existing state — nodes must not return a
    complete replacement state, only the keys they modify.

    Args:
        state: Current graph state.
        **kwargs: Additional keyword arguments forwarded by the runner
                  (e.g. ``config`` for LangGraph-compatible nodes).

    Returns:
        Partial state update dict.
    """

    async def __call__(self, state: StateT, **kwargs: Any) -> Dict[str, Any]: ...


#: Type alias for a sync or async conditional-edge router.
#: Receives the current state and returns the name of the next node
#: (or END to terminate).
EdgeRouter = Callable[[StateT], str | Coroutine[Any, Any, str]]


# ---------------------------------------------------------------------------
# Step events
# ---------------------------------------------------------------------------


class StepEventType(str, Enum):
    """Lifecycle events emitted around each graph node execution."""

    NODE_START = "node_start"
    NODE_END = "node_end"
    NODE_ERROR = "node_error"
    NODE_RETRY = "node_retry"
    NODE_SKIP = "node_skip"


@dataclass
class GraphStepEvent:
    """Structured event emitted before, after, or on error for a node.

    Consumers register sinks via ``StepEventEmitter.add_sink`` to receive
    these events for monitoring, tracing, or streaming to frontends.
    """

    event_type: StepEventType
    node_name: str
    graph_id: str
    attempt: int = 1
    elapsed_ms: float | None = None
    error: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)


#: Sink callable that receives step events asynchronously.
StepEventSink = Callable[[GraphStepEvent], Coroutine[Any, Any, None]]


class StepEventEmitter:
    """Emits ``GraphStepEvent`` objects to registered async sinks.

    Sinks are called concurrently via ``asyncio.gather``.  A failing sink
    is logged and suppressed so it never disrupts graph execution.
    """

    def __init__(self) -> None:
        self._sinks: List[StepEventSink] = []

    def add_sink(self, sink: StepEventSink) -> None:
        """Register an async event sink."""
        self._sinks.append(sink)

    async def emit(self, event: GraphStepEvent) -> None:
        """Emit *event* to all registered sinks in parallel."""
        if not self._sinks:
            return
        results = await asyncio.gather(
            *(sink(event) for sink in self._sinks),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.warning("StepEventSink raised (suppressed): %s", result)


# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------


class BackoffMode(str, Enum):
    """Back-off strategy for node retries."""

    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


@dataclass
class NodeRetryConfig:
    """Per-node retry configuration.

    Attributes:
        max_retries: Maximum number of retry attempts (0 = no retry).
        backoff_mode: Delay growth strategy.
        base_delay_s: Base delay in seconds before the first retry.
        max_delay_s: Upper bound on retry delay (prevents unbounded waits).
        retryable_exceptions: Only retry on these exception types.
                              Empty tuple means retry on any ``Exception``.
    """

    max_retries: int = 0
    backoff_mode: BackoffMode = BackoffMode.FIXED
    base_delay_s: float = 1.0
    max_delay_s: float = 60.0
    retryable_exceptions: Tuple[Type[Exception], ...] = field(default_factory=tuple)

    def delay_for(self, attempt: int) -> float:
        """Return the delay (seconds) before *attempt* (1-indexed)."""
        if attempt <= 1:
            return 0.0
        n = attempt - 1  # number of failures so far
        if self.backoff_mode == BackoffMode.EXPONENTIAL:
            delay = self.base_delay_s * (2 ** (n - 1))
        elif self.backoff_mode == BackoffMode.LINEAR:
            delay = self.base_delay_s * n
        else:
            delay = self.base_delay_s
        return min(delay, self.max_delay_s)

    def is_retryable(self, exc: Exception) -> bool:
        """Return True when *exc* qualifies for a retry."""
        if not self.retryable_exceptions:
            return True
        return isinstance(exc, self.retryable_exceptions)


# ---------------------------------------------------------------------------
# Internal graph structure
# ---------------------------------------------------------------------------


@dataclass
class _NodeEntry:
    """Internal: stores a registered node and its retry config."""

    name: str
    fn: NodeRunner
    retry: NodeRetryConfig = field(default_factory=NodeRetryConfig)


@dataclass
class _EdgeEntry:
    """Internal: stores an edge — unconditional or conditional."""

    source: str
    #: For unconditional edges: target node name (or END).
    target: str | None = None
    #: For conditional edges: router function (returns node name or END).
    router: EdgeRouter | None = None


# ---------------------------------------------------------------------------
# Checkpoint adapter (shared with WorkflowCheckpointManager)
# ---------------------------------------------------------------------------


class _CheckpointAdapter:
    """Thin async wrapper around ``WorkflowCheckpointManager``.

    ``WorkflowCheckpointManager`` uses sync Redis calls via the shared
    ``autobot_shared.redis_client``.  This adapter wraps each call in
    ``asyncio.get_running_loop().run_in_executor`` so graph execution
    remains non-blocking.

    When ``WorkflowCheckpointManager`` is unavailable (test environments)
    the adapter silently no-ops.
    """

    def __init__(self, graph_id: str) -> None:
        self._graph_id = graph_id
        self._manager: Any | None = None
        try:
            from orchestration.error_handler import WorkflowCheckpointManager

            self._manager = WorkflowCheckpointManager()
        except Exception as exc:
            logger.debug("Checkpoint manager unavailable (%s); skipping", exc)

    async def save(self, node_name: str, output: Dict[str, Any]) -> None:
        """Persist a checkpoint for *node_name*."""
        if self._manager is None:
            return
        try:
            from orchestration.error_handler import StepCheckpoint

            checkpoint = StepCheckpoint(
                step_id=node_name,
                status="completed",
                output=output,
            )
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._manager.save, self._graph_id, checkpoint)
        except Exception as exc:
            logger.warning(
                "GraphRunner: checkpoint save failed for %s/%s: %s",
                self._graph_id,
                node_name,
                exc,
            )

    async def load_all(self) -> Dict[str, Any]:
        """Return all persisted checkpoints keyed by node name."""
        if self._manager is None:
            return {}
        try:
            loop = asyncio.get_running_loop()
            checkpoints = await loop.run_in_executor(None, self._manager.load_all, self._graph_id)
            return {name: cp.output for name, cp in (checkpoints or {}).items()}
        except Exception as exc:
            logger.warning(
                "GraphRunner: checkpoint load failed for %s: %s",
                self._graph_id,
                exc,
            )
            return {}

    async def clear(self) -> None:
        """Remove all checkpoints for this graph run."""
        if self._manager is None:
            return
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._manager.clear, self._graph_id)
        except Exception as exc:
            logger.warning(
                "GraphRunner: checkpoint clear failed for %s: %s",
                self._graph_id,
                exc,
            )


# ---------------------------------------------------------------------------
# CompiledGraph
# ---------------------------------------------------------------------------


@dataclass
class _CompiledStructure:
    """Validated, immutable graph topology returned by ``AutoBotGraph.compile()``."""

    nodes: Dict[str, _NodeEntry]
    edges: List[_EdgeEntry]
    entry_point: str

    def successors(self, node_name: str) -> List[_EdgeEntry]:
        """Return all outgoing edge entries for *node_name*."""
        return [e for e in self.edges if e.source == node_name]


class CompiledGraph(Generic[StateT]):
    """A validated, ready-to-execute graph.

    Obtain via ``AutoBotGraph.compile()``.  Execute via
    ``GraphRunner(compiled).run(state)``.
    """

    def __init__(self, structure: _CompiledStructure) -> None:
        self._structure = structure

    @property
    def structure(self) -> _CompiledStructure:
        return self._structure


# ---------------------------------------------------------------------------
# AutoBotGraph (builder)
# ---------------------------------------------------------------------------


class AutoBotGraph(Generic[StateT]):
    """Builder that constructs a validated ``CompiledGraph``.

    API is intentionally aligned with the LangGraph ``StateGraph`` builder
    to ease future migration:

    - ``add_node(name, fn, retry=...)``
    - ``add_edge(source, target)``
    - ``add_conditional_edges(source, router)``
    - ``set_entry_point(name)``
    - ``compile() -> CompiledGraph``

    Unlike LangGraph, ``AutoBotGraph`` does not require a ``TypedDict``
    schema argument; it accepts any dict subtype as state.
    """

    def __init__(self, state_type: Type[StateT] | None = None) -> None:
        self._state_type = state_type
        self._nodes: Dict[str, _NodeEntry] = {}
        self._edges: List[_EdgeEntry] = []
        self._entry_point: str | None = None

    # ------------------------------------------------------------------
    # Builder methods
    # ------------------------------------------------------------------

    def add_node(
        self,
        name: str,
        fn: NodeRunner,
        retry: NodeRetryConfig | None = None,
    ) -> "AutoBotGraph[StateT]":
        """Register a node.

        Args:
            name: Unique node identifier.
            fn:   Async callable ``(state, **kwargs) -> partial_state_dict``.
            retry: Optional per-node retry configuration.

        Returns:
            self (fluent API).
        """
        if name in (START, END):
            raise ValueError(f"'{name}' is a reserved sentinel and cannot be used as a node name.")
        if name in self._nodes:
            raise ValueError(f"Node '{name}' is already registered.")
        self._nodes[name] = _NodeEntry(
            name=name,
            fn=fn,
            retry=retry or NodeRetryConfig(),
        )
        return self

    def add_edge(self, source: str, target: str) -> "AutoBotGraph[StateT]":
        """Add an unconditional edge from *source* to *target*.

        *source* may be the ``START`` sentinel (sets entry point).
        *target* may be ``END``.
        """
        if source == START:
            if self._entry_point is not None:
                raise ValueError("Entry point already set.")
            if target == END:
                raise ValueError("Cannot connect START directly to END.")
            self._entry_point = target
            return self

        self._edges.append(_EdgeEntry(source=source, target=target))
        return self

    def add_conditional_edges(
        self,
        source: str,
        router: EdgeRouter,
    ) -> "AutoBotGraph[StateT]":
        """Add a conditional edge from *source* whose target is chosen by *router*.

        Args:
            source: The node whose output drives the routing decision.
            router: Sync or async callable ``(state) -> node_name | END``.
        """
        self._edges.append(_EdgeEntry(source=source, router=router))
        return self

    def set_entry_point(self, name: str) -> "AutoBotGraph[StateT]":
        """Explicitly set the entry node (alternative to ``add_edge(START, name)``)."""
        if self._entry_point is not None:
            raise ValueError("Entry point already set.")
        self._entry_point = name
        return self

    # ------------------------------------------------------------------
    # Compilation
    # ------------------------------------------------------------------

    def compile(self) -> CompiledGraph[StateT]:
        """Validate topology and return an executable ``CompiledGraph``.

        Raises:
            ValueError: When the graph is malformed (missing entry point,
                        edges referencing unknown nodes, etc.).
        """
        if not self._entry_point:
            raise ValueError("Graph has no entry point. " "Call set_entry_point() or add_edge(START, '<node>').")

        # Validate edge sources/targets reference known nodes or sentinels.
        known = set(self._nodes.keys()) | {START, END}
        for edge in self._edges:
            if edge.source not in known:
                raise ValueError(f"Edge source '{edge.source}' is not a registered node.")
            if edge.target is not None and edge.target not in known:
                raise ValueError(f"Edge target '{edge.target}' is not a registered node.")

        structure = _CompiledStructure(
            nodes=dict(self._nodes),
            edges=list(self._edges),
            entry_point=self._entry_point,
        )
        logger.debug(
            "AutoBotGraph compiled: %d nodes, %d edges, entry=%s",
            len(structure.nodes),
            len(structure.edges),
            structure.entry_point,
        )
        return CompiledGraph(structure)


# ---------------------------------------------------------------------------
# GraphRunner
# ---------------------------------------------------------------------------


class GraphRunner(Generic[StateT]):
    """Executes a ``CompiledGraph`` against an initial state dict.

    Responsibilities (all handled here, not in individual nodes):
    - Node execution with configurable retry / back-off
    - Checkpoint save after each successful node
    - Checkpoint load for resume-from-failure
    - ``GraphStepEvent`` emission before/after/on-error for each node
    - Conditional edge resolution (sync or async routers supported)

    Args:
        graph:      Compiled graph to execute.
        graph_id:   Logical identifier for this execution run (used for
                    checkpointing and logging).
        emitter:    Optional ``StepEventEmitter``; created internally
                    if not provided.
        enable_checkpoints: When False, checkpoint save/load are skipped.
        configurable: Arbitrary key-value pairs forwarded to each node
                      via ``kwargs["config"]["configurable"]``.  Mirrors
                      the LangGraph ``RunnableConfig`` pattern.
    """

    def __init__(
        self,
        graph: CompiledGraph[StateT],
        graph_id: str = "",
        emitter: StepEventEmitter | None = None,
        enable_checkpoints: bool = True,
        configurable: Dict[str, Any] | None = None,
    ) -> None:
        self._graph = graph
        self._graph_id = graph_id
        self._emitter = emitter or StepEventEmitter()
        self._checkpoint = _CheckpointAdapter(graph_id) if enable_checkpoints and graph_id else None
        self._configurable = configurable or {}

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        initial_state: StateT,
        resume_from_checkpoint: bool = False,
    ) -> StateT:
        """Execute the graph from the entry point.

        Args:
            initial_state:          Initial state dict.
            resume_from_checkpoint: When True, load persisted checkpoints and
                                    skip nodes that already completed.

        Returns:
            Final merged state dict after all nodes have executed.
        """
        state: Dict[str, Any] = dict(initial_state)

        # Seed state from checkpoints so resume works correctly.
        completed_nodes: Set[str] = set()
        if resume_from_checkpoint and self._checkpoint:
            checkpoints = await self._checkpoint.load_all()
            if checkpoints:
                logger.info(
                    "GraphRunner %s: resuming with %d checkpointed node(s): %s",
                    self._graph_id,
                    len(checkpoints),
                    list(checkpoints.keys()),
                )
                for node_name, output in checkpoints.items():
                    if isinstance(output, dict):
                        state.update(output)
                    completed_nodes.add(node_name)

        structure = self._graph.structure
        current_node = structure.entry_point

        while current_node and current_node != END:
            if current_node not in structure.nodes:
                logger.error(
                    "GraphRunner %s: unknown node '%s'; halting",
                    self._graph_id,
                    current_node,
                )
                break

            # Skip if resumed and already completed.
            if current_node in completed_nodes:
                logger.debug(
                    "GraphRunner %s: skipping checkpointed node '%s'",
                    self._graph_id,
                    current_node,
                )
                current_node = await self._resolve_next(current_node, state, structure)
                continue

            node_entry = structure.nodes[current_node]
            partial_update = await self._execute_node(node_entry, state)

            if isinstance(partial_update, dict):
                state.update(partial_update)
                # Checkpoint after success.
                if self._checkpoint:
                    await self._checkpoint.save(current_node, partial_update)

            current_node = await self._resolve_next(current_node, state, structure)

        # Clear checkpoints on clean completion.
        if self._checkpoint and not state.get("error"):
            await self._checkpoint.clear()

        return state  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _execute_node(
        self,
        entry: _NodeEntry,
        state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute *entry.fn* with retry.  Emits step events."""
        retry = entry.retry
        attempt = 1
        config = {"configurable": dict(self._configurable)}

        while True:
            t0 = time.monotonic()
            await self._emitter.emit(
                GraphStepEvent(
                    event_type=StepEventType.NODE_START,
                    node_name=entry.name,
                    graph_id=self._graph_id,
                    attempt=attempt,
                )
            )
            try:
                result = await entry.fn(state, config=config)
                elapsed = (time.monotonic() - t0) * 1000
                await self._emitter.emit(
                    GraphStepEvent(
                        event_type=StepEventType.NODE_END,
                        node_name=entry.name,
                        graph_id=self._graph_id,
                        attempt=attempt,
                        elapsed_ms=elapsed,
                    )
                )
                logger.debug(
                    "GraphRunner %s: node '%s' completed in %.1f ms (attempt %d)",
                    self._graph_id,
                    entry.name,
                    elapsed,
                    attempt,
                )
                return result or {}
            except Exception as exc:
                elapsed = (time.monotonic() - t0) * 1000
                await self._emitter.emit(
                    GraphStepEvent(
                        event_type=StepEventType.NODE_ERROR,
                        node_name=entry.name,
                        graph_id=self._graph_id,
                        attempt=attempt,
                        elapsed_ms=elapsed,
                        error=str(exc),
                    )
                )
                logger.warning(
                    "GraphRunner %s: node '%s' raised on attempt %d: %s",
                    self._graph_id,
                    entry.name,
                    attempt,
                    exc,
                )
                if attempt <= retry.max_retries and retry.is_retryable(exc):
                    delay = retry.delay_for(attempt + 1)
                    await self._emitter.emit(
                        GraphStepEvent(
                            event_type=StepEventType.NODE_RETRY,
                            node_name=entry.name,
                            graph_id=self._graph_id,
                            attempt=attempt,
                            metadata={"delay_s": delay},
                        )
                    )
                    if delay > 0:
                        await asyncio.sleep(delay)
                    attempt += 1
                    continue
                # Exhausted retries — propagate.
                raise

    async def _resolve_next(
        self,
        current: str,
        state: Dict[str, Any],
        structure: _CompiledStructure,
    ) -> str | None:
        """Resolve the next node name from the outgoing edges of *current*."""
        edges = structure.successors(current)
        if not edges:
            return END

        for edge in edges:
            if edge.router is not None:
                # Conditional edge: invoke router.
                result = edge.router(state)
                if asyncio.iscoroutine(result):
                    result = await result
                return result  # type: ignore[return-value]
            # Unconditional edge.
            if edge.target is not None:
                return edge.target

        return END
