# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for DAGExecutor and WorkflowDAG.  Issue #2140."""

from typing import Any, Dict, List

import pytest

from constants.status_enums import TaskStatus
from orchestration.dag_executor import (
    DAGExecutionContext,
    DAGExecutor,
    DAGNode,
    NodeType,
    WorkflowDAG,
    _evaluate_condition,
    _evaluate_switch,
    build_dag,
    workflow_has_condition_nodes,
)
from orchestration.success_criteria import SuccessCriteria, SuccessCriteriaEvaluator, SuccessCriteriaType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_step_nodes(*ids: str) -> List[Dict[str, Any]]:
    return [{"id": nid, "type": "step", "data": {"id": nid}} for nid in ids]


def _make_condition_node(nid: str, expr: str) -> Dict[str, Any]:
    return {"id": nid, "type": "condition", "data": {"condition": expr}}


def _linear_edges(*ids: str) -> List[Dict[str, Any]]:
    """Build a left-to-right chain of unconditional edges."""
    return [{"source": ids[i], "target": ids[i + 1]} for i in range(len(ids) - 1)]


async def _noop_executor(node: DAGNode, ctx: DAGExecutionContext) -> Dict[str, Any]:
    return {"success": True, "node_id": node.node_id}


async def _failing_executor(node: DAGNode, ctx: DAGExecutionContext) -> Dict[str, Any]:
    raise RuntimeError("step failed intentionally")


# ---------------------------------------------------------------------------
# WorkflowDAG
# ---------------------------------------------------------------------------


class TestWorkflowDAG:
    def test_root_nodes_no_incoming(self):
        nodes = _make_step_nodes("a", "b", "c")
        edges = _linear_edges("a", "b", "c")
        dag = WorkflowDAG(nodes, edges)
        roots = dag.root_nodes()
        assert len(roots) == 1
        assert roots[0].node_id == "a"

    def test_two_roots_fork(self):
        nodes = _make_step_nodes("a", "b", "c")
        edges = [
            {"source": "a", "target": "c"},
            {"source": "b", "target": "c"},
        ]
        dag = WorkflowDAG(nodes, edges)
        root_ids = {n.node_id for n in dag.root_nodes()}
        assert root_ids == {"a", "b"}

    def test_no_cycle_linear(self):
        nodes = _make_step_nodes("a", "b", "c")
        dag = WorkflowDAG(nodes, _linear_edges("a", "b", "c"))
        assert dag.detect_cycle() is None

    def test_cycle_detected(self):
        nodes = _make_step_nodes("a", "b", "c")
        edges = [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
            {"source": "c", "target": "a"},  # cycle
        ]
        dag = WorkflowDAG(nodes, edges)
        cycle = dag.detect_cycle()
        assert cycle is not None
        assert len(cycle) >= 2

    def test_condition_node_type(self):
        nodes = [_make_condition_node("cond", "True")]
        dag = WorkflowDAG(nodes, [])
        assert dag.nodes["cond"].node_type == NodeType.CONDITION

    def test_has_condition_nodes_true(self):
        nodes = [_make_condition_node("c", "True")] + _make_step_nodes("a")
        dag = WorkflowDAG(nodes, [])
        assert dag.has_condition_nodes() is True

    def test_has_condition_nodes_false(self):
        dag = WorkflowDAG(_make_step_nodes("a", "b"), _linear_edges("a", "b"))
        assert dag.has_condition_nodes() is False

    def test_unknown_edge_source_skipped(self):
        nodes = _make_step_nodes("a")
        edges = [{"source": "ghost", "target": "a"}]
        dag = WorkflowDAG(nodes, edges)
        # Node "a" should still have no successors listed from "ghost"
        assert dag.successors("a") == []

    def test_from_step_list_builds_linear_dag(self):
        steps = [{"id": "s1"}, {"id": "s2"}, {"id": "s3"}]
        dag = WorkflowDAG.from_step_list(steps)
        assert len(dag.nodes) == 3
        assert len(dag.successors("s1")) == 1
        assert dag.successors("s1")[0].target == "s2"
        assert dag.successors("s3") == []

    def test_from_step_list_single_node(self):
        dag = WorkflowDAG.from_step_list([{"id": "only"}])
        assert "only" in dag.nodes
        assert dag.successors("only") == []


