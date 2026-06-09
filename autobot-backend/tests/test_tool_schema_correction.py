# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for Pydantic schema self-correction retry loop (Issue #4522).

Covers:
- validate_tool_arguments() returns None for valid arguments
- Returns structured error dict for missing required field
- Returns structured error dict for wrong-type argument
- _format_schema_validation_errors() produces human-readable hint string
- _try_mcp_dispatch() returns schema-error WorkflowMessage on bad args
- _try_mcp_dispatch() respects max_schema_retries limit in retries_left
- Bad (invalid) JSON Schemas are handled gracefully (log warning, continue)
"""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
import time
import types
import uuid
from collections import deque
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Minimal stubs required so tool_handler.py can be loaded in isolation.
#
# tool_handler imports at module level:
#   from async_chat_workflow import WorkflowMessage
#   from utils.errors import RepairableException
#   from chat_workflow.llm_handler import _emit_*
#   from chat_workflow.session_handler import _emit_*
#
# We load tool_handler via importlib (bypassing chat_workflow/__init__.py,
# which triggers a metaclass conflict in the test environment) and stub its
# direct imports before executing the module.
# ---------------------------------------------------------------------------

_BACKEND_ROOT = Path(__file__).parent.parent  # autobot-backend/


def _simple_stub(name: str) -> MagicMock:
    """Register a plain MagicMock as *name* if not already present."""
    if name not in sys.modules:
        mod = MagicMock()
        sys.modules[name] = mod
    return sys.modules[name]  # type: ignore[return-value]


def _pkg_stub(name: str) -> types.ModuleType:
    """Register a lightweight package stub (needs __path__ for dotted imports)."""
    if name in sys.modules:
        return sys.modules[name]  # type: ignore[return-value]
    mod = types.ModuleType(name)
    mod.__path__ = []  # type: ignore[attr-defined]
    mod.__package__ = name
    _attr = MagicMock()
    mod.__getattr__ = lambda attr: _attr  # type: ignore[attr-defined]
    sys.modules[name] = mod
    return mod


# Build WorkflowMessage as a real dataclass (not a MagicMock) so tests can
# inspect .type and .metadata attributes.
if "async_chat_workflow" not in sys.modules:

    @dataclasses.dataclass
    class _WM:
        type: str
        content: str
        id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
        timestamp: float = dataclasses.field(default_factory=time.time)
        metadata: dict = dataclasses.field(default_factory=dict)

    _wf_mod = types.ModuleType("async_chat_workflow")
    _wf_mod.WorkflowMessage = _WM  # type: ignore[attr-defined]
    _wf_mod.AsyncChatWorkflow = MagicMock  # type: ignore[attr-defined]
    sys.modules["async_chat_workflow"] = _wf_mod

# utils.errors
_ue = _simple_stub("utils.errors")
_ue.RepairableException = Exception  # type: ignore[attr-defined]

# chat_workflow package stub — must exist before chat_workflow.llm_handler /
# chat_workflow.session_handler sub-stubs are registered.  We use a real
# ModuleType with __path__ so Python treats it as a package.
_cw_pkg = _pkg_stub("chat_workflow")
_cw_pkg.__path__ = [str(_BACKEND_ROOT / "chat_workflow")]  # type: ignore[attr-defined]

# Sub-module stubs for the two imports tool_handler pulls in at module level.
_lh = _simple_stub("chat_workflow.llm_handler")
_lh._emit_before_tool_execute = AsyncMock(return_value=True)  # type: ignore[attr-defined]
_lh._emit_after_tool_execute = AsyncMock(side_effect=lambda t, r, s, m: r)  # type: ignore[attr-defined]
_lh._emit_tool_error = AsyncMock(return_value=None)  # type: ignore[attr-defined]

_sh = _simple_stub("chat_workflow.session_handler")
_sh._emit_approval_received = AsyncMock(return_value=None)  # type: ignore[attr-defined]
_sh._emit_approval_required = AsyncMock(return_value=None)  # type: ignore[attr-defined]

# services.mcp_dispatch is imported lazily (local import) inside
# _try_mcp_dispatch.  Pre-register a stub package + module so patch() can
# resolve "services.mcp_dispatch.get_mcp_dispatcher" correctly.
_svc_pkg = _pkg_stub("services")
_mcp_stub = _simple_stub("services.mcp_dispatch")
_mcp_stub.get_mcp_dispatcher = MagicMock()  # type: ignore[attr-defined]
_svc_pkg.mcp_dispatch = _mcp_stub  # type: ignore[attr-defined]

# Load tool_handler directly from its source file, bypassing __init__.py.
_th_path = _BACKEND_ROOT / "chat_workflow" / "tool_handler.py"
_spec = importlib.util.spec_from_file_location("chat_workflow.tool_handler", str(_th_path))
assert _spec and _spec.loader, f"Could not locate tool_handler at {_th_path}"
_th_mod = importlib.util.module_from_spec(_spec)
_th_mod.__package__ = "chat_workflow"
sys.modules["chat_workflow.tool_handler"] = _th_mod
_spec.loader.exec_module(_th_mod)  # type: ignore[union-attr]

# Expose tool_handler as an attribute of the chat_workflow package stub so
# patch("chat_workflow.tool_handler.X") can resolve the dotted path correctly.
_cw_pkg.tool_handler = _th_mod  # type: ignore[attr-defined]

# Re-export the symbols under test.
_DEFAULT_SCHEMA_RETRIES = _th_mod._DEFAULT_SCHEMA_RETRIES
_format_schema_validation_errors = _th_mod._format_schema_validation_errors
_try_mcp_dispatch = _th_mod._try_mcp_dispatch
validate_tool_arguments = _th_mod.validate_tool_arguments


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_SIMPLE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "limit": {"type": "integer"},
    },
    "required": ["query"],
}


def _fake_validation_error(path: list, message: str):
    """Return a minimal jsonschema.ValidationError-like object."""
    err = MagicMock()
    err.absolute_path = deque(path)
    err.message = message
    return err


# ---------------------------------------------------------------------------
# validate_tool_arguments()
# ---------------------------------------------------------------------------


class TestValidateToolArguments:
    """Tests for validate_tool_arguments()."""

    def test_returns_none_for_valid_arguments(self):
        """Valid arguments matching the schema must return None (no error)."""
        result = validate_tool_arguments("my_tool", {"query": "hello"}, _SIMPLE_SCHEMA)
        assert result is None

    def test_returns_none_for_all_fields_provided(self):
        """All fields provided (including optional) still returns None."""
        result = validate_tool_arguments("my_tool", {"query": "hello", "limit": 10}, _SIMPLE_SCHEMA)
        assert result is None

    def test_returns_error_for_missing_required_field(self):
        """Missing required field must produce a structured error dict."""
        result = validate_tool_arguments("my_tool", {}, _SIMPLE_SCHEMA)

        assert result is not None
        assert result["schema_validation_failed"] is True
        assert result["tool"] == "my_tool"
        assert "error" in result
        assert "Tool argument validation failed" in result["error"]

    def test_returns_error_for_wrong_type(self):
        """Wrong field type must produce a structured error dict."""
        result = validate_tool_arguments("my_tool", {"query": "ok", "limit": "not-an-int"}, _SIMPLE_SCHEMA)

        assert result is not None
        assert result["schema_validation_failed"] is True
        assert "limit" in result["error"]

    def test_invalid_schema_returns_none_gracefully(self):
        """A broken/invalid JSON Schema must not raise — returns None."""
        bad_schema = {"type": "object", "$ref": "#/broken/ref/path"}
        result = validate_tool_arguments("my_tool", {"query": "hi"}, bad_schema)
        assert result is None

    def test_empty_schema_passes_through(self):
        """An empty schema dict has no constraints — returns None."""
        result = validate_tool_arguments("my_tool", {"anything": True}, {})
        assert result is None

    def test_error_dict_contains_tool_name(self):
        """Error dict must include the tool name for downstream context."""
        result = validate_tool_arguments("search_tool", {}, _SIMPLE_SCHEMA)
        assert result is not None
        assert result["tool"] == "search_tool"


# ---------------------------------------------------------------------------
# _format_schema_validation_errors()
# ---------------------------------------------------------------------------


class TestFormatSchemaValidationErrors:
    """Tests for _format_schema_validation_errors()."""

    def test_single_field_error_formatted(self):
        """Single field-level error should appear with field path and message."""
        errors = [_fake_validation_error(["query"], "'query' is a required property")]
        result = _format_schema_validation_errors(errors)

        assert "Tool argument validation failed:" in result
        assert "query" in result
        assert "'query' is a required property" in result

    def test_root_level_error_uses_root_label(self):
        """Errors with no path should show '<root>' as the field label."""
        errors = [_fake_validation_error([], "value is not of type 'object'")]
        result = _format_schema_validation_errors(errors)

        assert "<root>" in result

    def test_multiple_errors_all_present(self):
        """All errors in the list must appear in the output."""
        errors = [
            _fake_validation_error(["field_a"], "error in field_a"),
            _fake_validation_error(["field_b"], "error in field_b"),
        ]
        result = _format_schema_validation_errors(errors)

        assert "field_a" in result
        assert "field_b" in result
        assert "error in field_a" in result
        assert "error in field_b" in result

    def test_nested_path_joined_with_dots(self):
        """Nested paths must be joined with '.' separators."""
        errors = [_fake_validation_error(["props", "nested", "key"], "bad value")]
        result = _format_schema_validation_errors(errors)

        assert "props.nested.key" in result

    def test_output_starts_with_header(self):
        """Output always starts with 'Tool argument validation failed:'."""
        errors = [_fake_validation_error(["x"], "some error")]
        result = _format_schema_validation_errors(errors)
        assert result.startswith("Tool argument validation failed:")


# ---------------------------------------------------------------------------
# _try_mcp_dispatch() — schema self-correction retry behaviour
# ---------------------------------------------------------------------------

_TH_MODULE = "chat_workflow.tool_handler"
# get_mcp_dispatcher is imported lazily inside _try_mcp_dispatch, so we must
# patch it on the services.mcp_dispatch module rather than on tool_handler.
_MCP_DISPATCH_MODULE = "services.mcp_dispatch"


class TestTryMcpDispatchSchemaRetry:
    """Tests for the schema retry loop inside _try_mcp_dispatch()."""

    def _make_dispatcher(self, tool_name: str, schema: dict):
        """Return a mock MCP dispatcher with a single registered tool."""
        tool_meta = {"name": tool_name, "input_schema": schema}
        dispatcher = MagicMock()
        dispatcher._cache_loaded = True
        dispatcher.find_tool = MagicMock(return_value=tool_meta)
        dispatcher.dispatch = AsyncMock(return_value={"success": True, "result": "ok", "bridge": "test"})
        return dispatcher

    @pytest.mark.asyncio
    async def test_valid_args_dispatches_successfully(self):
        """Valid arguments skip the schema-error path and dispatch normally."""
        dispatcher = self._make_dispatcher("search", _SIMPLE_SCHEMA)

        with (
            patch(f"{_MCP_DISPATCH_MODULE}.get_mcp_dispatcher", return_value=dispatcher),
            patch(
                f"{_TH_MODULE}._emit_before_tool_execute",
                new=AsyncMock(return_value=True),
            ),
            patch(
                f"{_TH_MODULE}._emit_after_tool_execute",
                new=AsyncMock(side_effect=lambda t, r, s, m: r),
            ),
        ):
            tool_call = {"name": "search", "arguments": {"query": "hello"}}
            result = await _try_mcp_dispatch("search", tool_call, [])

        assert result is not None
        assert result.type == "tool_result"
        dispatcher.dispatch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_args_returns_schema_error_message(self):
        """Invalid arguments return a WorkflowMessage with schema_validation_failed=True."""
        dispatcher = self._make_dispatcher("search", _SIMPLE_SCHEMA)

        with patch(f"{_MCP_DISPATCH_MODULE}.get_mcp_dispatcher", return_value=dispatcher):
            tool_call = {"name": "search", "arguments": {}}  # missing "query"
            execution_results: list = []
            result = await _try_mcp_dispatch("search", tool_call, execution_results)

        assert result is not None
        assert result.metadata.get("schema_validation_failed") is True
        assert "self_correction_hint" in result.metadata
        dispatcher.dispatch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_retries_left_decrements_per_retry_count(self):
        """retries_left should equal max_schema_retries minus _schema_retry_count."""
        dispatcher = self._make_dispatcher("search", _SIMPLE_SCHEMA)

        with patch(f"{_MCP_DISPATCH_MODULE}.get_mcp_dispatcher", return_value=dispatcher):
            tool_call = {
                "name": "search",
                "arguments": {},
                "_schema_retry_count": 1,  # second attempt
            }
            result = await _try_mcp_dispatch("search", tool_call, [], max_schema_retries=3)

        assert result is not None
        assert result.metadata["retries_left"] == 2  # 3 - 1

    @pytest.mark.asyncio
    async def test_max_retries_exhausted_retries_left_zero(self):
        """When _schema_retry_count equals max_schema_retries, retries_left is 0."""
        dispatcher = self._make_dispatcher("search", _SIMPLE_SCHEMA)

        with patch(f"{_MCP_DISPATCH_MODULE}.get_mcp_dispatcher", return_value=dispatcher):
            tool_call = {
                "name": "search",
                "arguments": {},
                "_schema_retry_count": 3,
            }
            result = await _try_mcp_dispatch("search", tool_call, [], max_schema_retries=3)

        assert result is not None
        assert result.metadata["retries_left"] == 0

    @pytest.mark.asyncio
    async def test_self_correction_hint_mentions_tool_name(self):
        """self_correction_hint must reference the tool name."""
        dispatcher = self._make_dispatcher("my_tool", _SIMPLE_SCHEMA)

        with patch(f"{_MCP_DISPATCH_MODULE}.get_mcp_dispatcher", return_value=dispatcher):
            tool_call = {"name": "my_tool", "arguments": {}}
            result = await _try_mcp_dispatch("my_tool", tool_call, [])

        assert result is not None
        hint = result.metadata.get("self_correction_hint", "")
        assert "my_tool" in hint

    @pytest.mark.asyncio
    async def test_schema_error_appended_to_execution_results(self):
        """A schema-validation failure must be recorded in execution_results."""
        dispatcher = self._make_dispatcher("search", _SIMPLE_SCHEMA)

        with patch(f"{_MCP_DISPATCH_MODULE}.get_mcp_dispatcher", return_value=dispatcher):
            tool_call = {"name": "search", "arguments": {}}
            execution_results: list = []
            await _try_mcp_dispatch("search", tool_call, execution_results)

        assert len(execution_results) == 1
        entry = execution_results[0]
        assert entry["status"] == "schema_error"
        assert entry["schema_validation_failed"] is True
        assert entry["tool"] == "search"

    @pytest.mark.asyncio
    async def test_tool_not_found_returns_none(self):
        """Unknown tool (not in registry) must return None, not raise."""
        dispatcher = MagicMock()
        dispatcher._cache_loaded = True
        dispatcher.find_tool = MagicMock(return_value=None)

        with patch(f"{_MCP_DISPATCH_MODULE}.get_mcp_dispatcher", return_value=dispatcher):
            result = await _try_mcp_dispatch("unknown_tool", {"arguments": {}}, [])

        assert result is None

    @pytest.mark.asyncio
    async def test_tool_without_input_schema_skips_validation(self):
        """Tools registered without an input_schema bypass validation entirely."""
        tool_meta = {"name": "no_schema_tool"}  # no "input_schema" key
        dispatcher = MagicMock()
        dispatcher._cache_loaded = True
        dispatcher.find_tool = MagicMock(return_value=tool_meta)
        dispatcher.dispatch = AsyncMock(return_value={"success": True, "result": "ok", "bridge": "b"})

        with (
            patch(f"{_MCP_DISPATCH_MODULE}.get_mcp_dispatcher", return_value=dispatcher),
            patch(
                f"{_TH_MODULE}._emit_before_tool_execute",
                new=AsyncMock(return_value=True),
            ),
            patch(
                f"{_TH_MODULE}._emit_after_tool_execute",
                new=AsyncMock(side_effect=lambda t, r, s, m: r),
            ),
        ):
            result = await _try_mcp_dispatch("no_schema_tool", {"arguments": {}}, [])

        assert result is not None
        dispatcher.dispatch.assert_awaited_once()

    def test_default_schema_retries_constant(self):
        """_DEFAULT_SCHEMA_RETRIES must equal 3 as specified in #4482."""
        assert _DEFAULT_SCHEMA_RETRIES == 3
