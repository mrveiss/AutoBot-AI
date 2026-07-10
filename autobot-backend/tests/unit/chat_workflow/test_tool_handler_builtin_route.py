# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Uniform builtin routing table at the dispatch seam (GH#11489).

``_dispatch_tool_call`` runs one shared gate (invalid-call counter reset →
Issue #4529 schema validation) for every tool in ``_UNIFORM_BUILTIN_TOOLS``,
then delegates via ``_builtin_route``. These tests pin behavior parity with
the four hand-written branches the table replaced (browser #1368, web_search
#2306, web research #7509, execute_command).
"""

from types import SimpleNamespace

import pytest

from chat_workflow.tool_handler import (
    _BUILTIN_TOOL_SCHEMAS,
    _UNIFORM_BUILTIN_TOOLS,
    BROWSER_TOOL_NAMES,
    WEB_RESEARCH_TOOL_NAMES,
    ToolHandlerMixin,
)

_DISPATCH_ARGS = {
    "session_id": "sess-1",
    "terminal_session_id": "term-1",
    "ollama_endpoint": "http://127.0.0.1:11434",
    "selected_model": "test-model",
}


def _mixin() -> ToolHandlerMixin:
    mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)
    # Governance gates are covered by their own suites (GH#11145/11160/11177/11178);
    # quiet them here so routing is exercised in isolation.
    mixin._enforce_forbidden_work = lambda *a, **k: None
    mixin._enforce_config_protection = lambda *a, **k: None
    mixin._enforce_fact_forcing = lambda *a, **k: None
    mixin._enforce_work_item_approval = lambda *a, **k: None
    return mixin


def _recording_handler(calls: list, label: str):
    def factory(*args, **kwargs):
        # Record at call time (async-generator bodies only run when drained).
        calls.append((label, args))

        async def gen():
            yield f"{label}-msg"

        return gen()

    return factory


async def _dispatch(mixin: ToolHandlerMixin, tool_call: dict, execution_results: list) -> list:
    return [
        msg
        async for msg in mixin._dispatch_tool_call(
            tool_call,
            execution_results=execution_results,
            additional_response_parts=[],
            **_DISPATCH_ARGS,
        )
    ]


def test_uniform_set_is_union_of_builtin_families() -> None:
    """Membership SSOT: browser + web research + web_search + execute_command."""
    assert _UNIFORM_BUILTIN_TOOLS == (
        BROWSER_TOOL_NAMES | WEB_RESEARCH_TOOL_NAMES | {"web_search", "execute_command"}
    )
    # respond/delegate are non-uniform (special return shapes) and must stay out.
    assert "respond" not in _UNIFORM_BUILTIN_TOOLS
    assert "delegate" not in _UNIFORM_BUILTIN_TOOLS


def test_every_uniform_tool_has_a_schema() -> None:
    """A schema-less member would silently skip Issue #4529 validation."""
    missing = _UNIFORM_BUILTIN_TOOLS - set(_BUILTIN_TOOL_SCHEMAS)
    assert not missing, f"uniform builtins without schemas: {sorted(missing)}"


_ROUTE_EXPECTATIONS = [
    *[(name, "_handle_browser_tool") for name in sorted(BROWSER_TOOL_NAMES)],
    *[(name, "_handle_web_research_tool") for name in sorted(WEB_RESEARCH_TOOL_NAMES)],
    ("web_search", "_handle_web_search_tool"),
    ("execute_command", "_dispatch_execute_command"),
]


@pytest.mark.parametrize("tool_name,handler_attr", _ROUTE_EXPECTATIONS)
def test_route_table_covers_every_member(tool_name: str, handler_attr: str) -> None:
    """Every union member maps to its family handler — no silent fallback."""
    mixin, calls = _mixin(), []
    setattr(mixin, handler_attr, _recording_handler(calls, handler_attr))

    generator = mixin._builtin_route(
        tool_name, {"name": tool_name, "params": {}}, "sess-1", "term-1", "ep", "model", [], []
    )

    assert generator is not None
    (label, _args), = calls  # handler factory invoked exactly once
    assert label == handler_attr


def test_builtin_route_raises_on_unrouted_member() -> None:
    """Defensive tail: an unrouted name fails loudly, never execute_command."""
    mixin = _mixin()
    with pytest.raises(ValueError, match="no route for 'not_a_builtin'"):
        mixin._builtin_route("not_a_builtin", {"name": "not_a_builtin"}, "s", "t", "e", "m", [], [])


@pytest.mark.asyncio
async def test_uniform_gate_resets_invalid_call_counter() -> None:
    """The shared gate resets ctx.consecutive_invalid_tool_calls — parity with
    the four replaced branches."""
    mixin, calls = _mixin(), []
    mixin._handle_web_search_tool = _recording_handler(calls, "web_search")
    ctx = SimpleNamespace(consecutive_invalid_tool_calls=2)

    messages = [
        msg
        async for msg in mixin._dispatch_tool_call(
            {"name": "web_search", "params": {"query": "q"}},
            execution_results=[],
            additional_response_parts=[],
            ctx=ctx,
            **_DISPATCH_ARGS,
        )
    ]

    assert messages == ["web_search-msg"]
    assert ctx.consecutive_invalid_tool_calls == 0


@pytest.mark.asyncio
async def test_browser_tool_routes_to_browser_handler() -> None:
    mixin, calls = _mixin(), []
    mixin._handle_browser_tool = _recording_handler(calls, "browser")

    messages = await _dispatch(mixin, {"name": "click", "params": {"selector": "#go"}}, [])

    assert messages == ["browser-msg"]
    (label, args), = calls
    assert label == "browser"
    assert args[0]["name"] == "click"  # tool_call first
    assert args[2] == "sess-1"  # session_id third — parity with old branch


@pytest.mark.asyncio
async def test_web_search_routes_to_web_search_handler() -> None:
    mixin, calls = _mixin(), []
    mixin._handle_web_search_tool = _recording_handler(calls, "web_search")

    messages = await _dispatch(mixin, {"name": "web_search", "params": {"query": "hello"}}, [])

    assert messages == ["web_search-msg"]
    (label, args), = calls
    assert args[0]["params"]["query"] == "hello"
    assert args[2] == "sess-1"


@pytest.mark.asyncio
async def test_web_research_handler_receives_tool_name_first() -> None:
    mixin, calls = _mixin(), []
    mixin._handle_web_research_tool = _recording_handler(calls, "research")

    messages = await _dispatch(mixin, {"name": "scrape_url", "params": {"url": "https://example.com"}}, [])

    assert messages == ["research-msg"]
    (label, args), = calls
    assert args[0] == "scrape_url"  # tool_name first — parity with old branch
    assert args[3] == "sess-1"


@pytest.mark.asyncio
async def test_execute_command_routes_with_full_arg_set() -> None:
    mixin, calls = _mixin(), []
    mixin._dispatch_execute_command = _recording_handler(calls, "exec")
    extra_parts: list = []

    messages = [
        msg
        async for msg in mixin._dispatch_tool_call(
            {"name": "execute_command", "params": {"command": "ls"}},
            execution_results=[],
            additional_response_parts=extra_parts,
            **_DISPATCH_ARGS,
        )
    ]

    assert messages == ["exec-msg"]
    (label, args), = calls
    assert args[1] == "sess-1"
    assert args[2] == "term-1"
    assert args[3] == "http://127.0.0.1:11434"
    assert args[4] == "test-model"
    assert args[6] is extra_parts  # additional_response_parts threaded through


@pytest.mark.asyncio
async def test_schema_error_blocks_handler_and_records_result() -> None:
    """Issue #4529 gate parity: invalid params never reach the handler."""
    mixin, calls = _mixin(), []
    mixin._handle_web_search_tool = _recording_handler(calls, "web_search")
    execution_results: list = []

    messages = await _dispatch(mixin, {"name": "web_search", "params": {}}, execution_results)

    assert calls == []  # handler never invoked
    assert len(messages) == 1
    assert messages[0].metadata.get("schema_validation_failed") is True
    (result,) = execution_results
    assert result["status"] == "schema_error"
    assert result["schema_validation_failed"] is True


@pytest.mark.asyncio
async def test_unknown_tool_falls_through_to_mcp() -> None:
    mixin, calls = _mixin(), []
    mixin._dispatch_mcp_or_unknown = _recording_handler(calls, "mcp")

    messages = await _dispatch(mixin, {"name": "totally_unknown_tool", "params": {}}, [])

    assert messages == ["mcp-msg"]
    (label, args), = calls
    assert args[0] == "totally_unknown_tool"