# ---------------------------------------------------------------------------
# _evaluate_condition
# ---------------------------------------------------------------------------


class TestEvaluateCondition:
    def _ctx(self, step_results=None):
        ctx = DAGExecutionContext(workflow_id="wf")
        if step_results:
            ctx.step_results.update(step_results)
        return ctx

    def test_literal_true(self):
        node = DAGNode("c", NodeType.CONDITION, {"condition": "True"})
        assert _evaluate_condition(node, self._ctx()) is True

    def test_literal_false(self):
        node = DAGNode("c", NodeType.CONDITION, {"condition": "False"})
        assert _evaluate_condition(node, self._ctx()) is False

    def test_result_lookup(self):
        ctx = self._ctx({"step1": {"exit_code": 0}})
        node = DAGNode("c", NodeType.CONDITION, {"condition": "results['step1']['exit_code'] == 0"})
        assert _evaluate_condition(node, ctx) is True

    def test_result_lookup_false_branch(self):
        ctx = self._ctx({"step1": {"exit_code": 1}})
        node = DAGNode("c", NodeType.CONDITION, {"condition": "results['step1']['exit_code'] == 0"})
        assert _evaluate_condition(node, ctx) is False

    def test_empty_expression_defaults_false(self):
        node = DAGNode("c", NodeType.CONDITION, {"condition": ""})
        assert _evaluate_condition(node, self._ctx()) is False

    def test_syntax_error_defaults_false(self):
        node = DAGNode("c", NodeType.CONDITION, {"condition": "((("})
        assert _evaluate_condition(node, self._ctx()) is False

    def test_import_blocked(self):
        node = DAGNode("c", NodeType.CONDITION, {"condition": "__import__('os').getcwd()"})
        # Should not raise; eval with no builtins will raise NameError → False
        assert _evaluate_condition(node, self._ctx()) is False


# ---------------------------------------------------------------------------
# DAGExecutor — linear graphs
# ---------------------------------------------------------------------------


class TestDAGExecutorLinear:
    @pytest.mark.asyncio
    async def test_single_node(self):
        nodes = _make_step_nodes("a")
        dag = WorkflowDAG(nodes, [])
        executor = DAGExecutor(_noop_executor)
        ctx = await executor.execute(dag, "wf1")
        assert ctx.status == TaskStatus.COMPLETED.value
        assert "a" in ctx.step_results

    @pytest.mark.asyncio
    async def test_linear_three_nodes(self):
        nodes = _make_step_nodes("a", "b", "c")
        dag = WorkflowDAG(nodes, _linear_edges("a", "b", "c"))
        executor = DAGExecutor(_noop_executor)
        ctx = await executor.execute(dag, "wf2")
        assert ctx.status == TaskStatus.COMPLETED.value
        assert set(ctx.step_results.keys()) == {"a", "b", "c"}

    @pytest.mark.asyncio
    async def test_failing_step_records_error(self):
        nodes = _make_step_nodes("a")
        dag = WorkflowDAG(nodes, [])
        executor = DAGExecutor(_failing_executor)
        ctx = await executor.execute(dag, "wf_fail")
        assert ctx.step_results["a"]["success"] is False
        assert "step failed intentionally" in ctx.step_results["a"]["error"]

    @pytest.mark.asyncio
    async def test_cycle_aborts_immediately(self):
        nodes = _make_step_nodes("a", "b")
        edges = [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]
        dag = WorkflowDAG(nodes, edges)
        executor = DAGExecutor(_noop_executor)
        ctx = await executor.execute(dag, "wf_cycle")
        assert ctx.status == TaskStatus.FAILED.value
        assert "cycle" in ctx.error.lower()

    @pytest.mark.asyncio
    async def test_empty_dag_fails(self):
        dag = WorkflowDAG([], [])
        executor = DAGExecutor(_noop_executor)
        ctx = await executor.execute(dag, "wf_empty")
        assert ctx.status == TaskStatus.FAILED.value


