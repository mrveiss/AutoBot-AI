# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for sub-workflow composition.  Issue #2143."""

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from constants.status_enums import TaskStatus
from orchestration.sub_workflow import (
    MAX_NESTING_DEPTH,
    SubWorkflowExecutor,
    SubWorkflowStep,
    extract_sub_workflow_step,
    is_sub_workflow_step,
)
from orchestration.variable_resolver import StepOutput

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workflow_executor() -> MagicMock:
    """Return a MagicMock that satisfies WorkflowExecutor's interface."""
    executor = MagicMock()
    executor.execute_coordinated_workflow = AsyncMock(
        return_value={"status": TaskStatus.COMPLETED.value, "step_results": {}}
    )
    return executor


def _make_step_output(data: Dict[str, Any], status: str = TaskStatus.COMPLETED.value) -> StepOutput:
    import json

    stdout = json.dumps(data)
    return StepOutput(status=status, stdout=stdout, parsed_json=data)


# ---------------------------------------------------------------------------
# is_sub_workflow_step
# ---------------------------------------------------------------------------


class TestIsSubWorkflowStep:
    def test_valid_sub_workflow_step(self):
        step = {"id": "s1", "type": "sub_workflow", "workflow_id": "wf-child"}
        assert is_sub_workflow_step(step) is True

    def test_regular_step_returns_false(self):
        assert is_sub_workflow_step({"id": "s1", "type": "step", "action": "run"}) is False

    def test_missing_type_returns_false(self):
        assert is_sub_workflow_step({"id": "s1", "workflow_id": "wf-child"}) is False

    def test_empty_workflow_id_returns_false(self):
        assert is_sub_workflow_step({"id": "s1", "type": "sub_workflow", "workflow_id": ""}) is False

    def test_missing_workflow_id_returns_false(self):
        assert is_sub_workflow_step({"id": "s1", "type": "sub_workflow"}) is False


# ---------------------------------------------------------------------------
# extract_sub_workflow_step
# ---------------------------------------------------------------------------


class TestExtractSubWorkflowStep:
    def test_minimal_valid_step(self):
        step = {"id": "invoke", "type": "sub_workflow", "workflow_id": "wf-abc"}
        sub = extract_sub_workflow_step(step)
        assert sub.workflow_id == "wf-abc"
        assert sub.step_id == "invoke"
        assert sub.input_mapping == {}
        assert sub.output_key == "sub_workflow_output"

    def test_full_step_mapping(self):
        step = {
            "id": "run-child",
            "type": "sub_workflow",
            "workflow_id": "wf-pipeline",
            "input_mapping": {"path": "${steps.fetch.output.path}", "threshold": "0.8"},
            "output_key": "pipeline_result",
        }
        sub = extract_sub_workflow_step(step)
        assert sub.workflow_id == "wf-pipeline"
        assert sub.input_mapping == {
            "path": "${steps.fetch.output.path}",
            "threshold": "0.8",
        }
        assert sub.output_key == "pipeline_result"
        assert sub.step_id == "run-child"

    def test_missing_workflow_id_raises(self):
        with pytest.raises(ValueError, match="missing 'workflow_id'"):
            extract_sub_workflow_step({"id": "bad", "type": "sub_workflow"})

    def test_empty_workflow_id_raises(self):
        with pytest.raises(ValueError, match="missing 'workflow_id'"):
            extract_sub_workflow_step({"id": "bad", "type": "sub_workflow", "workflow_id": ""})


# ---------------------------------------------------------------------------
# SubWorkflowExecutor — basic execution
# ---------------------------------------------------------------------------


