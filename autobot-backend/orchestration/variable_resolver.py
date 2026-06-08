# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Variable Resolver for Structured Step Output Piping

Issue #2141: Implement ${steps.<step_id>.output} variable piping between
workflow steps so later steps can reference results from earlier steps.

Syntax supported
----------------
${steps.<step_id>.output}              — full parsed JSON output (or raw stdout)
${steps.<step_id>.output.<path>}       — nested field access, e.g. output.items[0].name
${steps.<step_id>.status}              — step status string (completed/failed/…)

Path segments support:
- Dotted traversal:  field.subfield
- Array indexing:    field[0]
- Combined:          items[2].name

Missing references are left unreplaced and logged as a warning so downstream
steps can detect them rather than silently operating on empty strings.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from constants.status_enums import TaskStatus

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# StepOutput dataclass
# ---------------------------------------------------------------------------

_UNSET = object()  # sentinel for "no value found during path traversal


@dataclass
class StepOutput:
    """
    Structured result of a single workflow step execution.

    Stored in DAGExecutionContext / execution_context after each step completes
    so subsequent steps can reference values via VariableResolver.

    Attributes:
        status:      Terminal status string — 'completed', 'failed', 'skipped'.
        stdout:      Raw text output produced by the step.
        parsed_json: Parsed JSON object when stdout is valid JSON, else None.
        metadata:    Arbitrary key/value pairs (execution_time, exit_code, …).
    """

    status: str
    stdout: str = ""
    parsed_json: Dict[str, Any] | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_step_result(cls, result: Dict[str, Any]) -> "StepOutput":
        """
        Build a StepOutput from the raw result dict produced by step executors.

        Attempts to parse *stdout* as JSON.  Falls back to None for parsed_json
        when stdout is absent, empty, or not valid JSON.

        Issue #2141.
        """
        stdout = result.get("stdout", "") or ""
        parsed_json: Dict[str, Any] | None = None
        if stdout:
            try:
                parsed_json = json.loads(stdout)
            except (json.JSONDecodeError, ValueError):
                pass

        status = TaskStatus.COMPLETED.value if result.get("success") else TaskStatus.FAILED.value

        metadata = {k: v for k, v in result.items() if k not in ("stdout", "success")}

        return cls(status=status, stdout=stdout, parsed_json=parsed_json, metadata=metadata)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches: ${steps.step_id.output}  or  ${steps.step_id.output.a.b[0]}
#          ${steps.step_id.status}
_VAR_PATTERN = re.compile(r"\$\{steps\.(\w+)\.([^}]+)\}")

# Matches an array-indexed path segment, e.g. "items[2]"
_ARRAY_SEGMENT = re.compile(r"^(\w+)\[(\d+)\]$")


# ---------------------------------------------------------------------------
# VariableResolver
# ---------------------------------------------------------------------------