# ---------------------------------------------------------------------------
# DAGExecutor — branching (condition nodes)
# ---------------------------------------------------------------------------


class TestDAGExecutorBranching:
    def _branch_dag(self, condition_expr: str) -> WorkflowDAG:
        """Build a diamond: start → cond → (true_branch | false_branch) → end."""
        nodes = _make_step_nodes("start", "true_branch", "false_branch", "end") + [
            _make_condition_node("cond", condition_expr)
        ]
        edges = [
            {"source": "start", "target": "cond"},
            {"source": "cond", "target": "true_branch", "label": True},
            {"source": "cond", "target": "false_branch", "label": False},
            {"source": "true_branch", "target": "end"},
            {"source": "false_branch", "target": "end"},
        ]
        return WorkflowDAG(nodes, edges)

    @pytest.mark.asyncio
    async def test_true_branch_taken(self):
        dag = self._branch_dag("True")
        executed: List[str] = []

        async def recording_executor(node: DAGNode, ctx: DAGExecutionContext) -> Dict[str, Any]:
            executed.append(node.node_id)
            return {"success": True}

        executor = DAGExecutor(recording_executor)
        ctx = await executor.execute(dag, "wf_branch")
        assert ctx.status == TaskStatus.COMPLETED.value
        assert "true_branch" in executed
        assert "false_branch" not in executed
        assert "end" in executed
        assert ctx.branches_taken["cond"] is True

    @pytest.mark.asyncio
    async def test_false_branch_taken(self):
        dag = self._branch_dag("False")
        executed: List[str] = []

        async def recording_executor(node: DAGNode, ctx: DAGExecutionContext) -> Dict[str, Any]:
            executed.append(node.node_id)
            return {"success": True}

        executor = DAGExecutor(recording_executor)
        ctx = await executor.execute(dag, "wf_false")
        assert ctx.status == TaskStatus.COMPLETED.value
        assert "false_branch" in executed
        assert "true_branch" not in executed
        assert ctx.branches_taken["cond"] is False

    @pytest.mark.asyncio
    async def test_skipped_nodes_recorded(self):
        dag = self._branch_dag("True")
        executor = DAGExecutor(_noop_executor)
        ctx = await executor.execute(dag, "wf_skip")
        assert "false_branch" in ctx.skipped_nodes

    @pytest.mark.asyncio
    async def test_condition_result_in_step_results(self):
        dag = self._branch_dag("True")
        executor = DAGExecutor(_noop_executor)
        ctx = await executor.execute(dag, "wf_cond_result")
        assert ctx.step_results["cond"]["result"] is True
        assert ctx.step_results["cond"]["success"] is True


# ---------------------------------------------------------------------------
# DAGExecutor — fork / join (parallel branches)
# ---------------------------------------------------------------------------


