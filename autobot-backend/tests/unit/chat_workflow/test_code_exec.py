# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for chat_workflow.code_exec package (GH#11568)."""

import asyncio
import json
import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the backend is on sys.path
_BACKEND = pathlib.Path(__file__).parent.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ---------------------------------------------------------------------------
# AST guard tests
# ---------------------------------------------------------------------------


def test_ast_guard_allowed_script():
    """Script using only allowlisted imports passes."""
    from chat_workflow.code_exec.ast_guard import check_script

    script = "import asyncio\nimport json\nresult = json.dumps({'x': 1})\n"
    result = check_script(script, frozenset())
    assert result.ok
    assert result.violations == []


def test_ast_guard_blocked_import():
    """import os is not in the allowlist and must be rejected."""
    from chat_workflow.code_exec.ast_guard import check_script

    result = check_script("import os\n", frozenset())
    assert not result.ok
    assert any("forbidden import" in v["message"] for v in result.violations)


def test_ast_guard_blocked_eval():
    """eval() call must be rejected."""
    from chat_workflow.code_exec.ast_guard import check_script

    result = check_script("import json\nx = eval('1+1')\n", frozenset())
    assert not result.ok
    assert any("eval" in v["message"] for v in result.violations)


def test_ast_guard_blocked_exec():
    """exec() call must be rejected."""
    from chat_workflow.code_exec.ast_guard import check_script

    result = check_script("exec('print(1)')\n", frozenset())
    assert not result.ok
    assert any("exec" in v["message"] for v in result.violations)


def test_ast_guard_blocked_getattr_smuggling():
    """getattr(autobot_tools, computed_name) must be rejected."""
    from chat_workflow.code_exec.ast_guard import check_script

    script = "import autobot_tools\nfn = getattr(autobot_tools, 'web_search')\n"
    result = check_script(script, frozenset())
    assert not result.ok
    assert any("smuggling" in v["message"] for v in result.violations)


def test_ast_guard_blocked_forbidden_token():
    """A name that matches a forbidden_work token must be rejected."""
    from chat_workflow.code_exec.ast_guard import check_script

    result = check_script("x = bash_run\n", frozenset({"bash_run"}))
    assert not result.ok
    assert any("forbidden token" in v["message"] for v in result.violations)


def test_ast_guard_syntax_error():
    """Malformed Python must produce a SyntaxError violation."""
    from chat_workflow.code_exec.ast_guard import check_script

    result = check_script("def broken(:\n    pass\n", frozenset())
    assert not result.ok
    assert any("SyntaxError" in v["message"] for v in result.violations)


# ---------------------------------------------------------------------------
# Shim codegen tests
# ---------------------------------------------------------------------------


def test_shim_codegen_generates_functions():
    """generate_shim_module must produce async def for each tool."""
    from chat_workflow.code_exec.shim_codegen import generate_shim_module

    src = generate_shim_module(["web_search", "scrape_url"])
    assert "async def web_search" in src
    assert "async def scrape_url" in src


def test_injectable_tool_set_empty_allowed():
    """When allowed_work is empty, all CODEEXEC_INJECTABLE_TOOLS minus forbidden are returned."""
    from chat_workflow.code_exec.shim_codegen import CODEEXEC_INJECTABLE_TOOLS, injectable_tool_set

    result = injectable_tool_set([], frozenset())
    assert set(result) == CODEEXEC_INJECTABLE_TOOLS


def test_injectable_tool_set_forbidden_excluded():
    """Forbidden tools must not appear in the injectable set."""
    from chat_workflow.code_exec.shim_codegen import injectable_tool_set

    result = injectable_tool_set([], frozenset({"web_search"}))
    assert "web_search" not in result


# ---------------------------------------------------------------------------
# Broker enforcement tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broker_rejects_non_shimmed_tool():
    """handle_line must return ok=False for a tool not in the injectable list."""
    from chat_workflow.code_exec.broker import CodeExecBroker

    dispatch = AsyncMock(return_value="result")
    broker = CodeExecBroker(
        dispatch_fn=dispatch,
        tools=["web_search"],
        forbidden=frozenset(),
        run_id="test-run",
        security_event_key="autobot:codeexec:audit",
    )
    line = json.dumps({"id": "x", "tool": "execute_command", "params": {}})
    reply = json.loads(await broker.handle_line(line))
    assert reply["ok"] is False
    assert "not injectable" in reply["error"]


