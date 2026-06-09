# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow Input/Output Forms and Formatting (Issue #2161)

Provides:
- FieldType enum: typed field definitions for workflow input forms
- InputFieldSchema: schema for a single user-supplied input field
- WorkflowInputSchema: collection of fields with bulk validation
- OutputTemplate: named template for rendering execution results
- WorkflowOutputFormatter: renders execution_context into JSON/CSV/Markdown/HTML

Usage:
    from services.workflow_io import (
        FieldType,
        InputFieldSchema,
        WorkflowInputSchema,
        OutputTemplate,
        WorkflowOutputFormatter,
    )

    schema = WorkflowInputSchema(fields=[
        InputFieldSchema(name="target_host", field_type=FieldType.IP_ADDRESS, required=True),
        InputFieldSchema(name="port", field_type=FieldType.INTEGER, default=22),
    ])

    validated, errors = schema.validate({"target_host": "192.168.1.1"})

    formatter = WorkflowOutputFormatter()
    md_report = formatter.to_markdown(execution_context)
"""

import csv
import io
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Field type enumeration
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"^https?://" r"(?:[a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,}" r"(?::\d+)?" r"(?:/[^\s]*)?$")

_IPV4_RE = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}" r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$")

_IPV6_RE = re.compile(r"^[0-9a-fA-F:]+$")


class FieldType(Enum):
    """Supported input field types for workflow forms."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    SELECT = "select"
    IP_ADDRESS = "ip_address"
    URL = "url"
    JSON = "json"


# ---------------------------------------------------------------------------
# Input field schema
# ---------------------------------------------------------------------------


