# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for workflow_io — input validation, output formatting, schema generation.

Issue #2161.

Covers:
- FieldType coercion and validation for all 8 types
- Required / optional field handling
- SELECT options enforcement
- Numeric range and string length constraints
- Pattern matching
- WorkflowInputSchema.validate() bulk validation
- WorkflowInputSchema.to_json_schema() schema generation
- OutputTemplate format guard
- WorkflowOutputFormatter.to_json / to_csv / to_markdown / to_html
- WorkflowOutputFormatter.format_results dispatch
"""

import json

import pytest

from services.workflow_io import (
    FieldType,
    InputFieldSchema,
    OutputTemplate,
    WorkflowInputSchema,
    WorkflowOutputFormatter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ctx(
    workflow_id: str = "wf-001",
    status: str = "completed",
    success_rate: float = 1.0,
    step_results: dict | None = None,
    agents_involved: list | None = None,
) -> dict:
    return {
        "workflow_id": workflow_id,
        "status": status,
        "success_rate": success_rate,
        "step_results": step_results
        or {
            "step_1": {"success": True, "agent_id": "agent-a", "execution_time": 1.25},
            "step_2": {
                "success": False,
                "agent_id": "agent-b",
                "error": "timeout",
                "execution_time": 5.0,
            },
        },
        "agents_involved": agents_involved or ["agent-a", "agent-b"],
    }


# ---------------------------------------------------------------------------
# InputFieldSchema — coercion
# ---------------------------------------------------------------------------


class TestCoercion:
    def test_string_passthrough(self) -> None:
        f = InputFieldSchema(name="x", field_type=FieldType.STRING)
        assert f.coerce("hello") == "hello"

    def test_integer_from_string(self) -> None:
        f = InputFieldSchema(name="x", field_type=FieldType.INTEGER)
        assert f.coerce("42") == 42

    def test_float_from_string(self) -> None:
        f = InputFieldSchema(name="x", field_type=FieldType.FLOAT)
        assert abs(f.coerce("3.14") - 3.14) < 1e-9

    def test_boolean_true_variants(self) -> None:
        f = InputFieldSchema(name="x", field_type=FieldType.BOOLEAN)
        for v in ("true", "True", "yes", "YES", "1"):
            assert f.coerce(v) is True, f"Expected True for {v!r}"

    def test_boolean_false_variants(self) -> None:
        f = InputFieldSchema(name="x", field_type=FieldType.BOOLEAN)
        for v in ("false", "False", "no", "NO", "0"):
            assert f.coerce(v) is False, f"Expected False for {v!r}"

    def test_boolean_native(self) -> None:
        f = InputFieldSchema(name="x", field_type=FieldType.BOOLEAN)
        assert f.coerce(True) is True
        assert f.coerce(False) is False

    def test_boolean_invalid_raises(self) -> None:
        f = InputFieldSchema(name="x", field_type=FieldType.BOOLEAN)
        with pytest.raises(ValueError, match="boolean"):
            f.coerce("maybe")

    def test_select_coerces_to_string(self) -> None:
        f = InputFieldSchema(name="x", field_type=FieldType.SELECT, options=["a", "b"])
        assert f.coerce("a") == "a"

    def test_ip_address_coerces_to_string(self) -> None:
        f = InputFieldSchema(name="x", field_type=FieldType.IP_ADDRESS)
        assert f.coerce("10.0.0.1") == "10.0.0.1"

    def test_url_coerces_to_string(self) -> None:
        f = InputFieldSchema(name="x", field_type=FieldType.URL)
        assert f.coerce("https://example.com") == "https://example.com"

    def test_json_passthrough_dict(self) -> None:
        f = InputFieldSchema(name="x", field_type=FieldType.JSON)
        payload = {"key": "val"}
        assert f.coerce(payload) == payload

    def test_json_parses_string(self) -> None:
        f = InputFieldSchema(name="x", field_type=FieldType.JSON)
        assert f.coerce('{"k": 1}') == {"k": 1}

    def test_integer_bad_value_raises(self) -> None:
        f = InputFieldSchema(name="x", field_type=FieldType.INTEGER)
        with pytest.raises(ValueError, match="integer"):
            f.coerce("not-a-number")

    def test_none_coerces_to_none(self) -> None:
        f = InputFieldSchema(name="x", field_type=FieldType.STRING)
        assert f.coerce(None) is None


# ---------------------------------------------------------------------------
# InputFieldSchema — validation
# ---------------------------------------------------------------------------


class TestValidation:
    # required / optional
    def test_required_field_missing_is_error(self) -> None:
        f = InputFieldSchema(name="host", field_type=FieldType.STRING, required=True)
        errors = f.validate(None)
        assert errors
        assert "required" in errors[0].lower()

    def test_optional_field_none_is_ok(self) -> None:
        f = InputFieldSchema(name="host", field_type=FieldType.STRING, required=False)
        assert f.validate(None) == []

    # SELECT
    def test_select_valid_option(self) -> None:
        f = InputFieldSchema(name="env", field_type=FieldType.SELECT, options=["dev", "prod"])
        assert f.validate("dev") == []

    def test_select_invalid_option(self) -> None:
        f = InputFieldSchema(name="env", field_type=FieldType.SELECT, options=["dev", "prod"])
        errors = f.validate("staging")
        assert errors
        assert "staging" in errors[0]

    def test_select_no_options_accepts_anything(self) -> None:
        f = InputFieldSchema(name="env", field_type=FieldType.SELECT)
        assert f.validate("whatever") == []

    # IP address
    def test_valid_ipv4(self) -> None:
        f = InputFieldSchema(name="ip", field_type=FieldType.IP_ADDRESS)
        assert f.validate("192.168.1.100") == []

    def test_invalid_ipv4(self) -> None:
        f = InputFieldSchema(name="ip", field_type=FieldType.IP_ADDRESS)
        errors = f.validate("999.999.999.999")
        assert errors

    def test_valid_ipv6_loopback(self) -> None:
        f = InputFieldSchema(name="ip", field_type=FieldType.IP_ADDRESS)
        assert f.validate("::1") == []

    # URL
    def test_valid_http_url(self) -> None:
        f = InputFieldSchema(name="endpoint", field_type=FieldType.URL)
        assert f.validate("http://api.example.com/path") == []

    def test_valid_https_url(self) -> None:
        f = InputFieldSchema(name="endpoint", field_type=FieldType.URL)
        assert f.validate("https://example.com") == []

    def test_invalid_url(self) -> None:
        f = InputFieldSchema(name="endpoint", field_type=FieldType.URL)
        errors = f.validate("not-a-url")
        assert errors

    # JSON
    def test_valid_json_string(self) -> None:
        f = InputFieldSchema(name="payload", field_type=FieldType.JSON)
        assert f.validate('{"a": 1}') == []

    def test_invalid_json_string(self) -> None:
        f = InputFieldSchema(name="payload", field_type=FieldType.JSON)
        errors = f.validate("{bad json}")
        assert errors

    def test_json_dict_value_skips_parse(self) -> None:
        f = InputFieldSchema(name="payload", field_type=FieldType.JSON)
        assert f.validate({"a": 1}) == []

    # Numeric range
    def test_integer_below_min(self) -> None:
        f = InputFieldSchema(name="port", field_type=FieldType.INTEGER, min_value=1)
        errors = f.validate(0)
        assert errors
        assert "minimum" in errors[0]

    def test_integer_above_max(self) -> None:
        f = InputFieldSchema(name="port", field_type=FieldType.INTEGER, max_value=65535)
        errors = f.validate(70000)
        assert errors
        assert "maximum" in errors[0]

    def test_float_within_range(self) -> None:
        f = InputFieldSchema(name="ratio", field_type=FieldType.FLOAT, min_value=0.0, max_value=1.0)
        assert f.validate(0.5) == []

    # String length
    def test_string_below_min_length(self) -> None:
        f = InputFieldSchema(name="name", field_type=FieldType.STRING, min_length=3)
        errors = f.validate("ab")
        assert errors
        assert "minimum" in errors[0]

    def test_string_above_max_length(self) -> None:
        f = InputFieldSchema(name="name", field_type=FieldType.STRING, max_length=5)
        errors = f.validate("toolong")
        assert errors
        assert "maximum" in errors[0]

    def test_string_within_length(self) -> None:
        f = InputFieldSchema(name="name", field_type=FieldType.STRING, min_length=2, max_length=10)
        assert f.validate("hello") == []

    # Pattern
    def test_pattern_match(self) -> None:
        f = InputFieldSchema(name="code", field_type=FieldType.STRING, pattern=r"^[A-Z]{3}$")
        assert f.validate("ABC") == []

    def test_pattern_mismatch(self) -> None:
        f = InputFieldSchema(name="code", field_type=FieldType.STRING, pattern=r"^[A-Z]{3}$")
        errors = f.validate("abc")
        assert errors
        assert "pattern" in errors[0]


# ---------------------------------------------------------------------------
# WorkflowInputSchema — bulk validation
# ---------------------------------------------------------------------------


class TestWorkflowInputSchema:
    def _schema(self) -> WorkflowInputSchema:
        return WorkflowInputSchema(
            fields=[
                InputFieldSchema(
                    name="host",
                    field_type=FieldType.IP_ADDRESS,
                    required=True,
                ),
                InputFieldSchema(
                    name="port",
                    field_type=FieldType.INTEGER,
                    default=22,
                    min_value=1,
                    max_value=65535,
                ),
                InputFieldSchema(
                    name="dry_run",
                    field_type=FieldType.BOOLEAN,
                    default=False,
                ),
            ]
        )

    def test_valid_input_returns_coerced_values(self) -> None:
        schema = self._schema()
        validated, errors = schema.validate({"host": "10.0.0.1", "port": "8022"})
        assert errors == []
        assert validated["host"] == "10.0.0.1"
        assert validated["port"] == 8022
        assert validated["dry_run"] is False  # default

    def test_missing_required_field_is_error(self) -> None:
        schema = self._schema()
        _, errors = schema.validate({})
        assert any("host" in e and "required" in e.lower() for e in errors)

    def test_default_applied_when_field_absent(self) -> None:
        schema = self._schema()
        validated, errors = schema.validate({"host": "10.0.0.1"})
        assert errors == []
        assert validated["port"] == 22

    def test_invalid_ip_is_error(self) -> None:
        schema = self._schema()
        _, errors = schema.validate({"host": "not-an-ip"})
        assert errors

    def test_port_out_of_range_is_error(self) -> None:
        schema = self._schema()
        _, errors = schema.validate({"host": "10.0.0.1", "port": "99999"})
        assert errors

    def test_multiple_errors_collected(self) -> None:
        schema = self._schema()
        _, errors = schema.validate({"port": "bad", "dry_run": "maybe"})
        assert len(errors) >= 2

    # JSON schema generation
    def test_to_json_schema_has_required(self) -> None:
        schema = self._schema()
        js = schema.to_json_schema()
        assert "required" in js
        assert "host" in js["required"]

    def test_to_json_schema_properties_present(self) -> None:
        schema = self._schema()
        js = schema.to_json_schema()
        assert "host" in js["properties"]
        assert "port" in js["properties"]

    def test_to_json_schema_no_required_key_when_all_optional(self) -> None:
        schema = WorkflowInputSchema(fields=[InputFieldSchema(name="x", field_type=FieldType.STRING)])
        js = schema.to_json_schema()
        assert "required" not in js


# ---------------------------------------------------------------------------
# InputFieldSchema.to_json_schema
# ---------------------------------------------------------------------------


class TestInputFieldJsonSchema:
    def test_integer_type(self) -> None:
        f = InputFieldSchema(name="port", field_type=FieldType.INTEGER, min_value=1, max_value=65535)
        schema = f.to_json_schema()
        assert schema["type"] == "integer"
        assert schema["minimum"] == 1
        assert schema["maximum"] == 65535

    def test_float_type(self) -> None:
        f = InputFieldSchema(name="ratio", field_type=FieldType.FLOAT)
        assert f.to_json_schema()["type"] == "number"

    def test_boolean_type(self) -> None:
        f = InputFieldSchema(name="flag", field_type=FieldType.BOOLEAN)
        assert f.to_json_schema()["type"] == "boolean"

    def test_select_enum(self) -> None:
        f = InputFieldSchema(name="env", field_type=FieldType.SELECT, options=["dev", "prod"])
        schema = f.to_json_schema()
        assert schema["type"] == "string"
        assert schema["enum"] == ["dev", "prod"]

    def test_ip_address_is_string_type(self) -> None:
        f = InputFieldSchema(name="ip", field_type=FieldType.IP_ADDRESS)
        assert f.to_json_schema()["type"] == "string"

    def test_url_is_string_type(self) -> None:
        f = InputFieldSchema(name="url", field_type=FieldType.URL)
        assert f.to_json_schema()["type"] == "string"

    def test_json_type_is_multi(self) -> None:
        f = InputFieldSchema(name="payload", field_type=FieldType.JSON)
        schema = f.to_json_schema()
        assert isinstance(schema["type"], list)

    def test_string_length_constraints(self) -> None:
        f = InputFieldSchema(name="label", field_type=FieldType.STRING, min_length=2, max_length=50)
        schema = f.to_json_schema()
        assert schema["minLength"] == 2
        assert schema["maxLength"] == 50

    def test_pattern_in_schema(self) -> None:
        f = InputFieldSchema(name="code", field_type=FieldType.STRING, pattern=r"^[A-Z]+$")
        schema = f.to_json_schema()
        assert schema["pattern"] == r"^[A-Z]+$"

    def test_default_in_schema(self) -> None:
        f = InputFieldSchema(name="port", field_type=FieldType.INTEGER, default=22)
        schema = f.to_json_schema()
        assert schema["default"] == 22

    def test_description_in_schema(self) -> None:
        f = InputFieldSchema(name="x", description="My field")
        schema = f.to_json_schema()
        assert schema["description"] == "My field"


# ---------------------------------------------------------------------------
# OutputTemplate
# ---------------------------------------------------------------------------


class TestOutputTemplate:
    def test_valid_formats_accepted(self) -> None:
        for fmt in ("json", "csv", "markdown", "html"):
            tmpl = OutputTemplate(name="t", format=fmt)
            assert tmpl.format == fmt

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported format"):
            OutputTemplate(name="t", format="xml")


# ---------------------------------------------------------------------------
# WorkflowOutputFormatter
# ---------------------------------------------------------------------------


class TestToJson:
    def test_returns_valid_json(self) -> None:
        ctx = _make_ctx()
        result = WorkflowOutputFormatter().to_json(ctx)
        parsed = json.loads(result)
        assert parsed["workflow_id"] == "wf-001"

    def test_contains_step_results(self) -> None:
        ctx = _make_ctx()
        result = WorkflowOutputFormatter().to_json(ctx)
        assert "step_1" in result

    def test_sets_serialised_as_lists(self) -> None:
        ctx = _make_ctx()
        ctx["agents_involved"] = {"agent-a", "agent-b"}
        result = WorkflowOutputFormatter().to_json(ctx)
        parsed = json.loads(result)
        assert isinstance(parsed["agents_involved"], list)

    def test_non_serialisable_becomes_repr(self) -> None:
        ctx = _make_ctx()
        ctx["custom"] = object()
        result = WorkflowOutputFormatter().to_json(ctx)
        parsed = json.loads(result)
        assert isinstance(parsed["custom"], str)


class TestToCsv:
    def test_header_present(self) -> None:
        result = WorkflowOutputFormatter().to_csv(_make_ctx())
        assert result.startswith("step_id,success,agent_id")

    def test_step_rows_present(self) -> None:
        result = WorkflowOutputFormatter().to_csv(_make_ctx())
        assert "step_1" in result
        assert "step_2" in result

    def test_error_column_populated(self) -> None:
        result = WorkflowOutputFormatter().to_csv(_make_ctx())
        assert "timeout" in result

    def test_empty_step_results(self) -> None:
        ctx = _make_ctx(step_results={})
        result = WorkflowOutputFormatter().to_csv(ctx)
        lines = [l for l in result.splitlines() if l]
        assert len(lines) == 1  # header only


class TestToMarkdown:
    def test_has_header(self) -> None:
        result = WorkflowOutputFormatter().to_markdown(_make_ctx())
        assert result.startswith("# Workflow Report")

    def test_status_in_output(self) -> None:
        result = WorkflowOutputFormatter().to_markdown(_make_ctx(status="partially_completed"))
        assert "partially_completed" in result

    def test_success_rate_formatted(self) -> None:
        result = WorkflowOutputFormatter().to_markdown(_make_ctx(success_rate=0.5))
        assert "50%" in result

    def test_step_table_present(self) -> None:
        result = WorkflowOutputFormatter().to_markdown(_make_ctx())
        assert "| Step |" in result

    def test_step_detail_section_present(self) -> None:
        result = WorkflowOutputFormatter().to_markdown(_make_ctx())
        assert "## Step Details" in result

    def test_error_shown_in_details(self) -> None:
        result = WorkflowOutputFormatter().to_markdown(_make_ctx())
        assert "timeout" in result

    def test_agents_listed(self) -> None:
        result = WorkflowOutputFormatter().to_markdown(_make_ctx(agents_involved=["agent-x"]))
        assert "agent-x" in result


class TestToHtml:
    def test_is_article_fragment(self) -> None:
        result = WorkflowOutputFormatter().to_html(_make_ctx())
        assert result.startswith("<article>")
        assert result.strip().endswith("</article>")

    def test_workflow_id_escaped(self) -> None:
        ctx = _make_ctx(workflow_id="<script>")
        result = WorkflowOutputFormatter().to_html(ctx)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_step_rows_present(self) -> None:
        result = WorkflowOutputFormatter().to_html(_make_ctx())
        assert "step_1" in result
        assert "step_2" in result

    def test_error_text_escaped(self) -> None:
        ctx = _make_ctx(step_results={"s1": {"success": False, "error": "<xss>", "agent_id": "a"}})
        result = WorkflowOutputFormatter().to_html(ctx)
        assert "<xss>" not in result
        assert "&lt;xss&gt;" in result


class TestFormatResults:
    def test_dispatches_to_json(self) -> None:
        tmpl = OutputTemplate(name="t", format="json")
        result = WorkflowOutputFormatter().format_results(_make_ctx(), tmpl)
        assert json.loads(result)["workflow_id"] == "wf-001"

    def test_dispatches_to_csv(self) -> None:
        tmpl = OutputTemplate(name="t", format="csv")
        result = WorkflowOutputFormatter().format_results(_make_ctx(), tmpl)
        assert "step_id" in result

    def test_dispatches_to_markdown(self) -> None:
        tmpl = OutputTemplate(name="t", format="markdown")
        result = WorkflowOutputFormatter().format_results(_make_ctx(), tmpl)
        assert result.startswith("# Workflow Report")

    def test_dispatches_to_html(self) -> None:
        tmpl = OutputTemplate(name="t", format="html")
        result = WorkflowOutputFormatter().format_results(_make_ctx(), tmpl)
        assert "<article>" in result