@pytest.mark.asyncio
async def test_broker_budget_cap():
    """After CODEEXEC_MAX_TOOL_CALLS calls the next call must be rejected."""
    from chat_workflow.code_exec import broker as broker_mod
    from chat_workflow.code_exec.broker import CodeExecBroker

    dispatch = AsyncMock(return_value="result")
    with patch.object(broker_mod, "CODEEXEC_MAX_TOOL_CALLS", 2):
        b = CodeExecBroker(
            dispatch_fn=dispatch,
            tools=["web_search"],
            forbidden=frozenset(),
            run_id="run-cap",
            security_event_key="autobot:codeexec:audit",
        )
        # Patch _emit_audit to avoid Redis calls
        b._emit_audit = AsyncMock()
        for _ in range(2):
            line = json.dumps({"id": "x", "tool": "web_search", "params": {}})
            reply = json.loads(await b.handle_line(line))
            assert reply["ok"] is True
        # Third call must be rejected
        reply = json.loads(await b.handle_line(json.dumps({"id": "y", "tool": "web_search", "params": {}})))
        assert reply["ok"] is False
        assert "budget" in reply["error"]


# ---------------------------------------------------------------------------
# Compose flag-off test
# ---------------------------------------------------------------------------


def test_compose_absent_from_schemas_when_flag_off():
    """Flag-off zero-change: 'compose' absent from schemas AND uniform routing."""
    import chat_workflow.tool_handler as th

    assert th.CODEEXEC_ENABLED is False  # default posture
    assert "compose" not in th._BUILTIN_TOOL_SCHEMAS
    assert "compose" not in th._UNIFORM_BUILTIN_TOOLS


def test_compose_schema_registration_helper_matches_flag():
    """The COMPOSE_TOOL_SCHEMA is only merged into _BUILTIN_TOOL_SCHEMAS under the flag."""
    import chat_workflow.tool_handler as th

    # Directly exercise the registration predicate the module uses at import time.
    schemas = dict(th._BUILTIN_TOOL_SCHEMAS)
    if th.CODEEXEC_ENABLED:
        schemas["compose"] = th.COMPOSE_TOOL_SCHEMA
        assert schemas["compose"]["required"] == ["program"]
    else:
        assert "compose" not in schemas
    # The schema constant always exists (definition is unconditional); only registration is gated.
    assert th.COMPOSE_TOOL_SCHEMA["properties"]["program"]["type"] == "string"


# ---------------------------------------------------------------------------
# _handle_compose_tool tests (with fakes / patches)
# ---------------------------------------------------------------------------


class _FakeCtx:
    agent_context = None
    consecutive_invalid_tool_calls = 0


class _FakeCtxWithAgent:
    class _AC:
        agent_id = "research_agent"

    agent_context = _AC()
    consecutive_invalid_tool_calls = 0


@pytest.mark.asyncio
async def test_compose_delegated_subagent_rejected():
    """compose must yield error when ctx has an agent_context (delegated subagent)."""
    import chat_workflow.tool_handler as th

    handler = object.__new__(th.ToolHandlerMixin)
    msgs = []
    tool_call = {"name": "compose", "params": {"program": "x = 1"}}
    async for msg in handler._handle_compose_tool(tool_call, "s1", [], _FakeCtxWithAgent()):
        msgs.append(msg)
    assert msgs
    assert "not available" in msgs[0].content


@pytest.mark.asyncio
async def test_compose_ast_violation_rejected():
    """compose must yield a tool_result error when AST guard fires."""
    import chat_workflow.tool_handler as th

    handler = object.__new__(th.ToolHandlerMixin)
    tool_call = {"name": "compose", "params": {"program": "import os"}}
    msgs = []
    async for msg in handler._handle_compose_tool(tool_call, "s1", [], _FakeCtx()):
        msgs.append(msg)
    assert msgs
    assert "AST guard" in msgs[0].content or "rejected" in msgs[0].content


@pytest.mark.asyncio
async def test_compose_approval_gate_creates_record():
    """When auto-approve is off, compose persists a WORKFLOW_GATE record and yields approval_required."""
    import chat_workflow.tool_handler as th

    handler = object.__new__(th.ToolHandlerMixin)
    program = "import asyncio\nresult = 1\n"
    tool_call = {"name": "compose", "params": {"program": program}}
    msgs = []
    handler._persist_compose_approval = AsyncMock(return_value="approval-uuid-1")

    with patch.object(th, "CODEEXEC_AUTOAPPROVE_READONLY", False):
        async for msg in handler._handle_compose_tool(tool_call, "s1", [], _FakeCtx()):
            msgs.append(msg)

    assert any(m.type == "approval_required" for m in msgs)
    # AC: the persist path receives program text + shim snapshot to record on the gate.
    handler._persist_compose_approval.assert_awaited_once()
    call_args = handler._persist_compose_approval.await_args.args
    assert call_args[0] == program
    assert isinstance(call_args[1], list)


