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
    """getattr against the tools module must be rejected (reflective accessor blocked)."""
    from chat_workflow.code_exec.ast_guard import check_script

    script = "import autobot_tools\nfn = getattr(autobot_tools, 'web_search')\n"
    result = check_script(script, frozenset())
    assert not result.ok
    assert any("getattr" in v["message"] for v in result.violations)


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
    handler._poll_compose_approval = AsyncMock(return_value="rejected")

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


# ---------------------------------------------------------------------------
# BLOCKER-1: AST guard escape-gap corpus (each must be REJECTED)
# ---------------------------------------------------------------------------

_ESCAPE_CORPUS = [
    "().__class__.__bases__[0].__subclasses__()",
    'getattr(__builtins__, "exec")()',
    '__builtins__["open"]("x")',
    "breakpoint()",
    'globals()["__builtins__"]',
    "vars()",
    "locals()",
    "import autobot_tools as t\nfn = getattr(t, 'web_search')\n",
    "x = ().__reduce__()",
    # LEAK-1: computed / concatenated attribute name reaching a dunder via getattr.
    "getattr(object(), '__cl' + 'ass__')",
    "g = getattr\ng(object(), '__class__')",
    # LEAK-2: eval/exec/... as a bare Name (decorator, rebind), not a call func.
    "@eval\ndef f():\n    pass\n",
    "f = eval\nf('1')",
    # LEAK-3: delattr smuggling + hasattr with a dunder/computed name.
    "delattr(object, 'x')",
    "hasattr(o, '__class__')",
    # Builtin-ALLOWLIST wave: dangerous builtins caught by allowlist, not blocklist.
    # print/open/input MUST reject — the broker RPC uses the script's stdout for
    # requests and stdin for replies, so print() corrupts the request stream and
    # input() steals a broker reply (protocol integrity, not just sandboxing).
    "open('/etc/passwd')",
    "input()",
    "print('x')",
    "type('X',(object,),{})",
    "memoryview(b'x')",
    "id(o)",
    "dir()",
    "object()",
    "super",
]


@pytest.mark.parametrize("script", _ESCAPE_CORPUS)
def test_ast_guard_rejects_escape_corpus(script):
    """Each known escape technique must be rejected by the hard gate."""
    from chat_workflow.code_exec.ast_guard import check_script

    result = check_script(script, frozenset())
    assert not result.ok, f"escape NOT rejected: {script!r}"
    assert result.violations


_CLEAN_CORPUS = [
    (
        "import autobot_tools\n"
        "import asyncio\n"
        "async def main():\n"
        "    r = await autobot_tools.web_search(query='x')\n"
        "    return r\n"
    ),
    ("import asyncio, json\n" "async def run():\n" "    r = await scrape_url(url='x')\n" "    return json.dumps(r)\n"),
    # Uses SAFE_BUILTINS range/len + math + a comprehension — must pass.
    (
        "import math\n"
        "vals = extract_structured_data(url='u', schema={})\n"
        "n = math.floor(1.5)\n"
        "items = [x for x in range(len(vals))]\n"
    ),
]


@pytest.mark.parametrize("script", _CLEAN_CORPUS)
def test_ast_guard_accepts_clean_scripts(script):
    """Legitimate multi-tool scripts still pass after the gap fixes."""
    from chat_workflow.code_exec.ast_guard import check_script

    result = check_script(script, frozenset())
    assert result.ok, f"clean script wrongly rejected: {result.violations}"


def test_ast_guard_allows_locally_shadowed_builtin_name():
    """A user-defined function shadowing a builtin name is not a builtin violation."""
    from chat_workflow.code_exec.ast_guard import check_script

    script = "def helper(x):\n    return x + 1\n" "result = helper(1)\n"
    assert check_script(script, frozenset()).ok


def test_ast_guard_builtins_allowlist_is_env_extendable():
    """AUTOBOT_CODEEXEC_BUILTINS_ALLOWLIST content is honored (env-extendable constant)."""
    import importlib

    import chat_workflow.code_exec.ast_guard as guard

    # 'print' is excluded by default; a reload with it whitelisted must accept it.
    with patch.dict("os.environ", {"AUTOBOT_CODEEXEC_BUILTINS_ALLOWLIST": "len,range,print"}):
        reloaded = importlib.reload(guard)
        try:
            assert reloaded.check_script("print('x')", frozenset()).ok
        finally:
            importlib.reload(guard)  # restore default module state for other tests