class TestDAGExecutorForkJoin:
    @pytest.mark.asyncio
    async def test_two_parallel_branches_both_run(self):
        """Fork from root into A and B, both join into end."""
        nodes = _make_step_nodes("root", "branch_a", "branch_b", "end")
        edges = [
            {"source": "root", "target": "branch_a"},
            {"source": "root", "target": "branch_b"},
            {"source": "branch_a", "target": "end"},
            {"source": "branch_b", "target": "end"},
        ]
        dag = WorkflowDAG(nodes, edges)
        executed: List[str] = []

        async def recording_executor(node: DAGNode, ctx: DAGExecutionContext) -> Dict[str, Any]:
            executed.append(node.node_id)
            return {"success": True}

        executor = DAGExecutor(recording_executor)
        ctx = await executor.execute(dag, "wf_fork")
        assert ctx.status == TaskStatus.COMPLETED.value
        assert set(executed) == {"root", "branch_a", "branch_b", "end"}

    @pytest.mark.asyncio
    async def test_join_node_executed_once(self):
        """Join node must be executed exactly once even when two paths reach it."""
        nodes = _make_step_nodes("a", "b", "join")
        edges = [
            {"source": "a", "target": "join"},
            {"source": "b", "target": "join"},
        ]
        dag = WorkflowDAG(nodes, edges)
        call_count: Dict[str, int] = {}

        async def counting_executor(node: DAGNode, ctx: DAGExecutionContext) -> Dict[str, Any]:
            call_count[node.node_id] = call_count.get(node.node_id, 0) + 1
            return {"success": True}

        executor = DAGExecutor(counting_executor)
        await executor.execute(dag, "wf_join")
        assert call_count.get("join", 0) == 1


# ---------------------------------------------------------------------------
# Helpers — workflow_has_condition_nodes / build_dag
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_workflow_has_condition_nodes_true(self):
        steps = [{"id": "a", "type": "condition"}]
        edges = [{"source": "a", "target": "b"}]
        assert workflow_has_condition_nodes(steps, edges) is True

    def test_workflow_has_condition_nodes_false_no_edges(self):
        steps = [{"id": "a", "type": "condition"}]
        assert workflow_has_condition_nodes(steps, []) is False

    def test_workflow_has_condition_nodes_false_no_condition_type(self):
        steps = [{"id": "a", "type": "step"}]
        edges = [{"source": "a", "target": "b"}]
        assert workflow_has_condition_nodes(steps, edges) is False

    def test_build_dag_returns_workflow_dag(self):
        steps = _make_step_nodes("x", "y")
        edges = _linear_edges("x", "y")
        dag = build_dag(steps, edges)
        assert isinstance(dag, WorkflowDAG)
        assert "x" in dag.nodes
        assert "y" in dag.nodes


# ---------------------------------------------------------------------------
# DAGExecutor — SuccessCriteriaEvaluator integration
# ---------------------------------------------------------------------------


class TestDAGExecutorCriteriaEvaluator:
    @pytest.mark.asyncio
    async def test_dag_executor_evaluates_structured_criteria_when_injected(self):
        """criteria_evaluation is populated when evaluator + structured_criteria are provided."""
        nodes = _make_step_nodes("a")
        dag = WorkflowDAG(nodes, [])
        criteria = [
            SuccessCriteria(
                criteria_type=SuccessCriteriaType.EXIT_CODE,
                parameters={"expected": 0},
                description="exit zero",
            )
        ]

        async def step_with_exit_code(node: DAGNode, ctx: DAGExecutionContext) -> Dict[str, Any]:
            return {"success": True, "exit_code": 0, "node_id": node.node_id}

        executor = DAGExecutor(step_with_exit_code, criteria_evaluator=SuccessCriteriaEvaluator())
        ctx = await executor.execute(dag, "wf_criteria", context={"structured_criteria": criteria})

        assert ctx.status == TaskStatus.COMPLETED.value
        assert "overall" in ctx.criteria_evaluation
        assert "score" in ctx.criteria_evaluation

    @pytest.mark.asyncio
    async def test_dag_executor_skips_criteria_when_no_evaluator(self):
        """criteria_evaluation stays empty when no evaluator is injected."""
        nodes = _make_step_nodes("a")
        dag = WorkflowDAG(nodes, [])
        executor = DAGExecutor(_noop_executor)
        ctx = await executor.execute(dag, "wf_no_criteria")
        assert ctx.criteria_evaluation == {}


# ---------------------------------------------------------------------------
# _evaluate_switch + DAGExecutor switch-node routing (GH#9036)
# ---------------------------------------------------------------------------


def _make_switch_node(nid: str, switch_on: str) -> Dict[str, Any]:
    return {"id": nid, "type": "switch", "data": {"switch_on": switch_on}}