@dataclass
class InputFieldSchema:
    """
    Schema definition for a single workflow input field.

    Args:
        name:        Unique field identifier (used as the dict key in inputs).
        field_type:  One of the FieldType enum values.
        required:    When True, the field must be present and non-empty.
        default:     Default value applied when the field is absent.
        description: Human-readable description shown in the form.
        min_value:   Minimum numeric value (applies to INTEGER / FLOAT).
        max_value:   Maximum numeric value (applies to INTEGER / FLOAT).
        min_length:  Minimum string length (applies to STRING / URL / IP_ADDRESS).
        max_length:  Maximum string length (applies to STRING / URL / IP_ADDRESS).
        pattern:     Regex pattern the value must match (applies to STRING).
        options:     Allowed values for SELECT fields.
    """

    name: str
    field_type: FieldType = FieldType.STRING
    required: bool = False
    default: Any = None
    description: str = ""
    min_value: float | None = None
    max_value: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    options: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Coercion
    # ------------------------------------------------------------------

    def coerce(self, raw: Any) -> Any:
        """
        Coerce *raw* to the Python type implied by field_type.

        Raises ValueError when coercion fails.
        """
        if raw is None:
            return None
        try:
            return self._coerce_by_type(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Field '{self.name}': cannot coerce {raw!r} to {self.field_type.value}: {exc}") from exc

    def _coerce_by_type(self, raw: Any) -> Any:
        """Dispatch coercion by field_type (helper for coerce)."""
        if self.field_type == FieldType.INTEGER:
            return int(raw)
        if self.field_type == FieldType.FLOAT:
            return float(raw)
        if self.field_type == FieldType.BOOLEAN:
            return _coerce_bool(raw)
        if self.field_type == FieldType.JSON:
            return raw if not isinstance(raw, str) else json.loads(raw)
        return str(raw)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, value: Any) -> List[str]:
        """
        Validate *value* against this field's constraints.

        Returns a list of error strings.  An empty list means the value
        is valid.  Validation runs after coercion.
        """
        errors: List[str] = []

        if value is None:
            if self.required:
                errors.append(f"Field '{self.name}' is required.")
            return errors

        errors.extend(self._validate_by_type(value))
        errors.extend(self._validate_range(value))
        errors.extend(self._validate_length(value))
        errors.extend(self._validate_pattern(value))
        return errors

    def _validate_by_type(self, value: Any) -> List[str]:
        """Type-specific validation rules (helper for validate)."""
        errors: List[str] = []

        if self.field_type == FieldType.SELECT:
            if self.options and value not in self.options:
                errors.append(f"Field '{self.name}': '{value}' is not one of {self.options}.")

        elif self.field_type == FieldType.IP_ADDRESS:
            if not _is_valid_ip(str(value)):
                errors.append(f"Field '{self.name}': '{value}' is not a valid IP address.")

        elif self.field_type == FieldType.URL:
            if not _URL_RE.match(str(value)):
                errors.append(f"Field '{self.name}': '{value}' is not a valid URL.")

        elif self.field_type == FieldType.JSON:
            errors.extend(self._validate_json(value))

        return errors

    def _validate_json(self, value: Any) -> List[str]:
        """Verify that string values can be parsed as JSON (helper for _validate_by_type)."""
        if not isinstance(value, str):
            return []
        try:
            json.loads(value)
        except json.JSONDecodeError as exc:
            return [f"Field '{self.name}': invalid JSON — {exc}."]
        return []

    def _validate_range(self, value: Any) -> List[str]:
        """Validate numeric min/max constraints (helper for validate)."""
        errors: List[str] = []
        if self.field_type not in (FieldType.INTEGER, FieldType.FLOAT):
            return errors
        if self.min_value is not None and value < self.min_value:
            errors.append(f"Field '{self.name}': {value} is below minimum {self.min_value}.")
        if self.max_value is not None and value > self.max_value:
            errors.append(f"Field '{self.name}': {value} exceeds maximum {self.max_value}.")
        return errors

    def _validate_length(self, value: Any) -> List[str]:
        """Validate string length constraints (helper for validate)."""
        errors: List[str] = []
        if self.field_type not in (
            FieldType.STRING,
            FieldType.URL,
            FieldType.IP_ADDRESS,
        ):
            return errors
        str_value = str(value)
        if self.min_length is not None and len(str_value) < self.min_length:
            errors.append(f"Field '{self.name}': length {len(str_value)} is below minimum {self.min_length}.")
        if self.max_length is not None and len(str_value) > self.max_length:
            errors.append(f"Field '{self.name}': length {len(str_value)} exceeds maximum {self.max_length}.")
        return errors

    def _validate_pattern(self, value: Any) -> List[str]:
        """Validate regex pattern constraint (helper for validate)."""
        if self.field_type != FieldType.STRING or not self.pattern:
            return []
        if not re.match(self.pattern, str(value)):
            return [f"Field '{self.name}': '{value}' does not match pattern '{self.pattern}'."]
        return []

    # ------------------------------------------------------------------
    # JSON Schema generation
    # ------------------------------------------------------------------

    def to_json_schema(self) -> Dict[str, Any]:
        """
        Generate a JSON Schema dict for this field.

        The returned dict is suitable for frontend form generation.  SELECT
        fields emit an ``enum`` constraint; numeric fields include ``minimum``
        and ``maximum`` when set.
        """
        schema: Dict[str, Any] = {
            "title": self.name,
            "description": self.description,
        }
        _apply_json_schema_type(self.field_type, self.options, schema)
        _apply_json_schema_constraints(self, schema)
        if self.default is not None:
            schema["default"] = self.default
        return schema


# ---------------------------------------------------------------------------
# Workflow input schema (collection of fields)
# ---------------------------------------------------------------------------