# ---------------------------------------------------------------------------
# MAJOR-3: sensitive tools can never be injected via the env allowlist
# ---------------------------------------------------------------------------


def test_injectable_excludes_sensitive_even_when_env_widened():
    """compose/delegate/execute_command are excluded even if added to the env allowlist."""
    from chat_workflow.code_exec import shim_codegen

    widened = frozenset({"web_search", "compose", "delegate", "execute_command"})
    with patch.object(shim_codegen, "CODEEXEC_INJECTABLE_TOOLS", widened):
        result = shim_codegen.injectable_tool_set([], frozenset())
    assert "compose" not in result
    assert "delegate" not in result
    assert "execute_command" not in result
    assert "web_search" in result


# ---------------------------------------------------------------------------
# MAJOR-1: shim RPC uses per-call ids so concurrent calls correlate
# ---------------------------------------------------------------------------


def test_shim_codegen_uses_per_call_ids_not_tool_name():
    """The shim must not hardcode the tool name as the RPC id."""
    from chat_workflow.code_exec.shim_codegen import generate_shim_module

    src = generate_shim_module(["web_search"])
    assert "_next_id" in src
    assert '"id": "web_search"' not in src  # not a constant id


def test_shim_emits_monotonic_ids_and_correlates():
    """The shim emits a distinct id per call and dispatches replies to a pending map.

    Runs the generated ``_rpc_call`` against a synchronous stub stdio to prove the
    id monotonically increments and that out-of-order replies land on the right id
    — the correlation mechanism — without the executor-thread event-loop coupling
    that only exists inside the real sandbox.
    """
    from chat_workflow.code_exec.shim_codegen import generate_shim_module

    ns: dict = {}
    exec(generate_shim_module(["web_search"]), ns)  # nosec B102 — generated trusted shim under test
    assert ns["_next_id"]() == 1
    assert ns["_next_id"]() == 2  # monotonic, not a constant tool-name id
    # Correlation: a reply keyed by id is retrievable by that id, out of arrival order.
    ns["_pending"][2] = {"id": 2, "ok": True, "result": "B"}
    ns["_pending"][1] = {"id": 1, "ok": True, "result": "A"}
    assert ns["_pending"].pop(1)["result"] == "A"
    assert ns["_pending"].pop(2)["result"] == "B"


@pytest.mark.asyncio
async def test_broker_echoes_request_id():
    """The broker must echo the incoming request id so the shim can correlate replies."""
    from chat_workflow.code_exec.broker import CodeExecBroker

    b = CodeExecBroker(
        dispatch_fn=AsyncMock(return_value="r"),
        tools=["web_search"],
        forbidden=frozenset(),
        run_id="r",
        security_event_key="k",
    )
    b._emit_audit = AsyncMock()
    b._emit_progress = AsyncMock()
    reply = json.loads(await b.handle_line(json.dumps({"id": 7, "tool": "web_search", "params": {}})))
    assert reply["id"] == 7


# ---------------------------------------------------------------------------
# BLOCKER-2/3: executor start-once and multiplexed-frame demux
# ---------------------------------------------------------------------------


def test_demux_frames_strips_docker_headers():
    """_demux_frames must strip the 8-byte stdout frame header and drop stderr frames."""
    from secure_sandbox_executor import SecureSandboxExecutor

    payload = b'{"id": 1}\n'
    stdout_frame = bytes([1, 0, 0, 0]) + len(payload).to_bytes(4, "big") + payload
    stderr_frame = bytes([2, 0, 0, 0]) + (3).to_bytes(4, "big") + b"err"
    decoded, remaining = SecureSandboxExecutor._demux_frames(stdout_frame + stderr_frame)
    assert decoded == payload
    assert remaining == b""


def test_demux_frames_holds_incomplete_frame():
    """A partial frame is returned as remaining bytes, not decoded."""
    from secure_sandbox_executor import SecureSandboxExecutor

    partial = bytes([1, 0, 0, 0]) + (10).to_bytes(4, "big") + b"onl"  # claims 10, has 3
    decoded, remaining = SecureSandboxExecutor._demux_frames(partial)
    assert decoded == b""
    assert remaining == partial


