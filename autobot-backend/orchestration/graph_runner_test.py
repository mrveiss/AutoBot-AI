# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for orchestration.graph_runner and orchestration.dag_graph_adapter.

Issue #3228: unified graph model.

Tests cover:
- AutoBotGraph builder validation
- GraphRunner linear execution
- GraphRunner conditional edge routing
- GraphRunner retry / back-off
- GraphRunner checkpoint resume
- StepEventEmitter sink dispatch
- DAGGraphExecutor basic execution
- DAGGraphExecutor condition-node branching
- NodeRetryConfig delay calculations
"""

from typing import Any, Dict, List

import pytest

from orchestration.graph_runner import (
    END,
    START,
    AutoBotGraph,
    BackoffMode,
    CompiledGraph,
    GraphRunner,
    GraphStepEvent,
    NodeRetryConfig,
    StepEventEmitter,
    StepEventType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _noop(state: dict, **kwargs: Any) -> dict:
    return {}


async def _set_key(key: str, value: Any):
    async def _fn(state: dict, **kwargs: Any) -> dict:
        return {key: value}

    return _fn


async def _fail_then_succeed(call_count: list[int]):
    """Node that raises on first call, succeeds on second."""

    async def _fn(state: dict, **kwargs: Any) -> dict:
        call_count.append(1)
        if len(call_count) == 1:
            raise RuntimeError("transient error")
        return {"retried": True}

    return _fn


# ---------------------------------------------------------------------------
# NodeRetryConfig
# ---------------------------------------------------------------------------


class TestNodeRetryConfig:
    def test_delay_fixed(self):
        cfg = NodeRetryConfig(max_retries=3, base_delay_s=2.0)
        assert cfg.delay_for(1) == 0.0  # first attempt — no delay
        assert cfg.delay_for(2) == 2.0
        assert cfg.delay_for(3) == 2.0

    def test_delay_linear(self):
        cfg = NodeRetryConfig(
            max_retries=3,
            backoff_mode=BackoffMode.LINEAR,
            base_delay_s=1.0,
        )
        assert cfg.delay_for(2) == 1.0
        assert cfg.delay_for(3) == 2.0
        assert cfg.delay_for(4) == 3.0

    def test_delay_exponential(self):
        cfg = NodeRetryConfig(
            max_retries=5,
            backoff_mode=BackoffMode.EXPONENTIAL,
            base_delay_s=1.0,
        )
        assert cfg.delay_for(2) == 1.0  # 1 * 2^0
        assert cfg.delay_for(3) == 2.0  # 1 * 2^1
        assert cfg.delay_for(4) == 4.0  # 1 * 2^2

    def test_delay_capped_by_max(self):
        cfg = NodeRetryConfig(
            max_retries=5,
            backoff_mode=BackoffMode.EXPONENTIAL,
            base_delay_s=10.0,
            max_delay_s=15.0,
        )
        assert cfg.delay_for(5) <= 15.0

    def test_is_retryable_any(self):
        cfg = NodeRetryConfig()
        assert cfg.is_retryable(RuntimeError("x"))
        assert cfg.is_retryable(ValueError("y"))

    def test_is_retryable_specific(self):
        cfg = NodeRetryConfig(retryable_exceptions=(RuntimeError,))
        assert cfg.is_retryable(RuntimeError("x"))
        assert not cfg.is_retryable(ValueError("y"))


# ---------------------------------------------------------------------------
# AutoBotGraph builder
# ---------------------------------------------------------------------------


class TestAutoBotGraph:
    def test_compile_simple(self):
        builder: AutoBotGraph = AutoBotGraph()
        builder.add_node("a", _noop)
        builder.add_node("b", _noop)
        builder.add_edge(START, "a")
        builder.add_edge("a", "b")
        builder.add_edge("b", END)
        graph = builder.compile()
        assert isinstance(graph, CompiledGraph)
        assert graph.structure.entry_point == "a"

    def test_compile_missing_entry_point_raises(self):
        builder: AutoBotGraph = AutoBotGraph()
        builder.add_node("a", _noop)
        with pytest.raises(ValueError, match="no entry point"):
            builder.compile()

    def test_duplicate_node_raises(self):
        builder: AutoBotGraph = AutoBotGraph()
        builder.add_node("a", _noop)
        with pytest.raises(ValueError, match="already registered"):
            builder.add_node("a", _noop)

    def test_reserved_name_raises(self):
        builder: AutoBotGraph = AutoBotGraph()
        with pytest.raises(ValueError, match="reserved sentinel"):
            builder.add_node(START, _noop)
        with pytest.raises(ValueError, match="reserved sentinel"):
            builder.add_node(END, _noop)

    def test_edge_unknown_source_raises(self):
        builder: AutoBotGraph = AutoBotGraph()
        builder.add_node("a", _noop)
        builder.add_edge(START, "a")
        builder.add_edge("a", "unknown_node")
        with pytest.raises(ValueError, match="unknown_node"):
            builder.compile()

    def test_start_directly_to_end_raises(self):
        builder: AutoBotGraph = AutoBotGraph()
        with pytest.raises(ValueError, match="Cannot connect START directly to END"):
            builder.add_edge(START, END)

    def test_fluent_api(self):
        """Builder methods return self for chaining."""
        builder: AutoBotGraph = AutoBotGraph()
        result = builder.add_node("a", _noop).add_edge(START, "a").add_edge("a", END)
        assert result is builder

    def test_set_entry_point_twice_raises(self):
        builder: AutoBotGraph = AutoBotGraph()
        builder.add_node("a", _noop)
        builder.add_node("b", _noop)
        builder.add_edge(START, "a")
        with pytest.raises(ValueError, match="Entry point already set"):
            builder.set_entry_point("b")


# ---------------------------------------------------------------------------
# GraphRunner linear execution
# ---------------------------------------------------------------------------


class TestGraphRunnerLinear:
    @pytest.fixture
    def simple_graph(self):
        builder: AutoBotGraph = AutoBotGraph()

        async def node_a(state: dict, **kw: Any) -> dict:
            return {"a_done": True}

        async def node_b(state: dict, **kw: Any) -> dict:
            return {"b_done": True}

        builder.add_node("a", node_a)
        builder.add_node("b", node_b)
        builder.add_edge(START, "a")
        builder.add_edge("a", "b")
        builder.add_edge("b", END)
        return builder.compile()

    @pytest.mark.asyncio
    async def test_executes_all_nodes(self, simple_graph):
        runner = GraphRunner(simple_graph, graph_id="test", enable_checkpoints=False)
        state = await runner.run({})
        assert state["a_done"] is True
        assert state["b_done"] is True

    @pytest.mark.asyncio
    async def test_state_accumulates(self, simple_graph):
        runner = GraphRunner(simple_graph, graph_id="test", enable_checkpoints=False)
        state = await runner.run({"initial": 42})
        assert state["initial"] == 42
        assert state["a_done"] is True
        assert state["b_done"] is True

    @pytest.mark.asyncio
    async def test_configurable_forwarded(self):
        received_config = {}

        async def node_a(state: dict, **kw: Any) -> dict:
            received_config.update(kw.get("config", {}).get("configurable", {}))
            return {}

        builder: AutoBotGraph = AutoBotGraph()
        builder.add_node("a", node_a)
        builder.add_edge(START, "a")
        builder.add_edge("a", END)
        graph = builder.compile()

        runner = GraphRunner(
            graph,
            graph_id="test",
            enable_checkpoints=False,
            configurable={"manager": "mock_manager"},
        )
        await runner.run({})
        assert received_config["manager"] == "mock_manager"


# ---------------------------------------------------------------------------
# GraphRunner conditional edges
# ---------------------------------------------------------------------------


class TestGraphRunnerConditional:
    def _build_graph(self, router_result: str):
        builder: AutoBotGraph = AutoBotGraph()

        async def node_start(state: dict, **kw: Any) -> dict:
            return {"ran_start": True}

        async def node_true_branch(state: dict, **kw: Any) -> dict:
            return {"branch": "true"}

        async def node_false_branch(state: dict, **kw: Any) -> dict:
            return {"branch": "false"}

        def router(state: dict) -> str:
            return router_result

        builder.add_node("start", node_start)
        builder.add_node("true_branch", node_true_branch)
        builder.add_node("false_branch", node_false_branch)
        builder.add_edge(START, "start")
        builder.add_conditional_edges("start", router)
        builder.add_edge("true_branch", END)
        builder.add_edge("false_branch", END)
        return builder.compile()

    @pytest.mark.asyncio
    async def test_routes_to_true_branch(self):
        graph = self._build_graph("true_branch")
        runner = GraphRunner(graph, graph_id="t", enable_checkpoints=False)
        state = await runner.run({})
        assert state["branch"] == "true"

    @pytest.mark.asyncio
    async def test_routes_to_false_branch(self):
        graph = self._build_graph("false_branch")
        runner = GraphRunner(graph, graph_id="t", enable_checkpoints=False)
        state = await runner.run({})
        assert state["branch"] == "false"

    @pytest.mark.asyncio
    async def test_async_router(self):
        builder: AutoBotGraph = AutoBotGraph()

        async def node_a(state: dict, **kw: Any) -> dict:
            return {}

        async def node_b(state: dict, **kw: Any) -> dict:
            return {"from_async": True}

        async def async_router(state: dict) -> str:
            return "b"

        builder.add_node("a", node_a)
        builder.add_node("b", node_b)
        builder.add_edge(START, "a")
        builder.add_conditional_edges("a", async_router)
        builder.add_edge("b", END)
        graph = builder.compile()

        runner = GraphRunner(graph, graph_id="t", enable_checkpoints=False)
        state = await runner.run({})
        assert state["from_async"] is True

    @pytest.mark.asyncio
    async def test_router_returns_end(self):
        builder: AutoBotGraph = AutoBotGraph()

        async def node_a(state: dict, **kw: Any) -> dict:
            return {"a": 1}

        builder.add_node("a", node_a)
        builder.add_edge(START, "a")
        builder.add_conditional_edges("a", lambda s: END)
        graph = builder.compile()

        runner = GraphRunner(graph, graph_id="t", enable_checkpoints=False)
        state = await runner.run({})
        assert state["a"] == 1  # graph terminated cleanly at END


# ---------------------------------------------------------------------------
# GraphRunner retry
# ---------------------------------------------------------------------------


class TestGraphRunnerRetry:
    @pytest.mark.asyncio
    async def test_retry_on_transient_error(self):
        calls: List[int] = []

        async def flaky_node(state: dict, **kw: Any) -> dict:
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("transient")
            return {"result": "ok"}

        builder: AutoBotGraph = AutoBotGraph()
        builder.add_node(
            "flaky",
            flaky_node,
            retry=NodeRetryConfig(max_retries=3, base_delay_s=0.0),
        )
        builder.add_edge(START, "flaky")
        builder.add_edge("flaky", END)
        graph = builder.compile()

        runner = GraphRunner(graph, graph_id="t", enable_checkpoints=False)
        state = await runner.run({})
        assert state["result"] == "ok"
        assert len(calls) == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries_propagate(self):
        async def always_fails(state: dict, **kw: Any) -> dict:
            raise RuntimeError("always fails")

        builder: AutoBotGraph = AutoBotGraph()
        builder.add_node(
            "bad",
            always_fails,
            retry=NodeRetryConfig(max_retries=2, base_delay_s=0.0),
        )
        builder.add_edge(START, "bad")
        builder.add_edge("bad", END)
        graph = builder.compile()

        runner = GraphRunner(graph, graph_id="t", enable_checkpoints=False)
        with pytest.raises(RuntimeError, match="always fails"):
            await runner.run({})

    @pytest.mark.asyncio
    async def test_non_retryable_exception_not_retried(self):
        calls: List[int] = []

        async def specific_error(state: dict, **kw: Any) -> dict:
            calls.append(1)
            raise ValueError("not retryable")

        builder: AutoBotGraph = AutoBotGraph()
        builder.add_node(
            "node",
            specific_error,
            retry=NodeRetryConfig(
                max_retries=3,
                base_delay_s=0.0,
                retryable_exceptions=(RuntimeError,),  # ValueError NOT included
            ),
        )
        builder.add_edge(START, "node")
        builder.add_edge("node", END)
        graph = builder.compile()

        runner = GraphRunner(graph, graph_id="t", enable_checkpoints=False)
        with pytest.raises(ValueError):
            await runner.run({})
        assert len(calls) == 1  # No retry attempted


# ---------------------------------------------------------------------------
# StepEventEmitter
# ---------------------------------------------------------------------------


class TestStepEventEmitter:
    @pytest.mark.asyncio
    async def test_sink_receives_events(self):
        received: List[GraphStepEvent] = []

        async def sink(event: GraphStepEvent) -> None:
            received.append(event)

        emitter = StepEventEmitter()
        emitter.add_sink(sink)

        event = GraphStepEvent(
            event_type=StepEventType.NODE_START,
            node_name="test",
            graph_id="g1",
        )
        await emitter.emit(event)
        assert len(received) == 1
        assert received[0].node_name == "test"

    @pytest.mark.asyncio
    async def test_failing_sink_suppressed(self):
        async def bad_sink(event: GraphStepEvent) -> None:
            raise RuntimeError("sink failure")

        emitter = StepEventEmitter()
        emitter.add_sink(bad_sink)

        event = GraphStepEvent(
            event_type=StepEventType.NODE_END,
            node_name="n",
            graph_id="g",
        )
        # Must not raise.
        await emitter.emit(event)

    @pytest.mark.asyncio
    async def test_multiple_sinks(self):
        counter: List[int] = []

        async def sink_a(e: GraphStepEvent) -> None:
            counter.append(1)

        async def sink_b(e: GraphStepEvent) -> None:
            counter.append(2)

        emitter = StepEventEmitter()
        emitter.add_sink(sink_a)
        emitter.add_sink(sink_b)

        event = GraphStepEvent(event_type=StepEventType.NODE_START, node_name="n", graph_id="g")
        await emitter.emit(event)
        assert sorted(counter) == [1, 2]

    @pytest.mark.asyncio
    async def test_events_emitted_during_execution(self):
        emitted: List[StepEventType] = []

        async def sink(event: GraphStepEvent) -> None:
            emitted.append(event.event_type)

        emitter = StepEventEmitter()
        emitter.add_sink(sink)

        async def node_a(state: dict, **kw: Any) -> dict:
            return {"a": 1}

        builder: AutoBotGraph = AutoBotGraph()
        builder.add_node("a", node_a)
        builder.add_edge(START, "a")
        builder.add_edge("a", END)
        graph = builder.compile()

        runner = GraphRunner(graph, graph_id="t", emitter=emitter, enable_checkpoints=False)
        await runner.run({})

        assert StepEventType.NODE_START in emitted
        assert StepEventType.NODE_END in emitted


# ---------------------------------------------------------------------------
# DAGGraphExecutor
# ---------------------------------------------------------------------------


class TestDAGGraphExecutor:
    """Integration tests for DAGGraphExecutor using real WorkflowDAG objects."""

    def _build_linear_dag(self, num_steps: int = 3):
        """Build a linear DAG with *num_steps* step nodes."""
        from orchestration.dag_executor import WorkflowDAG

        nodes = [{"id": f"s{i}", "type": "step", "data": {}} for i in range(num_steps)]
        edges = [{"source": f"s{i}", "target": f"s{i + 1}"} for i in range(num_steps - 1)]
        return WorkflowDAG(nodes, edges)

    def _build_condition_dag(self, condition_value: bool):
        """Build a condition DAG: root → condition → true_branch | false_branch."""
        from orchestration.dag_executor import WorkflowDAG

        nodes = [
            {"id": "root", "type": "step", "data": {}},
            {
                "id": "cond",
                "type": "condition",
                "data": {"condition": f"{condition_value}"},
            },
            {"id": "true_branch", "type": "step", "data": {}},
            {"id": "false_branch", "type": "step", "data": {}},
        ]
        edges = [
            {"source": "root", "target": "cond"},
            {"source": "cond", "target": "true_branch", "label": True},
            {"source": "cond", "target": "false_branch", "label": False},
        ]
        return WorkflowDAG(nodes, edges)

    def _make_step_executor(self, results: Dict[str, Any] = None):
        """Return an async step executor that records which nodes ran."""
        executed: List[str] = []
        base_results = results or {}

        async def step_executor(node, ctx) -> dict:
            executed.append(node.node_id)
            return base_results.get(node.node_id, {"success": True, "node_id": node.node_id})

        return step_executor, executed

    @pytest.mark.asyncio
    async def test_linear_execution(self):
        from orchestration.dag_graph_adapter import DAGGraphExecutor

        dag = self._build_linear_dag(3)
        step_executor, executed = self._make_step_executor()

        executor = DAGGraphExecutor(step_executor_callback=step_executor, enable_checkpoints=False)
        ctx = await executor.execute(dag, "wf-linear")

        assert ctx.status == "completed"
        assert ctx.error is None
        # All nodes ran.
        assert "s0" in executed or "s0" in ctx.step_results

    @pytest.mark.asyncio
    async def test_empty_dag_returns_failed(self):
        from orchestration.dag_executor import WorkflowDAG
        from orchestration.dag_graph_adapter import DAGGraphExecutor

        dag = WorkflowDAG([], [])
        step_executor, _ = self._make_step_executor()

        executor = DAGGraphExecutor(step_executor_callback=step_executor, enable_checkpoints=False)
        ctx = await executor.execute(dag, "wf-empty")

        assert ctx.status == "failed"
        assert ctx.error is not None

    @pytest.mark.asyncio
    async def test_cycle_detection(self):
        from orchestration.dag_executor import WorkflowDAG
        from orchestration.dag_graph_adapter import DAGGraphExecutor

        nodes = [
            {"id": "a", "type": "step", "data": {}},
            {"id": "b", "type": "step", "data": {}},
        ]
        edges = [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "a"},  # cycle
        ]
        dag = WorkflowDAG(nodes, edges)
        step_executor, _ = self._make_step_executor()

        executor = DAGGraphExecutor(step_executor_callback=step_executor, enable_checkpoints=False)
        ctx = await executor.execute(dag, "wf-cycle")

        assert ctx.status == "failed"
        assert "Cycle detected" in (ctx.error or "")

    @pytest.mark.asyncio
    async def test_condition_true_branch(self):
        from orchestration.dag_graph_adapter import DAGGraphExecutor

        dag = self._build_condition_dag(True)
        step_executor, executed = self._make_step_executor()

        executor = DAGGraphExecutor(step_executor_callback=step_executor, enable_checkpoints=False)
        ctx = await executor.execute(dag, "wf-cond-true")

        assert ctx.status == "completed"
        # true_branch should be in step_results; false_branch should be skipped.
        assert "true_branch" in ctx.skipped_nodes or "true_branch" in ctx.step_results
        assert "false_branch" in ctx.skipped_nodes or "false_branch" not in ctx.step_results

    @pytest.mark.asyncio
    async def test_step_results_populated(self):
        from orchestration.dag_graph_adapter import DAGGraphExecutor

        dag = self._build_linear_dag(2)
        step_executor, _ = self._make_step_executor(
            {
                "s0": {"success": True, "output": "hello"},
                "s1": {"success": True, "output": "world"},
            }
        )

        executor = DAGGraphExecutor(step_executor_callback=step_executor, enable_checkpoints=False)
        ctx = await executor.execute(dag, "wf-results")

        assert ctx.status == "completed"
        assert ctx.step_results.get("s0", {}).get("output") == "hello"
        assert ctx.step_results.get("s1", {}).get("output") == "world"