class TestEvaluateSwitch:
    def _ctx(self, results: Dict[str, Any]) -> DAGExecutionContext:
        ctx = DAGExecutionContext(workflow_id="wf")
        ctx.step_results = results
        return ctx

    def test_resolves_string_case(self):
        node = DAGNode("sw", NodeType.SWITCH, {"switch_on": "results['lang']['code']"})
        ctx = self._ctx({"lang": {"code": "es"}})
        assert _evaluate_switch(node, ctx) == "es"

    def test_missing_switch_on_routes_default(self):
        node = DAGNode("sw", NodeType.SWITCH, {"switch_on": ""})
        assert _evaluate_switch(node, self._ctx({})) == "default"

    def test_eval_error_routes_default(self):
        node = DAGNode("sw", NodeType.SWITCH, {"switch_on": "results['missing']['x']"})
        assert _evaluate_switch(node, self._ctx({})) == "default"


class TestDAGExecutorSwitch:
    def _switch_dag(self, switch_on: str) -> WorkflowDAG:
        """start → switch → (case_es | case_fr | case_default)."""
        nodes = _make_step_nodes("start", "case_es", "case_fr", "case_default") + [_make_switch_node("sw", switch_on)]
        edges = [
            {"source": "start", "target": "sw"},
            {"source": "sw", "target": "case_es", "label": "es"},
            {"source": "sw", "target": "case_fr", "label": "fr"},
            {"source": "sw", "target": "case_default", "label": "default"},
        ]
        return WorkflowDAG(nodes, edges)

    async def _run(self, dag: WorkflowDAG) -> tuple[List[str], DAGExecutionContext]:
        executed: List[str] = []

        async def recording_executor(node: DAGNode, ctx: DAGExecutionContext) -> Dict[str, Any]:
            executed.append(node.node_id)
            if node.node_id == "start":
                # Seed the discriminant the switch expression reads.
                ctx.step_results["lang"] = {"code": ctx.step_results.get("_seed", "es")}
            return {"success": True}

        executor = DAGExecutor(recording_executor)
        ctx = await executor.execute(dag, "wf_switch")
        return executed, ctx

    @pytest.mark.asyncio
    async def test_case_match_routes_to_matching_branch(self):
        dag = self._switch_dag("results['lang']['code']")
        executed, ctx = await self._run(dag)
        assert ctx.status == TaskStatus.COMPLETED.value
        assert "case_es" in executed
        assert "case_fr" not in executed
        assert "case_default" not in executed
        assert ctx.step_results["sw"]["case_value"] == "es"

    @pytest.mark.asyncio
    async def test_no_case_match_routes_to_default(self):
        # switch_on resolves to a value with no matching labeled edge.
        dag = self._switch_dag("'unmatched'")
        executed, ctx = await self._run(dag)
        assert "case_default" in executed
        assert "case_es" not in executed
        assert "case_fr" not in executed


# ---------------------------------------------------------------------------
# Safe expression evaluation — no eval() escape (GH#9036)
# ---------------------------------------------------------------------------


class TestConditionSafeEvaluation:
    def _ctx(self) -> DAGExecutionContext:
        return DAGExecutionContext(workflow_id="wf")

    def test_subclasses_escape_blocked(self):
        """__class__/__bases__ sandbox escape must NOT evaluate (returns False)."""
        node = DAGNode("c", NodeType.CONDITION, {"condition": "results.__class__.__bases__"})
        assert _evaluate_condition(node, self._ctx()) is False

    def test_attribute_access_blocked(self):
        node = DAGNode("c", NodeType.CONDITION, {"condition": "results.keys"})
        assert _evaluate_condition(node, self._ctx()) is False

    def test_subscript_comparison_true(self):
        ctx = self._ctx()
        ctx.step_results = {"step1": {"exit_code": 0}}
        node = DAGNode("c", NodeType.CONDITION, {"condition": "results['step1']['exit_code'] == 0"})
        assert _evaluate_condition(node, ctx) is True