@pytest.mark.asyncio
async def test_run_broker_script_mounts_large_script_via_file_not_argv():
    """MAJOR-2: a large script is delivered by mounted file, not argv (no ARG_MAX)."""
    from secure_sandbox_executor import SandboxSecurityLevel, SecureSandboxExecutor

    ex = object.__new__(SecureSandboxExecutor)
    ex.logger = MagicMock()
    ex.container_prefix = "t-"
    ex.active_containers = {}
    container = MagicMock()
    container.wait.return_value = {"StatusCode": 0}
    container.logs.return_value = b""
    docker_client = MagicMock()
    docker_client.containers.create.return_value = container
    ex.docker_client = docker_client

    captured = {}

    def _prep(cmd, cfg):
        captured["cmd"] = cmd
        return {"image": "x"}

    ex._prepare_container_config = _prep
    ex._parse_logs = lambda logs: ("", "")
    ex._collect_security_events = AsyncMock(return_value=[])
    ex._build_sandbox_result = SecureSandboxExecutor._build_sandbox_result.__get__(ex)
    ex._log_execution_metrics = AsyncMock()
    ex._cleanup_container = AsyncMock()
    ex._pump_broker_io = AsyncMock()

    big = "x = 1  # padding\n" * 20000  # ~300 KB, well over a typical ARG_MAX
    cfg = SecureSandboxExecutor._codeexec_config(ex, 30)
    cfg.security_level = SandboxSecurityLevel.HIGH
    await ex._run_broker_script(big, cfg, MagicMock())
    # The command runs a file path, never embeds the source as an argv token.
    assert captured["cmd"][:2] == ["/usr/bin/python3", "/sandbox/compose_script.py"]
    assert not any(len(str(tok)) > 4096 for tok in captured["cmd"])


@pytest.mark.asyncio
async def test_run_broker_script_starts_container_once():
    """BLOCKER-2: the broker path must call container.start() exactly once (no 409)."""
    from secure_sandbox_executor import SandboxSecurityLevel, SecureSandboxExecutor

    ex = object.__new__(SecureSandboxExecutor)
    ex.logger = MagicMock()
    ex.container_prefix = "t-"
    ex.active_containers = {}

    container = MagicMock()
    container.wait.return_value = {"StatusCode": 0}
    container.logs.return_value = b""
    docker_client = MagicMock()
    docker_client.containers.create.return_value = container
    ex.docker_client = docker_client

    ex._prepare_container_config = lambda cmd, cfg: {"image": "x"}
    ex._parse_logs = lambda logs: ("out", "")
    ex._collect_security_events = AsyncMock(return_value=[])
    ex._build_sandbox_result = SecureSandboxExecutor._build_sandbox_result.__get__(ex)
    ex._log_execution_metrics = AsyncMock()
    ex._cleanup_container = AsyncMock()
    ex._pump_broker_io = AsyncMock()

    cfg = SecureSandboxExecutor._codeexec_config(ex, 30)
    cfg.security_level = SandboxSecurityLevel.HIGH
    await ex._run_broker_script("print(1)", cfg, MagicMock())
    assert container.start.call_count == 1


# ---------------------------------------------------------------------------
# BLOCKER-4: non-read-only shim forces the gate even with the flag on
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compose_non_readonly_shim_forces_gate_despite_flag():
    """A non-read-only tool in the shim snapshot forces approval even when auto-approve is on."""
    import chat_workflow.tool_handler as th

    handler = object.__new__(th.ToolHandlerMixin)
    handler._persist_compose_approval = AsyncMock(return_value="gate-1")
    handler._poll_compose_approval = AsyncMock(return_value="rejected")
    handler._compose_shim_snapshot = lambda agent_id: ["web_search", "write_file"]
    tool_call = {"name": "compose", "params": {"program": "import asyncio\n"}}

    msgs = []
    with patch.object(th, "CODEEXEC_AUTOAPPROVE_READONLY", True):
        async for msg in handler._handle_compose_tool(tool_call, "s1", [], _FakeCtx()):
            msgs.append(msg)

    handler._persist_compose_approval.assert_awaited_once()  # gate created despite flag
    assert any(m.type == "approval_required" for m in msgs)


