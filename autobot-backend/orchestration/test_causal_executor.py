# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for causal validation and effect tracing.

Issue: Extend DAG executor with causal validation and effect tracing.
"""

from typing import Any, Dict, List

import pytest

from orchestration.causal_executor import CausalExecutor
from orchestration.causal_models import (
    CausalEffect,
    CausalEffectType,
    CausalMetadata,
)
from orchestration.causal_validator import CausalValidator
from orchestration.dag_executor import (
    DAGExecutionContext,
    DAGExecutor,
    DAGNode,
    WorkflowDAG,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_step_nodes(*ids: str) -> List[Dict[str, Any]]:
    """Create step nodes."""
    return [{"id": nid, "type": "step", "data": {"id": nid}} for nid in ids]


def _linear_edges(*ids: str) -> List[Dict[str, Any]]:
    """Create linear chain edges."""
    return [{"source": ids[i], "target": ids[i + 1]} for i in range(len(ids) - 1)]


async def _noop_executor(node: DAGNode, ctx: DAGExecutionContext) -> Dict[str, Any]:
    """Step executor that returns success."""
    return {"success": True, "node_id": node.node_id, "output": "done"}


async def _failing_executor(node: DAGNode, ctx: DAGExecutionContext) -> Dict[str, Any]:
    """Step executor that fails."""
    if node.node_id == "failing_step":
        raise RuntimeError("step failed intentionally")
    return {"success": True, "node_id": node.node_id}


# ---------------------------------------------------------------------------
# CausalValidator Tests
# ---------------------------------------------------------------------------


class TestCausalValidator:
    """Test causal validation logic."""

    def test_validate_no_issues_linear_workflow(self):
        """Simple linear workflow with no causal metadata should be valid."""
        nodes = _make_step_nodes("a", "b", "c")
        edges = _linear_edges("a", "b", "c")
        dag = WorkflowDAG(nodes, edges)

        validator = CausalValidator()
        result = validator.validate_workflow(dag, {})

        assert result.valid
        assert len(result.errors()) == 0

    def test_validate_backward_effect_error(self):
        """Backward causal effect (target before source) should error."""
        nodes = _make_step_nodes("a", "b")
        edges = [{"source": "a", "target": "b"}]
        dag = WorkflowDAG(nodes, edges)

        # Effect: b → a (backward, should fail)
        metadata = {
            "b": CausalMetadata(
                step_id="b",
                causal_effects=[
                    CausalEffect(
                        source_step_id="b",
                        target_step_id="a",
                        effect_type=CausalEffectType.CAUSES,
                    )
                ],
            )
        }

        validator = CausalValidator()
        result = validator.validate_workflow(dag, metadata)

        assert not result.valid
        errors = result.errors()
        assert len(errors) > 0
        assert any("backward" in e.message.lower() for e in errors)

    def test_validate_effect_target_not_found(self):
        """Effect targeting non-existent step should error."""
        nodes = _make_step_nodes("a", "b")
        edges = _linear_edges("a", "b")
        dag = WorkflowDAG(nodes, edges)

        metadata = {
            "a": CausalMetadata(
                step_id="a",
                causal_effects=[
                    CausalEffect(
                        source_step_id="a",
                        target_step_id="nonexistent",
                        effect_type=CausalEffectType.CAUSES,
                    )
                ],
            )
        }

        validator = CausalValidator()
        result = validator.validate_workflow(dag, metadata)

        assert not result.valid
        assert len(result.errors()) > 0

    def test_validate_prevents_without_condition_warns(self):
        """PREVENTS effect without condition should warn."""
        nodes = _make_step_nodes("a", "b")
        edges = _linear_edges("a", "b")
        dag = WorkflowDAG(nodes, edges)

        metadata = {
            "a": CausalMetadata(
                step_id="a",
                causal_effects=[
                    CausalEffect(
                        source_step_id="a",
                        target_step_id="b",
                        effect_type=CausalEffectType.PREVENTS,
                        condition=None,  # Missing condition
                    )
                ],
            )
        }

        validator = CausalValidator()
        result = validator.validate_workflow(dag, metadata)

        warnings = result.warnings()
        assert any("condition" in w.message.lower() for w in warnings)

    def test_validate_conflicting_mutations_warns(self):
        """Multiple steps modifying same state key should warn."""
        nodes = _make_step_nodes("a", "b")
        edges = _linear_edges("a", "b")
        dag = WorkflowDAG(nodes, edges)

        metadata = {
            "a": CausalMetadata(step_id="a", state_keys_modified=["shared_key"]),
            "b": CausalMetadata(step_id="b", state_keys_modified=["shared_key"]),
        }

        validator = CausalValidator()
        result = validator.validate_workflow(dag, metadata)

        warnings = result.warnings()
        assert any("modified by multiple steps" in w.message.lower() for w in warnings)

    def test_validate_amplifies_without_condition_warns(self):
        """AMPLIFIES (cascade) without condition should warn."""
        nodes = _make_step_nodes("a", "b")
        edges = _linear_edges("a", "b")
        dag = WorkflowDAG(nodes, edges)

        metadata = {
            "a": CausalMetadata(
                step_id="a",
                causal_effects=[
                    CausalEffect(
                        source_step_id="a",
                        target_step_id="b",
                        effect_type=CausalEffectType.AMPLIFIES,
                        condition=None,
                    )
                ],
            )
        }

        validator = CausalValidator()
        result = validator.validate_workflow(dag, metadata)

        warnings = result.warnings()
        assert any("amplifies" in w.message.lower() for w in warnings)


# ---------------------------------------------------------------------------
# CausalExecutor Tests
# ---------------------------------------------------------------------------


class TestCausalExecutor:
    """Test effect tracing and cascade analysis."""

    @pytest.mark.asyncio
    async def test_simple_linear_execution_traces_mutations(self):
        """Linear execution should trace state mutations."""
        nodes = _make_step_nodes("a", "b", "c")
        edges = _linear_edges("a", "b", "c")
        dag = WorkflowDAG(nodes, edges)

        executor = DAGExecutor(_noop_executor)
        causal_executor = CausalExecutor(executor)

        ctx = await causal_executor.execute(dag, "workflow_1", validate_causal=False)

        assert ctx.status == "completed"
        assert causal_executor.effect_trace is not None
        assert len(causal_executor.effect_trace.execution_frames) == 3

    @pytest.mark.asyncio
    async def test_effect_trace_records_outputs(self):
        """Effect trace should record step outputs."""
        nodes = _make_step_nodes("a", "b")
        edges = _linear_edges("a", "b")
        dag = WorkflowDAG(nodes, edges)

        executor = DAGExecutor(_noop_executor)
        causal_executor = CausalExecutor(executor)

        await causal_executor.execute(dag, "workflow_2", validate_causal=False)

        assert causal_executor.effect_trace is not None
        assert "a" in causal_executor.effect_trace.step_outputs
        assert "b" in causal_executor.effect_trace.step_outputs

    @pytest.mark.asyncio
    async def test_failure_cascade_analysis(self):
        """Cascade analysis should identify affected steps."""
        nodes = _make_step_nodes("a", "b", "c")
        edges = [
            {"source": "a", "target": "b"},
            {"source": "a", "target": "c"},  # Both b and c depend on a
        ]
        dag = WorkflowDAG(nodes, edges)

        # Metadata: a's failure affects b and c
        metadata = {
            "a": CausalMetadata(
                step_id="a",
                failure_cascades_to=["b", "c"],
                causal_effects=[
                    CausalEffect(
                        source_step_id="a",
                        target_step_id="b",
                        effect_type=CausalEffectType.AMPLIFIES,
                    ),
                    CausalEffect(
                        source_step_id="a",
                        target_step_id="c",
                        effect_type=CausalEffectType.AMPLIFIES,
                    ),
                ],
            )
        }

        executor = DAGExecutor(_failing_executor)
        causal_executor = CausalExecutor(executor, metadata)

        ctx = await causal_executor.execute(dag, "workflow_3", validate_causal=False)

        # Analyze cascades from the failed step
        report = causal_executor.analyze_cascades(ctx, "a")

        assert report.failed_step_id == "a"
        assert len(report.suggested_mitigation) > 0

    @pytest.mark.asyncio
    async def test_validation_before_execution(self):
        """Validation should run before execution if enabled."""
        nodes = _make_step_nodes("a", "b")
        edges = _linear_edges("a", "b")
        dag = WorkflowDAG(nodes, edges)

        executor = DAGExecutor(_noop_executor)
        causal_executor = CausalExecutor(executor)

        await causal_executor.execute(dag, "workflow_4", validate_causal=True)

        assert causal_executor.validation_result is not None
        assert causal_executor.validation_result.valid

    @pytest.mark.asyncio
    async def test_trace_effect_chain(self):
        """Should generate human-readable effect chain traces."""
        nodes = _make_step_nodes("a", "b")
        edges = _linear_edges("a", "b")
        dag = WorkflowDAG(nodes, edges)

        executor = DAGExecutor(_noop_executor)
        causal_executor = CausalExecutor(executor)

        await causal_executor.execute(dag, "workflow_5", validate_causal=False)

        # Get trace for a step output
        trace = causal_executor.trace_effect_chain("output")
        assert "mutation chain" in trace.lower() or "not modified" in trace.lower()

    @pytest.mark.asyncio
    async def test_summary_includes_execution_stats(self):
        """Summary should include execution statistics."""
        nodes = _make_step_nodes("a", "b", "c")
        edges = _linear_edges("a", "b", "c")
        dag = WorkflowDAG(nodes, edges)

        executor = DAGExecutor(_noop_executor)
        causal_executor = CausalExecutor(executor)

        await causal_executor.execute(dag, "workflow_6", validate_causal=False)

        summary = causal_executor.summary()
        assert "workflow_6" in summary
        assert "steps executed" in summary
        assert "mutated" in summary


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestCausalIntegration:
    """Integration tests with realistic workflows."""

    @pytest.mark.asyncio
    async def test_three_step_workflow_with_causal_dependencies(self):
        """
        Realistic scenario: three-step workflow with causal effects.

        Step A (prepare data) → Step B (process) → Step C (store)

        Causal effects:
        - A ENABLES B (B can't run without A's output)
        - B ENABLES C (C depends on B's transformation)
        """
        nodes = _make_step_nodes("prepare", "process", "store")
        edges = _linear_edges("prepare", "process", "store")
        dag = WorkflowDAG(nodes, edges)

        metadata = {
            "prepare": CausalMetadata(
                step_id="prepare",
                state_keys_modified=["raw_data"],
                causal_effects=[
                    CausalEffect(
                        source_step_id="prepare",
                        target_step_id="process",
                        effect_type=CausalEffectType.ENABLES,
                        description="prepare provides input for process",
                    )
                ],
            ),
            "process": CausalMetadata(
                step_id="process",
                state_keys_modified=["processed_data"],
                causal_effects=[
                    CausalEffect(
                        source_step_id="process",
                        target_step_id="store",
                        effect_type=CausalEffectType.ENABLES,
                        description="process transforms data for store",
                    )
                ],
            ),
            "store": CausalMetadata(step_id="store", state_keys_modified=["stored"]),
        }

        executor = DAGExecutor(_noop_executor)
        causal_executor = CausalExecutor(executor, metadata)

        ctx = await causal_executor.execute(dag, "data_pipeline", validate_causal=True)

        assert ctx.status == "completed"
        assert causal_executor.validation_result.valid
        assert len(causal_executor.effect_trace.execution_frames) == 3

    @pytest.mark.asyncio
    async def test_parallel_steps_with_join(self):
        """
        Parallel execution with join: two independent steps merging to one.

        Step A —\
                 → Join Step
        Step B —/
        """
        nodes = _make_step_nodes("a", "b", "join")
        edges = [
            {"source": "a", "target": "join"},
            {"source": "b", "target": "join"},
        ]
        dag = WorkflowDAG(nodes, edges)

        executor = DAGExecutor(_noop_executor)
        causal_executor = CausalExecutor(executor)

        ctx = await causal_executor.execute(dag, "parallel_workflow", validate_causal=False)

        assert ctx.status == "completed"
        assert len(causal_executor.effect_trace.execution_frames) == 3

    @pytest.mark.asyncio
    async def test_branching_with_conditions(self):
        """
        Conditional branching: condition node picks true/false branch.
        """
        nodes = [
            {"id": "check", "type": "condition", "data": {"condition": "True"}},
            {"id": "true_step", "type": "step", "data": {"id": "true_step"}},
            {"id": "false_step", "type": "step", "data": {"id": "false_step"}},
        ]
        edges = [
            {"source": "check", "target": "true_step", "label": True},
            {"source": "check", "target": "false_step", "label": False},
        ]
        dag = WorkflowDAG(nodes, edges)

        executor = DAGExecutor(_noop_executor)
        causal_executor = CausalExecutor(executor)

        ctx = await causal_executor.execute(dag, "conditional_workflow", validate_causal=False)

        assert ctx.status == "completed"
        # Only true_step should execute (condition is True)
        assert "true_step" in ctx.step_results
        assert "false_step" in ctx.skipped_nodes


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_metadata_map(self):
        """Should handle empty metadata gracefully."""
        nodes = _make_step_nodes("a")
        WorkflowDAG(nodes, [])

        executor = DAGExecutor(_noop_executor)
        causal_executor = CausalExecutor(executor, {})

        assert causal_executor.metadata_map == {}

    def test_validation_with_missing_metadata(self):
        """Should validate workflow with partial metadata."""
        nodes = _make_step_nodes("a", "b")
        edges = _linear_edges("a", "b")
        dag = WorkflowDAG(nodes, edges)

        metadata = {"a": CausalMetadata(step_id="a")}  # Only metadata for "a"

        validator = CausalValidator()
        result = validator.validate_workflow(dag, metadata)

        assert result.valid

    @pytest.mark.asyncio
    async def test_effect_trace_no_data(self):
        """Should handle effect trace when no execution happened."""
        executor = DAGExecutor(_noop_executor)
        causal_executor = CausalExecutor(executor)

        trace = causal_executor.trace_effect_chain("nonexistent_key")
        assert "not available" in trace.lower() or "not modified" in trace.lower()
