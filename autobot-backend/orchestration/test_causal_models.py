# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for causal models only (no integration imports).

Issue: Extend DAG executor with causal validation and effect tracing.
"""

import time

from orchestration.causal_models import (
    CascadeReport,
    CausalEffect,
    CausalEffectType,
    CausalMetadata,
    Dependency,
    DependencyType,
    EffectTrace,
    StateFrame,
)


class TestCausalModels:
    """Test basic causal model functionality."""

    def test_causal_effect_creation(self):
        """Should create a causal effect."""
        effect = CausalEffect(
            source_step_id="step_a",
            target_step_id="step_b",
            effect_type=CausalEffectType.CAUSES,
            description="A causes B",
        )

        assert effect.source_step_id == "step_a"
        assert effect.target_step_id == "step_b"
        assert effect.effect_type == CausalEffectType.CAUSES
        assert str(effect) == "step_a --causes--> step_b"

    def test_causal_effect_with_condition(self):
        """Should include condition in string representation."""
        effect = CausalEffect(
            source_step_id="a",
            target_step_id="b",
            effect_type=CausalEffectType.ENABLES,
            condition="result['status'] == 'success'",
        )

        assert "[if:" in str(effect)

    def test_causal_metadata_add_effect(self):
        """Should accumulate effects in metadata."""
        metadata = CausalMetadata(step_id="prepare")

        effect1 = CausalEffect(
            source_step_id="prepare",
            target_step_id="process",
            effect_type=CausalEffectType.ENABLES,
        )
        effect2 = CausalEffect(
            source_step_id="prepare",
            target_step_id="validate",
            effect_type=CausalEffectType.CAUSES,
        )

        metadata.add_effect(effect1)
        metadata.add_effect(effect2)

        assert len(metadata.causal_effects) == 2

    def test_causal_metadata_add_state_mutation(self):
        """Should track state keys modified."""
        metadata = CausalMetadata(step_id="step_a")

        metadata.add_state_mutation("data_v1")
        metadata.add_state_mutation("data_v1")  # Duplicate
        metadata.add_state_mutation("status")

        assert len(metadata.state_keys_modified) == 2
        assert "data_v1" in metadata.state_keys_modified
        assert "status" in metadata.state_keys_modified

    def test_effect_trace_add_frame(self):
        """Should record state frames."""
        trace = EffectTrace(workflow_id="wf_1")

        frame1 = StateFrame(
            step_id="a",
            timestamp=time.time(),
            state_snapshot={"key1": "value1"},
            mutations={"key1": "value1"},
        )
        frame2 = StateFrame(
            step_id="b",
            timestamp=time.time(),
            state_snapshot={"key1": "value1", "key2": "value2"},
            mutations={"key2": "value2"},
        )

        trace.add_frame(frame1)
        trace.add_frame(frame2)

        assert len(trace.execution_frames) == 2
        assert "key1" in trace.mutation_map
        assert "key2" in trace.mutation_map

    def test_effect_trace_record_output(self):
        """Should record step outputs."""
        trace = EffectTrace(workflow_id="wf_2")

        output_a = {"success": True, "data": "result_a"}
        output_b = {"success": True, "data": "result_b"}

        trace.record_output("step_a", output_a)
        trace.record_output("step_b", output_b)

        assert trace.step_outputs["step_a"] == output_a
        assert trace.step_outputs["step_b"] == output_b

    def test_effect_trace_get_mutations_by_step(self):
        """Should retrieve mutations by step."""
        trace = EffectTrace(workflow_id="wf_3")

        frame = StateFrame(
            step_id="prepare",
            timestamp=time.time(),
            state_snapshot={"raw_data": [1, 2, 3]},
            mutations={"raw_data": [1, 2, 3]},
        )
        trace.add_frame(frame)

        mutations = trace.get_mutations_by_step("prepare")
        assert "raw_data" in mutations

    def test_effect_trace_trace_effect(self):
        """Should return causal chain for a state key."""
        trace = EffectTrace(workflow_id="wf_4")

        t1 = time.time()
        frame1 = StateFrame(
            step_id="a",
            timestamp=t1,
            state_snapshot={"x": 1},
            mutations={"x": 1},
        )

        t2 = time.time() + 0.1
        frame2 = StateFrame(
            step_id="b",
            timestamp=t2,
            state_snapshot={"x": 2},
            mutations={"x": 2},
        )

        trace.add_frame(frame1)
        trace.add_frame(frame2)

        chain = trace.trace_effect("x")
        assert len(chain) == 2
        assert chain[0][0] == "a"
        assert chain[1][0] == "b"

    def test_cascade_report_add_affected(self):
        """Should track directly and indirectly affected steps."""
        report = CascadeReport(failed_step_id="a", failure_reason="timeout")

        report.add_affected("b", "depends on a", direct=True)
        report.add_affected("c", "depends on b", direct=False)
        report.add_affected("d", "depends on b", direct=False)

        assert len(report.directly_affected) == 1
        assert len(report.indirectly_affected) == 2
        assert report.total_affected == 3

    def test_cascade_report_summary(self):
        """Should generate readable summary."""
        report = CascadeReport(failed_step_id="a", failure_reason="error")
        report.add_affected("b", "failed", direct=True)

        summary = str(report)
        assert "a" in summary
        assert "1 direct" in summary

    def test_dependency_type_enum(self):
        """Should have standard dependency types."""
        assert DependencyType.DATA.value == "data"
        assert DependencyType.CONTROL.value == "control"
        assert DependencyType.CAUSAL.value == "causal"
        assert DependencyType.IMPLICIT.value == "implicit"

    def test_causal_effect_types_enum(self):
        """Should have standard effect types."""
        assert CausalEffectType.CAUSES.value == "causes"
        assert CausalEffectType.ENABLES.value == "enables"
        assert CausalEffectType.PREVENTS.value == "prevents"
        assert CausalEffectType.BLOCKS.value == "blocks"
        assert CausalEffectType.AMPLIFIES.value == "amplifies"
        assert CausalEffectType.MITIGATES.value == "mitigates"

    def test_dependency_creation(self):
        """Should create dependencies with optional causal effects."""
        dep = Dependency(
            source_step_id="a",
            target_step_id="b",
            dep_type=DependencyType.DATA,
        )

        assert dep.source_step_id == "a"
        assert dep.target_step_id == "b"
        assert str(dep) == "a --[data]--> b"

    def test_state_frame_str(self):
        """Should have readable string representation."""
        frame = StateFrame(
            step_id="process",
            timestamp=time.time(),
            state_snapshot={},
            mutations={"x": 1, "y": 2},
        )

        s = str(frame)
        assert "process" in s
        assert "mutations" in s  # Should mention mutations

    def test_effect_trace_str(self):
        """Should have readable string representation."""
        trace = EffectTrace(workflow_id="wf_test")

        frame = StateFrame(
            step_id="a",
            timestamp=time.time(),
            state_snapshot={"x": 1},
            mutations={"x": 1},
        )
        trace.add_frame(frame)

        s = str(trace)
        assert "wf_test" in s
        assert "1 frames" in s
        assert "1 mutated" in s


class TestCausalModelEdgeCases:
    """Test edge cases in causal models."""

    def test_effect_trace_mutations_map_accumulates(self):
        """Multiple frames for same key should accumulate."""
        trace = EffectTrace(workflow_id="wf")

        t1 = time.time()
        frame1 = StateFrame(
            step_id="a",
            timestamp=t1,
            state_snapshot={"x": 1},
            mutations={"x": 1},
        )

        t2 = time.time() + 0.05
        frame2 = StateFrame(
            step_id="b",
            timestamp=t2,
            state_snapshot={"x": 2},
            mutations={"x": 2},
        )

        trace.add_frame(frame1)
        trace.add_frame(frame2)

        mutations_of_x = trace.mutation_map["x"]
        assert len(mutations_of_x) == 2

    def test_cascade_report_no_duplicates(self):
        """Should not double-count affected steps."""
        report = CascadeReport(failed_step_id="a", failure_reason="error")

        report.add_affected("b", "reason1", direct=True)
        report.add_affected("b", "reason2", direct=True)  # Same step again

        # Should only appear once
        assert report.directly_affected.count("b") == 1

    def test_causal_metadata_empty_defaults(self):
        """Should have sensible defaults."""
        metadata = CausalMetadata(step_id="test")

        assert metadata.causal_effects == []
        assert metadata.state_keys_modified == []
        assert metadata.failure_cascades_to == []
        assert metadata.can_run_parallel_with == []

    def test_effect_trace_get_mutations_nonexistent_step(self):
        """Should return empty dict for nonexistent step."""
        trace = EffectTrace(workflow_id="wf")

        mutations = trace.get_mutations_by_step("nonexistent")
        assert mutations == {}

    def test_effect_trace_trace_effect_nonexistent_key(self):
        """Should return empty list for nonexistent key."""
        trace = EffectTrace(workflow_id="wf")

        chain = trace.trace_effect("nonexistent")
        assert chain == []