def test_compose_auto_approvable_only_for_readonly_set():
    """_compose_auto_approvable is True only when all shims are read-only AND flag on."""
    import chat_workflow.tool_handler as th

    handler = object.__new__(th.ToolHandlerMixin)
    with patch.object(th, "CODEEXEC_AUTOAPPROVE_READONLY", True):
        assert handler._compose_auto_approvable(["web_search"]) is True
        assert handler._compose_auto_approvable(["web_search", "write_file"]) is False
    with patch.object(th, "CODEEXEC_AUTOAPPROVE_READONLY", False):
        assert handler._compose_auto_approvable(["web_search"]) is False


# ---------------------------------------------------------------------------
# MINOR-2: approved gate resumes execution; denied gate returns a refusal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compose_gate_approved_resumes_execution():
    """An APPROVED gate proceeds to _execute_compose."""
    import chat_workflow.tool_handler as th

    handler = object.__new__(th.ToolHandlerMixin)
    handler._persist_compose_approval = AsyncMock(return_value="gate-2")
    handler._poll_compose_approval = AsyncMock(return_value="approved")
    handler._compose_shim_snapshot = lambda agent_id: ["write_file"]  # forces gate
    handler._execute_compose = AsyncMock(
        return_value=type("M", (), {"content": "ran", "type": "tool_result", "metadata": {}})()
    )
    tool_call = {"name": "compose", "params": {"program": "import asyncio\n"}}

    msgs = []
    with patch.object(th, "CODEEXEC_AUTOAPPROVE_READONLY", False):
        async for msg in handler._handle_compose_tool(tool_call, "s1", [], _FakeCtx()):
            msgs.append(msg)

    handler._execute_compose.assert_awaited_once()
    assert msgs[-1].content == "ran"


@pytest.mark.asyncio
async def test_compose_gate_denied_returns_refusal_and_skips_execution():
    """A DENIED gate returns a refusal and never calls _execute_compose."""
    import chat_workflow.tool_handler as th

    handler = object.__new__(th.ToolHandlerMixin)
    handler._persist_compose_approval = AsyncMock(return_value="gate-3")
    handler._poll_compose_approval = AsyncMock(return_value="rejected")
    handler._compose_shim_snapshot = lambda agent_id: ["write_file"]
    handler._execute_compose = AsyncMock()
    tool_call = {"name": "compose", "params": {"program": "import asyncio\n"}}

    msgs = []
    with patch.object(th, "CODEEXEC_AUTOAPPROVE_READONLY", False):
        async for msg in handler._handle_compose_tool(tool_call, "s1", [], _FakeCtx()):
            msgs.append(msg)

    handler._execute_compose.assert_not_awaited()
    assert any("not approved" in m.content for m in msgs)


# ---------------------------------------------------------------------------
# MINOR-3: budget cannot overshoot under concurrent reservation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broker_budget_no_overshoot_concurrent():
    """Concurrent handle_line calls must not exceed the budget cap."""
    from chat_workflow.code_exec import broker as broker_mod
    from chat_workflow.code_exec.broker import CodeExecBroker

    async def _slow_dispatch(tool, params):
        await asyncio.sleep(0)
        return "ok"

    with patch.object(broker_mod, "CODEEXEC_MAX_TOOL_CALLS", 3):
        b = CodeExecBroker(
            dispatch_fn=_slow_dispatch,
            tools=["web_search"],
            forbidden=frozenset(),
            run_id="r",
            security_event_key="k",
        )
        b._emit_audit = AsyncMock()
        b._emit_progress = AsyncMock()
        lines = [json.dumps({"id": i, "tool": "web_search", "params": {}}) for i in range(10)]
        replies = await asyncio.gather(*(b.handle_line(x) for x in lines))
    ok_count = sum(1 for r in replies if json.loads(r)["ok"])
    assert ok_count == 3  # never overshoots the cap


# ---------------------------------------------------------------------------
# GH#11613: RPC sentinel separates broker traffic from the script's result
# ---------------------------------------------------------------------------