class TestSubWorkflowExecutorBasic:
    def _make_executor(self, workflow_def: Dict[str, Any] | None) -> SubWorkflowExecutor:
        wf_executor = _make_workflow_executor()
        fetcher = MagicMock(return_value=workflow_def)
        return SubWorkflowExecutor(workflow_executor=wf_executor, workflow_fetcher=fetcher)

    @pytest.mark.asyncio
    async def test_basic_execution_returns_success(self):
        workflow_def = {"steps": [{"id": "child_step", "type": "step", "action": "do"}]}
        executor = self._make_executor(workflow_def)
        sub_step = SubWorkflowStep(workflow_id="wf-child", step_id="invoke")

        result = await executor.execute(sub_step, parent_context={}, parent_step_outputs={})

        assert result["success"] is True
        assert result["step_id"] == "invoke"
        assert "sub_workflow_result" in result

    @pytest.mark.asyncio
    async def test_failed_child_returns_success_false(self):
        workflow_def = {"steps": []}
        wf_executor = _make_workflow_executor()
        wf_executor.execute_coordinated_workflow = AsyncMock(
            return_value={"status": TaskStatus.FAILED.value, "step_results": {}}
        )
        fetcher = MagicMock(return_value=workflow_def)
        executor = SubWorkflowExecutor(workflow_executor=wf_executor, workflow_fetcher=fetcher)
        sub_step = SubWorkflowStep(workflow_id="wf-fail", step_id="invoke")

        result = await executor.execute(sub_step, parent_context={}, parent_step_outputs={})

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_missing_workflow_id_raises_value_error(self):
        executor = self._make_executor(None)
        sub_step = SubWorkflowStep(workflow_id="wf-missing", step_id="invoke")

        with pytest.raises(ValueError, match="not found"):
            await executor.execute(sub_step, parent_context={}, parent_step_outputs={})

    @pytest.mark.asyncio
    async def test_child_workflow_called_with_correct_id(self):
        workflow_def = {"steps": []}
        wf_executor = _make_workflow_executor()
        fetcher = MagicMock(return_value=workflow_def)
        executor = SubWorkflowExecutor(workflow_executor=wf_executor, workflow_fetcher=fetcher)
        sub_step = SubWorkflowStep(workflow_id="wf-target", step_id="invoke")

        await executor.execute(sub_step, parent_context={}, parent_step_outputs={})

        wf_executor.execute_coordinated_workflow.assert_awaited_once()
        call_kwargs = wf_executor.execute_coordinated_workflow.call_args
        assert call_kwargs.kwargs["workflow_id"] == "wf-target"


# ---------------------------------------------------------------------------
# SubWorkflowExecutor — variable mapping
# ---------------------------------------------------------------------------