@pytest.mark.asyncio
async def test_persist_compose_approval_builds_workflow_gate_context():
    """_persist_compose_approval must create a WORKFLOW_GATE Approval carrying program+shims+budgets."""
    import chat_workflow.tool_handler as th

    handler = object.__new__(th.ToolHandlerMixin)
    created: dict = {}

    class _FakeApproval:
        id = "approval-uuid-2"

    class _FakeSvc:
        def __init__(self, _db):
            pass

        async def create_approval(self, **kwargs):
            created.update(kwargs)
            return _FakeApproval()

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    import services.approval_gate_service as svc_mod
    import user_management.database as db_mod

    with (
        patch.object(svc_mod, "ApprovalGateService", _FakeSvc),
        patch.object(db_mod, "get_async_session_factory", return_value=lambda: _FakeSession()),
    ):
        approval_id = await handler._persist_compose_approval("result = 1", ["web_search"], "s9")

    assert approval_id == "approval-uuid-2"
    assert created["approval_type"] == "workflow_gate"
    assert created["context"]["program"] == "result = 1"
    assert created["context"]["shim_snapshot"] == ["web_search"]
    assert "max_tool_calls" in created["context"]["budgets"]
    assert "timeout_seconds" in created["context"]["budgets"]


@pytest.mark.asyncio
async def test_broker_progress_emitted_dual_bus():
    """A successful shim call emits an audit event AND an EventBus progress event (dual-bus)."""
    from chat_workflow.code_exec.broker import CodeExecBroker

    broker = CodeExecBroker(
        dispatch_fn=AsyncMock(return_value="ok"),
        tools=["web_search"],
        forbidden=frozenset(),
        run_id="run-prog",
        security_event_key="autobot:codeexec:audit",
    )
    broker._emit_audit = AsyncMock()
    broker._emit_progress = AsyncMock()
    reply = json.loads(await broker.handle_line(json.dumps({"id": "p", "tool": "web_search", "params": {}})))
    assert reply["ok"] is True
    await asyncio.sleep(0)  # let create_task fire
    broker._emit_progress.assert_awaited()
    broker._emit_audit.assert_awaited()


@pytest.mark.asyncio
async def test_execute_compose_wires_broker_into_executor():
    """_execute_compose must build a CodeExecBroker and pass it to the executor (production caller)."""
    import chat_workflow.tool_handler as th
    from secure_sandbox_executor import SandboxResult

    handler = object.__new__(th.ToolHandlerMixin)
    fake_result = SandboxResult(
        success=True,
        exit_code=0,
        stdout="done\n",
        stderr="",
        execution_time=0.1,
        container_id="c",
        security_events=[],
        resource_usage={},
        metadata={},
    )
    passed = {}

    async def _fake_exec(program, shim_src, broker, timeout, run_id):
        passed["broker"] = broker
        return fake_result

    fake_executor = MagicMock()
    fake_executor.execute_with_stdio_broker = _fake_exec
    with patch("secure_sandbox_executor.SecureSandboxExecutor", return_value=fake_executor):
        msg = await handler._execute_compose("result = 1", None, "rid", "s1", _FakeCtx())
    from chat_workflow.code_exec.broker import CodeExecBroker

    assert isinstance(passed["broker"], CodeExecBroker)
    assert "done" in msg.content


@pytest.mark.asyncio
async def test_compose_e2e_with_fake_executor():
    """End-to-end: fake SecureSandboxExecutor returns success; result WorkflowMessage carries stdout."""
    import chat_workflow.tool_handler as th
    from secure_sandbox_executor import SandboxResult

    handler = object.__new__(th.ToolHandlerMixin)
    program = "import asyncio\nresult = 42\n"
    tool_call = {"name": "compose", "params": {"program": program}}

    fake_result = SandboxResult(
        success=True,
        exit_code=0,
        stdout="42\n",
        stderr="",
        execution_time=0.1,
        container_id="fake-container",
        security_events=[],
        resource_usage={},
        metadata={},
    )
    fake_executor_instance = MagicMock()
    fake_executor_instance.execute_with_stdio_broker = AsyncMock(return_value=fake_result)

    msgs = []
    with patch("chat_workflow.tool_handler.CODEEXEC_AUTOAPPROVE_READONLY", True):
        with patch("secure_sandbox_executor.SecureSandboxExecutor", return_value=fake_executor_instance):
            async for msg in handler._handle_compose_tool(tool_call, "s1", [], _FakeCtx()):
                msgs.append(msg)

    assert msgs
    result_msg = msgs[-1]
    assert "42" in result_msg.content