def test_shim_rpc_lines_carry_sentinel_prefix():
    """Generated shim writes RPC requests prefixed with RPC_SENTINEL."""
    from chat_workflow.code_exec.protocol import RPC_SENTINEL
    from chat_workflow.code_exec.shim_codegen import generate_shim_module

    src = generate_shim_module(["web_search"])
    assert repr(RPC_SENTINEL) in src
    assert "_RPC_SENTINEL + req" in src


@pytest.mark.asyncio
async def test_drain_lines_routes_sentinel_to_broker_and_output_to_script():
    """A sentinel line hits the broker; a plain script line goes to script_out (not the broker)."""
    from chat_workflow.code_exec.protocol import RPC_SENTINEL
    from secure_sandbox_executor import SecureSandboxExecutor

    ex = object.__new__(SecureSandboxExecutor)
    broker = MagicMock()
    broker.handle_line = AsyncMock(return_value='{"id": 1, "ok": true, "result": {}}')
    broker.budget_exhausted = False
    stream = MagicMock()

    rpc = (RPC_SENTINEL + json.dumps({"id": 1, "tool": "web_search", "params": {}})).encode("utf-8")
    plain = b'RESULT {"answer": 42}'
    line_buf = rpc + b"\n" + plain + b"\n"
    script_out: list[str] = []

    aborted, remaining = await ex._drain_lines(stream, broker, line_buf, MagicMock(), script_out)

    assert aborted is False
    # The broker saw ONLY the RPC payload, with the sentinel stripped.
    broker.handle_line.assert_awaited_once()
    handed = broker.handle_line.await_args[0][0]
    assert not handed.startswith(RPC_SENTINEL)
    assert json.loads(handed)["tool"] == "web_search"
    # The script's own line was captured, never routed to the broker.
    assert script_out == ['RESULT {"answer": 42}']


@pytest.mark.asyncio
async def test_drain_lines_script_print_is_not_a_bogus_tool_call():
    """Regression for #11613: a bare print() must NOT reach broker.handle_line."""
    from secure_sandbox_executor import SecureSandboxExecutor

    ex = object.__new__(SecureSandboxExecutor)
    broker = MagicMock()
    broker.handle_line = AsyncMock()
    broker.budget_exhausted = False

    script_out: list[str] = []
    line_buf = b"hello from the script\n" + json.dumps({"tool": "", "id": 0}).encode("utf-8") + b"\n"
    await ex._drain_lines(MagicMock(), broker, line_buf, MagicMock(), script_out)

    broker.handle_line.assert_not_awaited()
    assert script_out == ["hello from the script", json.dumps({"tool": "", "id": 0})]


@pytest.mark.asyncio
async def test_collect_broker_results_uses_script_stdout_not_rpc_logs():
    """#11613: result.stdout is the captured script output, not container.logs()."""
    from secure_sandbox_executor import SandboxSecurityLevel, SecureSandboxExecutor

    ex = object.__new__(SecureSandboxExecutor)
    ex.logger = MagicMock()
    container = MagicMock()
    container.wait.return_value = {"StatusCode": 0}
    # Simulate polluted logs: if the code used logs() for stdout, this RPC noise would leak.
    container.logs.return_value = b'\x1eCXRPC\x1e{"id": 1}\nRESULT clean'
    ex._parse_logs = SecureSandboxExecutor._parse_logs.__get__(ex)
    ex._collect_security_events = AsyncMock(return_value=[])
    ex._build_sandbox_result = SecureSandboxExecutor._build_sandbox_result.__get__(ex)
    ex._log_execution_metrics = AsyncMock()

    cfg = SecureSandboxExecutor._codeexec_config(ex, 30)
    cfg.security_level = SandboxSecurityLevel.HIGH
    result = await ex._collect_broker_results(container, "cid", cfg, 0.0, "RESULT clean")

    assert result.stdout == "RESULT clean"
    assert "CXRPC" not in result.stdout
    # stdout must NOT have been sourced from container.logs (called with stdout=False).
    _, kwargs = container.logs.call_args
    assert kwargs.get("stdout") is False
    # stderr-only logs are surfaced (not silently dropped): _parse_logs lumps
    # them into element 0, so the broker path reads them from there (#11613 review).
    assert "RESULT clean" in result.stderr