@dataclass
class WorkflowInputSchema:
    """
    Ordered collection of InputFieldSchema definitions for a workflow.

    Call ``validate(input_data)`` to coerce and validate a raw input dict.

    Args:
        fields: Ordered list of InputFieldSchema objects.
    """

    fields: List[InputFieldSchema] = field(default_factory=list)

    def validate(self, input_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """
        Coerce and validate *input_data* against all declared fields.

        Missing optional fields are filled with their ``default`` value.
        Returns ``(validated_dict, errors)``.  When errors is non-empty the
        validated_dict should not be used.

        Args:
            input_data: Raw user-supplied key/value pairs.

        Returns:
            Tuple of (coerced and validated dict, list of error strings).
        """
        validated: Dict[str, Any] = {}
        errors: List[str] = []

        for f in self.fields:
            raw = input_data.get(f.name, f.default)
            field_errors, coerced = self._coerce_field(f, raw)
            errors.extend(field_errors)
            if not field_errors:
                validation_errors = f.validate(coerced)
                errors.extend(validation_errors)
                if not validation_errors:
                    validated[f.name] = coerced

        return validated, errors

    @staticmethod
    def _coerce_field(f: InputFieldSchema, raw: Any) -> Tuple[List[str], Any]:
        """
        Attempt to coerce *raw* for field *f*.

        Returns ``(errors, coerced_value)``.  On coercion failure,
        errors is non-empty and coerced_value is None.
        """
        try:
            return [], f.coerce(raw)
        except ValueError as exc:
            return [str(exc)], None

    def to_json_schema(self) -> Dict[str, Any]:
        """
        Return a JSON Schema object describing the entire input payload.

        Suitable for rendering an HTML form or validating payloads in
        other language runtimes.
        """
        required_fields = [f.name for f in self.fields if f.required]
        properties = {f.name: f.to_json_schema() for f in self.fields}
        schema: Dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required_fields:
            schema["required"] = required_fields
        return schema


# ---------------------------------------------------------------------------
# Output template
# ---------------------------------------------------------------------------

_VALID_OUTPUT_FORMATS = frozenset({"json", "csv", "markdown", "html"})


@dataclass
class OutputTemplate:
    """
    Named template for rendering workflow execution results.

    Args:
        name:            Template identifier.
        format:          One of ``json``, ``csv``, ``markdown``, ``html``.
        template_string: Optional Jinja2-style template (reserved for future
                         use).  When empty the formatter uses its built-in
                         default renderer for the chosen format.
    """

    name: str
    format: str = "json"
    template_string: str = ""

    def __post_init__(self) -> None:
        """Raise ValueError for unsupported format values."""
        if self.format not in _VALID_OUTPUT_FORMATS:
            raise ValueError(
                f"OutputTemplate '{self.name}': unsupported format '{self.format}'. "
                f"Supported: {sorted(_VALID_OUTPUT_FORMATS)}"
            )


# ---------------------------------------------------------------------------
# Workflow output formatter
# ---------------------------------------------------------------------------


class WorkflowOutputFormatter:
    """
    Render a workflow execution_context dict into various output formats.

    The execution_context shape is the dict returned by
    ``WorkflowExecutor.execute_coordinated_workflow``.  All methods are
    pure functions — they do not mutate the context.
    """

    def format_results(
        self,
        execution_context: Dict[str, Any],
        template: OutputTemplate,
    ) -> str:
        """
        Render *execution_context* using *template*.

        Dispatches to to_json / to_csv / to_markdown / to_html based on
        ``template.format``.

        Args:
            execution_context: Workflow execution result dict.
            template:          OutputTemplate specifying format.

        Returns:
            Formatted string.
        """
        fmt = template.format
        dispatch = {
            "json": self.to_json,
            "csv": self.to_csv,
            "markdown": self.to_markdown,
            "html": self.to_html,
        }
        renderer = dispatch.get(fmt)
        if renderer is None:
            logger.warning("Unknown output format '%s'; falling back to json", fmt)
            renderer = self.to_json

        logger.debug(
            "Formatting workflow %s results as %s",
            execution_context.get("workflow_id", "<unknown>"),
            fmt,
        )
        return renderer(execution_context)

    # ------------------------------------------------------------------
    # Format renderers
    # ------------------------------------------------------------------

    def to_json(self, execution_context: Dict[str, Any]) -> str:
        """
        Serialize execution_context to a pretty-printed JSON string.

        Non-serialisable values (sets, custom objects) are converted to
        their repr() so the export never raises.

        Args:
            execution_context: Workflow execution result dict.

        Returns:
            JSON string.
        """
        safe_ctx = _make_json_safe(execution_context)
        return json.dumps(safe_ctx, indent=2, ensure_ascii=False)

    def to_csv(self, execution_context: Dict[str, Any]) -> str:
        """
        Render step results as a CSV table.

        Columns: ``step_id``, ``success``, ``agent_id``, ``execution_time``,
        ``error`` (empty when step succeeded).

        Args:
            execution_context: Workflow execution result dict.

        Returns:
            CSV string (with header row).
        """
        step_results: Dict[str, Any] = execution_context.get("step_results", {})
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["step_id", "success", "agent_id", "execution_time", "error"],
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()

        for step_id, result in step_results.items():
            writer.writerow(
                {
                    "step_id": step_id,
                    "success": result.get("success", ""),
                    "agent_id": result.get("agent_id", ""),
                    "execution_time": result.get("execution_time", ""),
                    "error": result.get("error", ""),
                }
            )

        return output.getvalue()

    def to_markdown(self, execution_context: Dict[str, Any]) -> str:
        """
        Render a human-readable Markdown report of the workflow execution.

        Args:
            execution_context: Workflow execution result dict.

        Returns:
            Markdown string.
        """
        lines: List[str] = []
        _md_header(execution_context, lines)
        _md_summary_table(execution_context, lines)
        _md_step_results(execution_context, lines)
        return "\n".join(lines)

    def to_html(self, execution_context: Dict[str, Any]) -> str:
        """
        Render a minimal HTML report of the workflow execution.

        The output is a self-contained ``<article>`` fragment (no ``<html>``
        wrapper) so it can be embedded in existing pages.

        Args:
            execution_context: Workflow execution result dict.

        Returns:
            HTML string.
        """
        workflow_id = execution_context.get("workflow_id", "unknown")
        status = execution_context.get("status", "unknown")
        success_rate = execution_context.get("success_rate", 0.0)
        step_results: Dict[str, Any] = execution_context.get("step_results", {})

        rows = "\n".join(_html_step_row(step_id, result) for step_id, result in step_results.items())

        return (
            f"<article>\n"
            f"<h1>Workflow Report: {_esc(workflow_id)}</h1>\n"
            f"<p>Status: <strong>{_esc(status)}</strong> "
            f"&mdash; success rate: {success_rate:.0%}</p>\n"
            f"<table>\n"
            f"<thead><tr>"
            f"<th>Step</th><th>Success</th><th>Agent</th><th>Error</th>"
            f"</tr></thead>\n"
            f"<tbody>\n{rows}\n</tbody>\n"
            f"</table>\n"
            f"</article>"
        )


# ---------------------------------------------------------------------------
# Private helpers — coercion
# ---------------------------------------------------------------------------


def _coerce_bool(raw: Any) -> bool:
    """Coerce *raw* to bool; accepts string forms 'true'/'false'/'yes'/'no'/'1'/'0'."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int):
        return bool(raw)
    lowered = str(raw).strip().lower()
    if lowered in ("true", "yes", "1"):
        return True
    if lowered in ("false", "no", "0"):
        return False
    raise ValueError(f"Cannot interpret '{raw}' as boolean.")


# ---------------------------------------------------------------------------
# Private helpers — IP validation
# ---------------------------------------------------------------------------


def _is_valid_ip(value: str) -> bool:
    """Return True when *value* is a valid IPv4 or IPv6 address."""
    return bool(_IPV4_RE.match(value)) or _is_valid_ipv6(value)


def _is_valid_ipv6(value: str) -> bool:
    """Return True when *value* looks like an IPv6 address."""
    if not _IPV6_RE.match(value):
        return False
    parts = value.split(":")
    return 2 <= len(parts) <= 8


# ---------------------------------------------------------------------------
# Private helpers — JSON schema generation
# ---------------------------------------------------------------------------

_FIELD_TYPE_TO_JSON_SCHEMA_TYPE: Dict[FieldType, str] = {
    FieldType.STRING: "string",
    FieldType.INTEGER: "integer",
    FieldType.FLOAT: "number",
    FieldType.BOOLEAN: "boolean",
    FieldType.SELECT: "string",
    FieldType.IP_ADDRESS: "string",
    FieldType.URL: "string",
    FieldType.JSON: "object",
}


def _apply_json_schema_type(
    field_type: FieldType,
    options: List[str],
    schema: Dict[str, Any],
) -> None:
    """Populate ``type`` (and optionally ``enum``) in *schema* (helper for to_json_schema)."""
    schema["type"] = _FIELD_TYPE_TO_JSON_SCHEMA_TYPE.get(field_type, "string")
    if field_type == FieldType.SELECT and options:
        schema["enum"] = list(options)
    if field_type == FieldType.JSON:
        schema["type"] = ["object", "array", "string"]


def _apply_json_schema_constraints(
    f: InputFieldSchema,
    schema: Dict[str, Any],
) -> None:
    """Populate numeric / string constraints in *schema* (helper for to_json_schema)."""
    if f.min_value is not None:
        schema["minimum"] = f.min_value
    if f.max_value is not None:
        schema["maximum"] = f.max_value
    if f.min_length is not None:
        schema["minLength"] = f.min_length
    if f.max_length is not None:
        schema["maxLength"] = f.max_length
    if f.pattern:
        schema["pattern"] = f.pattern


# ---------------------------------------------------------------------------
# Private helpers — JSON serialisation safety
# ---------------------------------------------------------------------------


def _make_json_safe(obj: Any) -> Any:
    """Recursively convert non-serialisable types to their repr() strings."""
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(v) for v in obj]
    if isinstance(obj, set):
        return [_make_json_safe(v) for v in sorted(obj, key=str)]
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return repr(obj)


# ---------------------------------------------------------------------------
# Private helpers — Markdown rendering
# ---------------------------------------------------------------------------


def _md_header(execution_context: Dict[str, Any], lines: List[str]) -> None:
    """Append the report header section to *lines* (helper for to_markdown)."""
    workflow_id = execution_context.get("workflow_id", "unknown")
    status = execution_context.get("status", "unknown")
    success_rate = execution_context.get("success_rate", 0.0)
    agents = execution_context.get("agents_involved", [])

    lines.append(f"# Workflow Report: `{workflow_id}`")
    lines.append("")
    lines.append(f"**Status:** {status}")
    lines.append(f"**Success rate:** {success_rate:.0%}")
    if agents:
        lines.append(f"**Agents involved:** {', '.join(str(a) for a in agents)}")
    lines.append("")


def _md_summary_table(execution_context: Dict[str, Any], lines: List[str]) -> None:
    """Append the summary table to *lines* (helper for to_markdown)."""
    step_results: Dict[str, Any] = execution_context.get("step_results", {})
    if not step_results:
        return

    lines.append("## Summary")
    lines.append("")
    lines.append("| Step | Success | Agent | Time (s) |")
    lines.append("|------|---------|-------|----------|")
    for step_id, result in step_results.items():
        success = "yes" if result.get("success") else "no"
        agent = result.get("agent_id", "—")
        elapsed = result.get("execution_time", "")
        elapsed_str = f"{elapsed:.2f}" if isinstance(elapsed, float) else str(elapsed)
        lines.append(f"| `{step_id}` | {success} | {agent} | {elapsed_str} |")
    lines.append("")


def _md_step_results(execution_context: Dict[str, Any], lines: List[str]) -> None:
    """Append per-step detail sections to *lines* (helper for to_markdown)."""
    step_results: Dict[str, Any] = execution_context.get("step_results", {})
    if not step_results:
        return

    lines.append("## Step Details")
    for step_id, result in step_results.items():
        lines.append("")
        lines.append(f"### Step `{step_id}`")
        if result.get("error"):
            lines.append(f"- **Error:** {result['error']}")
        inner = result.get("result")
        if inner:
            lines.append(f"- **Result:** `{inner}`")


# ---------------------------------------------------------------------------
# Private helpers — HTML rendering
# ---------------------------------------------------------------------------


def _esc(text: str) -> str:
    """Escape HTML special characters."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _html_step_row(step_id: str, result: Dict[str, Any]) -> str:
    """Return an HTML ``<tr>`` for a single step result (helper for to_html)."""
    success = "yes" if result.get("success") else "no"
    agent = _esc(str(result.get("agent_id", "")))
    error = _esc(str(result.get("error", "")))
    return f"<tr>" f"<td>{_esc(step_id)}</td>" f"<td>{success}</td>" f"<td>{agent}</td>" f"<td>{error}</td>" f"</tr>"