class TestSubWorkflowExecutorVariableMapping:
    def _make_executor(self, workflow_def: Dict[str, Any]) -> tuple:
        wf_executor = _make_workflow_executor()
        fetcher = MagicMock(return_value=workflow_def)
        executor = SubWorkflowExecutor(workflow_executor=wf_executor, workflow_fetcher=fetcher)
        return executor, wf_executor

    @pytest.mark.asyncio
    async def test_literal_value_passed_as_child_input(self):
        workflow_def = {"steps": []}
        executor, wf_executor = self._make_executor(workflow_def)
        sub_step = SubWorkflowStep(
            workflow_id="wf-child",
            step_id="invoke",
            input_mapping={"threshold": "0.9"},
        )

        await executor.execute(sub_step, parent_context={}, parent_step_outputs={})

        call_kwargs = wf_executor.execute_coordinated_workflow.call_args
        child_ctx = call_kwargs.kwargs["context"]
        assert child_ctx["_sub_workflow_inputs"]["threshold"] == "0.9"

    @pytest.mark.asyncio
    async def test_variable_reference_resolved_from_parent_outputs(self):
        workflow_def = {"steps": []}
        executor, wf_executor = self._make_executor(workflow_def)
        parent_outputs = {"fetch": _make_step_output({"path": "/data/file.csv"})}
        sub_step = SubWorkflowStep(
            workflow_id="wf-child",
            step_id="invoke",
            input_mapping={"dataset_path": "${steps.fetch.output.path}"},
        )

        await executor.execute(sub_step, parent_context={}, parent_step_outputs=parent_outputs)

        call_kwargs = wf_executor.execute_coordinated_workflow.call_args
        child_ctx = call_kwargs.kwargs["context"]
        assert child_ctx["_sub_workflow_inputs"]["dataset_path"] == "/data/file.csv"

    @pytest.mark.asyncio
    async def test_unresolvable_reference_passed_as_raw_expression(self):
        """Unresolvable ${steps.…} tokens are passed through unchanged (with a warning)."""
        workflow_def = {"steps": []}
        executor, wf_executor = self._make_executor(workflow_def)
        sub_step = SubWorkflowStep(
            workflow_id="wf-child",
            step_id="invoke",
            input_mapping={"key": "${steps.missing_step.output.value}"},
        )

        await executor.execute(sub_step, parent_context={}, parent_step_outputs={})

        call_kwargs = wf_executor.execute_coordinated_workflow.call_args
        child_ctx = call_kwargs.kwargs["context"]
        # Unresolvable token is left as-is
        assert child_ctx["_sub_workflow_inputs"]["key"] == "${steps.missing_step.output.value}"

    @pytest.mark.asyncio
    async def test_no_input_mapping_produces_empty_inputs(self):
        workflow_def = {"steps": []}
        executor, wf_executor = self._make_executor(workflow_def)
        sub_step = SubWorkflowStep(workflow_id="wf-child", step_id="invoke")

        await executor.execute(sub_step, parent_context={}, parent_step_outputs={})

        call_kwargs = wf_executor.execute_coordinated_workflow.call_args
        child_ctx = call_kwargs.kwargs["context"]
        assert child_ctx["_sub_workflow_inputs"] == {}

    @pytest.mark.asyncio
    async def test_output_key_stored_in_result(self):
        workflow_def = {"steps": []}
        executor, _ = self._make_executor(workflow_def)
        sub_step = SubWorkflowStep(
            workflow_id="wf-child",
            step_id="invoke",
            output_key="my_custom_key",
        )

        result = await executor.execute(sub_step, parent_context={}, parent_step_outputs={})

        assert result["output_key"] == "my_custom_key"


# ---------------------------------------------------------------------------
# SubWorkflowExecutor — max depth guard
# ---------------------------------------------------------------------------


class TestSubWorkflowExecutorMaxDepth:
    @pytest.mark.asyncio
    async def test_max_depth_raises_recursion_error(self):
        wf_executor = _make_workflow_executor()
        fetcher = MagicMock(return_value={"steps": []})
        executor = SubWorkflowExecutor(workflow_executor=wf_executor, workflow_fetcher=fetcher)
        sub_step = SubWorkflowStep(workflow_id="wf-deep", step_id="invoke")

        with pytest.raises(RecursionError, match="maximum nesting depth"):
            await executor.execute(
                sub_step,
                parent_context={},
                parent_step_outputs={},
                current_depth=MAX_NESTING_DEPTH,
            )

    @pytest.mark.asyncio
    async def test_depth_just_below_max_executes_normally(self):
        """Depth of MAX_NESTING_DEPTH - 1 should not raise."""
        wf_executor = _make_workflow_executor()
        fetcher = MagicMock(return_value={"steps": []})
        executor = SubWorkflowExecutor(workflow_executor=wf_executor, workflow_fetcher=fetcher)
        sub_step = SubWorkflowStep(workflow_id="wf-near-limit", step_id="invoke")

        result = await executor.execute(
            sub_step,
            parent_context={},
            parent_step_outputs={},
            current_depth=MAX_NESTING_DEPTH - 1,
        )
        assert result["success"] is True

    def test_max_nesting_depth_constant(self):
        """Sanity-check: the constant is a positive integer."""
        assert isinstance(MAX_NESTING_DEPTH, int)
        assert MAX_NESTING_DEPTH > 0
