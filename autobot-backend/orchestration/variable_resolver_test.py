# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for VariableResolver and StepOutput.  Issue #2141."""

import json
from typing import Any, Dict

from constants.status_enums import TaskStatus
from orchestration.variable_resolver import (
    StepOutput,
    VariableResolver,
    resolve_variables,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _output(stdout: str = "", status: str = TaskStatus.COMPLETED.value) -> StepOutput:
    """Build a StepOutput from raw stdout string."""
    parsed: Any = None
    if stdout:
        try:
            parsed = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            pass
    return StepOutput(status=status, stdout=stdout, parsed_json=parsed)


def _json_output(data: Dict[str, Any], status: str = TaskStatus.COMPLETED.value) -> StepOutput:
    """Build a StepOutput whose parsed_json is *data*."""
    stdout = json.dumps(data)
    return StepOutput(status=status, stdout=stdout, parsed_json=data)


# ---------------------------------------------------------------------------
# StepOutput
# ---------------------------------------------------------------------------


class TestStepOutput:
    def test_from_step_result_success(self):
        result = {"success": True, "stdout": '{"key": "value"}', "exit_code": 0}
        so = StepOutput.from_step_result(result)
        assert so.status == TaskStatus.COMPLETED.value
        assert so.stdout == '{"key": "value"}'
        assert so.parsed_json == {"key": "value"}
        assert so.metadata["exit_code"] == 0

    def test_from_step_result_failure(self):
        result = {"success": False, "stdout": "", "error": "boom"}
        so = StepOutput.from_step_result(result)
        assert so.status == TaskStatus.FAILED.value
        assert so.parsed_json is None

    def test_from_step_result_non_json_stdout(self):
        result = {"success": True, "stdout": "plain text output"}
        so = StepOutput.from_step_result(result)
        assert so.parsed_json is None
        assert so.stdout == "plain text output"

    def test_from_step_result_missing_stdout(self):
        result = {"success": True}
        so = StepOutput.from_step_result(result)
        assert so.stdout == ""
        assert so.parsed_json is None

    def test_metadata_excludes_stdout_and_success(self):
        result = {"success": True, "stdout": "", "execution_time": 1.5}
        so = StepOutput.from_step_result(result)
        assert "execution_time" in so.metadata
        assert "stdout" not in so.metadata
        assert "success" not in so.metadata


# ---------------------------------------------------------------------------
# VariableResolver — no-op cases
# ---------------------------------------------------------------------------


class TestVariableResolverNoOp:
    def setup_method(self):
        self.resolver = VariableResolver()

    def test_string_with_no_tokens_passthrough(self):
        assert self.resolver.resolve("hello world", {}) == "hello world"

    def test_empty_string_passthrough(self):
        assert self.resolver.resolve("", {}) == ""

    def test_non_steps_token_passthrough(self):
        template = "${env.HOME}"
        assert self.resolver.resolve(template, {}) == template


# ---------------------------------------------------------------------------
# VariableResolver — status accessor
# ---------------------------------------------------------------------------


class TestVariableResolverStatus:
    def setup_method(self):
        self.resolver = VariableResolver()
        self.outputs = {
            "step1": StepOutput(status=TaskStatus.COMPLETED.value, stdout=""),
            "step2": StepOutput(status=TaskStatus.FAILED.value, stdout=""),
        }

    def test_status_completed(self):
        result = self.resolver.resolve("${steps.step1.status}", self.outputs)
        assert result == TaskStatus.COMPLETED.value

    def test_status_failed(self):
        result = self.resolver.resolve("${steps.step2.status}", self.outputs)
        assert result == TaskStatus.FAILED.value

    def test_status_in_sentence(self):
        result = self.resolver.resolve("Step finished with status: ${steps.step1.status}", self.outputs)
        assert result == "Step finished with status: completed"


# ---------------------------------------------------------------------------
# VariableResolver — simple output substitution
# ---------------------------------------------------------------------------


class TestVariableResolverSimpleOutput:
    def setup_method(self):
        self.resolver = VariableResolver()

    def test_output_returns_parsed_json_as_json_string(self):
        outputs = {"s1": _json_output({"a": 1})}
        result = self.resolver.resolve("${steps.s1.output}", outputs)
        assert json.loads(result) == {"a": 1}

    def test_output_returns_stdout_when_not_json(self):
        outputs = {"s1": _output("raw text")}
        assert self.resolver.resolve("${steps.s1.output}", outputs) == "raw text"

    def test_output_field_access(self):
        outputs = {"fetch": _json_output({"name": "alpha", "count": 3})}
        assert self.resolver.resolve("${steps.fetch.output.name}", outputs) == "alpha"

    def test_output_integer_field_coerced_to_string(self):
        outputs = {"fetch": _json_output({"count": 42})}
        assert self.resolver.resolve("${steps.fetch.output.count}", outputs) == "42"


# ---------------------------------------------------------------------------
# VariableResolver — nested access and array indexing
# ---------------------------------------------------------------------------


class TestVariableResolverNested:
    def setup_method(self):
        self.resolver = VariableResolver()
        self.outputs = {
            "fetch_data": _json_output(
                {
                    "items": [
                        {"name": "alpha", "score": 10},
                        {"name": "beta", "score": 20},
                    ]
                }
            )
        }

    def test_array_first_element(self):
        result = self.resolver.resolve("${steps.fetch_data.output.items[0].name}", self.outputs)
        assert result == "alpha"

    def test_array_second_element(self):
        result = self.resolver.resolve("${steps.fetch_data.output.items[1].score}", self.outputs)
        assert result == "20"

    def test_deeply_nested_path(self):
        outputs = {"s": _json_output({"a": {"b": {"c": "deep"}}})}
        assert self.resolver.resolve("${steps.s.output.a.b.c}", outputs) == "deep"

    def test_nested_array_sub_object(self):
        outputs = {"s": _json_output({"results": [{"data": {"value": 99}}]})}
        result = self.resolver.resolve("${steps.s.output.results[0].data.value}", outputs)
        assert result == "99"


# ---------------------------------------------------------------------------
# VariableResolver — multiple tokens in one string
# ---------------------------------------------------------------------------


class TestVariableResolverMultipleTokens:
    def setup_method(self):
        self.resolver = VariableResolver()

    def test_two_tokens_in_one_string(self):
        outputs = {
            "s1": StepOutput(status=TaskStatus.COMPLETED.value, stdout=""),
            "s2": _json_output({"msg": "hello"}),
        }
        result = self.resolver.resolve("${steps.s1.status} — ${steps.s2.output.msg}", outputs)
        assert result == "completed — hello"

    def test_three_tokens(self):
        outputs = {
            "a": _json_output({"x": 1}),
            "b": _json_output({"x": 2}),
            "c": _json_output({"x": 3}),
        }
        result = self.resolver.resolve("${steps.a.output.x},${steps.b.output.x},${steps.c.output.x}", outputs)
        assert result == "1,2,3"


# ---------------------------------------------------------------------------
# VariableResolver — missing / unresolvable references
# ---------------------------------------------------------------------------


class TestVariableResolverMissingReferences:
    def setup_method(self):
        self.resolver = VariableResolver()

    def test_unknown_step_leaves_token_unchanged(self):
        template = "${steps.missing_step.output}"
        assert self.resolver.resolve(template, {}) == template

    def test_missing_field_leaves_token_unchanged(self):
        outputs = {"s1": _json_output({"existing": "yes"})}
        template = "${steps.s1.output.nonexistent}"
        assert self.resolver.resolve(template, outputs) == template

    def test_array_out_of_range_leaves_token_unchanged(self):
        outputs = {"s1": _json_output({"items": ["only_one"]})}
        template = "${steps.s1.output.items[5]}"
        assert self.resolver.resolve(template, outputs) == template

    def test_path_on_non_json_stdout_leaves_token_unchanged(self):
        outputs = {"s1": _output("not json")}
        template = "${steps.s1.output.some_field}"
        assert self.resolver.resolve(template, outputs) == template

    def test_partial_resolution_when_one_token_valid(self):
        """When one of two tokens is unresolvable, the valid one is resolved."""
        outputs = {"good": StepOutput(status="ok", stdout="")}
        template = "${steps.good.status} and ${steps.bad.status}"
        result = self.resolver.resolve(template, outputs)
        assert result == "ok and ${steps.bad.status}"

    def test_unrecognised_accessor_leaves_token_unchanged(self):
        outputs = {"s1": _output("x")}
        template = "${steps.s1.unknown_accessor}"
        assert self.resolver.resolve(template, outputs) == template


# ---------------------------------------------------------------------------
# VariableResolver — metadata accessor
# ---------------------------------------------------------------------------


class TestVariableResolverMetadata:
    def setup_method(self):
        self.resolver = VariableResolver()

    def test_metadata_field_access(self):
        outputs = {
            "s1": StepOutput(
                status=TaskStatus.COMPLETED.value,
                stdout="",
                metadata={"exit_code": 0, "execution_time": 2.5},
            )
        }
        assert self.resolver.resolve("${steps.s1.metadata.exit_code}", outputs) == "0"


# ---------------------------------------------------------------------------
# Module-level convenience: resolve_variables
# ---------------------------------------------------------------------------


class TestResolveVariablesConvenience:
    def test_delegates_to_resolver(self):
        outputs = {"s": StepOutput(status="done", stdout="")}
        result = resolve_variables("status=${steps.s.status}", outputs)
        assert result == "status=done"