class VariableResolver:
    """
    Resolves ``${steps.<step_id>.<accessor>}`` references in template strings.

    Usage::

        resolver = VariableResolver()
        outputs: Dict[str, StepOutput] = {
            "fetch_data": StepOutput(
                status="completed",
                stdout='{"items": [{"name": "alpha"}]}',
                parsed_json={"items": [{"name": "alpha"}]},
            )
        }
        result = resolver.resolve("Hello ${steps.fetch_data.output.items[0].name}!", outputs)
        # result == "Hello alpha!"

    When a reference cannot be resolved (unknown step, missing field, etc.),
    the original token is left in place and a warning is logged.  This makes
    resolution failures visible in downstream output rather than silently
    substituting empty strings.

    Issue #2141.
    """

    def resolve(self, template: str, step_outputs: Dict[str, "StepOutput"]) -> str:
        """
        Replace all ``${steps…}`` tokens in *template* with resolved values.

        Args:
            template:     String that may contain zero or more variable tokens.
            step_outputs: Mapping of step_id → StepOutput for completed steps.

        Returns:
            String with all resolvable tokens replaced.  Unresolvable tokens
            are left unchanged.
        """
        if "${steps." not in template:
            return template

        def _replace(match: re.Match) -> str:
            step_id, accessor = match.group(1), match.group(2)
            value = self._resolve_accessor(step_id, accessor, step_outputs, match.group(0))
            if value is _UNSET:
                return match.group(0)
            if isinstance(value, (dict, list)):
                return json.dumps(value)
            return str(value)

        return _VAR_PATTERN.sub(_replace, template)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_accessor(
        self,
        step_id: str,
        accessor: str,
        step_outputs: Dict[str, "StepOutput"],
        original_token: str,
    ) -> Any:
        """
        Resolve a single accessor string against the step outputs registry.

        Accessors:
          - ``status``             → StepOutput.status
          - ``output``             → StepOutput.parsed_json or StepOutput.stdout
          - ``output.<path>``      → nested path into parsed_json
          - ``metadata.<key>``     → StepOutput.metadata[key]

        Returns _UNSET when the reference cannot be satisfied.

        Issue #2141.
        """
        step_output = step_outputs.get(step_id)
        if step_output is None:
            logger.warning(
                "Variable reference %s: step '%s' has no recorded output",
                original_token,
                step_id,
            )
            return _UNSET

        if accessor == "status":
            return step_output.status

        if accessor == "output":
            return self._coerce_output(step_output)

        if accessor.startswith("output."):
            path = accessor[len("output.") :]
            root = step_output.parsed_json
            if root is None:
                logger.warning(
                    "Variable reference %s: step '%s' stdout is not JSON; cannot traverse path '%s'",
                    original_token,
                    step_id,
                    path,
                )
                return _UNSET
            return self._navigate(root, path, original_token)

        if accessor.startswith("metadata."):
            path = accessor[len("metadata.") :]
            return self._navigate(step_output.metadata, path, original_token)

        logger.warning(
            "Variable reference %s: unrecognised accessor '%s' for step '%s'",
            original_token,
            accessor,
            step_id,
        )
        return _UNSET

    @staticmethod
    def _coerce_output(step_output: "StepOutput") -> Any:
        """Return parsed_json when available, otherwise raw stdout."""
        if step_output.parsed_json is not None:
            return step_output.parsed_json
        return step_output.stdout

    def _navigate(self, root: Any, path: str, original_token: str) -> Any:
        """
        Walk a dot-separated path with optional array indexing into *root*.

        Returns _UNSET when any segment is missing or out of range.

        Issue #2141.
        """
        segments = self._split_path(path)
        current = root
        for segment in segments:
            if current is None:
                logger.warning(
                    "Variable reference %s: encountered None while traversing path",
                    original_token,
                )
                return _UNSET
            current = self._step_into(current, segment, original_token)
            if current is _UNSET:
                return _UNSET
        return current

    @staticmethod
    def _split_path(path: str) -> List[str]:
        """
        Split a dotted path into segments, expanding ``field[0]`` notations.

        ``items[0].name`` → ``["items[0]", "name"]``

        Issue #2141.
        """
        return [seg for seg in path.split(".") if seg]

    def _step_into(self, current: Any, segment: str, original_token: str) -> Any:
        """
        Descend one path segment, supporting both dict keys and array indices.

        Returns _UNSET on lookup failures.

        Issue #2141.
        """
        array_match = _ARRAY_SEGMENT.match(segment)
        if array_match:
            return self._step_into_array(current, array_match, original_token)

        if isinstance(current, dict):
            if segment not in current:
                logger.warning(
                    "Variable reference %s: key '%s' not found in object",
                    original_token,
                    segment,
                )
                return _UNSET
            return current[segment]

        logger.warning(
            "Variable reference %s: cannot index '%s' into non-dict type %s",
            original_token,
            segment,
            type(current).__name__,
        )
        return _UNSET

    @staticmethod
    def _step_into_array(
        current: Any,
        array_match: re.Match,
        original_token: str,
    ) -> Any:
        """
        Resolve ``key[index]`` segment against *current*.

        Returns _UNSET when the key is absent or the index is out of range.

        Issue #2141.
        """
        key = array_match.group(1)
        index = int(array_match.group(2))

        if isinstance(current, dict):
            container = current.get(key)
        else:
            container = None

        if container is None:
            logger.warning(
                "Variable reference %s: key '%s' not found for array access",
                original_token,
                key,
            )
            return _UNSET

        if not isinstance(container, (list, tuple)):
            logger.warning(
                "Variable reference %s: '%s' is not a list (got %s)",
                original_token,
                key,
                type(container).__name__,
            )
            return _UNSET

        if index >= len(container):
            logger.warning(
                "Variable reference %s: index %d out of range (length %d)",
                original_token,
                index,
                len(container),
            )
            return _UNSET

        return container[index]


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

#: Shared singleton — stateless, safe to reuse across calls.
_resolver = VariableResolver()


def resolve_variables(template: str, step_outputs: Dict[str, StepOutput]) -> str:
    """
    Module-level convenience wrapper around VariableResolver.resolve().

    Suitable for one-off calls where constructing a VariableResolver instance
    adds unnecessary boilerplate.

    Issue #2141.
    """
    return _resolver.resolve(template, step_outputs)
