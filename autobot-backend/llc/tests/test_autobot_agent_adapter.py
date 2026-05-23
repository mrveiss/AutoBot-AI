# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for AutoBotAgentAdapter (GH#8227).

Unit tests use lightweight duck-typed stubs so no live LLM is required and
the heavy ``agents/`` import chain is never triggered.
The integration test dispatches the real SummarizationAgent; it is marked
``integration`` so normal CI skips it.
"""

from __future__ import annotations

import asyncio
import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Stub agents/* so importing autobot_agent_adapter doesn't pull the full chain.
# autobot_agent_adapter only needs `AgentRequest` from agents.base_agent.
# ──────────────────────────────────────────────────────────────────────────────
if "agents" not in sys.modules:
    _agents_stub = types.ModuleType("agents")
    _agents_stub.__path__ = []
    _agents_stub.__package__ = "agents"
    sys.modules["agents"] = _agents_stub

if "agents.base_agent" not in sys.modules:
    from dataclasses import dataclass

    _base_stub = types.ModuleType("agents.base_agent")

    @dataclass
    class _AgentRequest:
        request_id: str
        agent_type: str
        action: str
        payload: dict
        context: dict | None = None
        priority: str = "normal"
        timeout: float = 30.0
        metadata: dict | None = None

    @dataclass
    class _AgentResponse:
        request_id: str
        agent_type: str
        status: str
        result: Any
        error: str | None = None
        execution_time: float = 0.0
        metadata: dict | None = None

    _base_stub.AgentRequest = _AgentRequest
    _base_stub.AgentResponse = _AgentResponse
    _base_stub.BaseAgent = object  # duck-typed; stubs don't inherit
    _base_stub.DeploymentMode = MagicMock()
    sys.modules["agents.base_agent"] = _base_stub

# Now the adapter's import resolves correctly.
from llc.adapters.autobot_agent_adapter import (  # noqa: E402
    AutoBotAgentAdapter,
    _build_agent_request,
    _import_agent_class,
)
from llc.adapters.base import (  # noqa: E402
    AdapterRunStatus,
    LLCAdapter,
    get_adapter,
    register_adapter,
)
from llc.models.enums import LLCRunStatus  # noqa: E402

# Convenience aliases for stub types
_AgentRequest = sys.modules["agents.base_agent"].AgentRequest
_AgentResponse = sys.modules["agents.base_agent"].AgentResponse


# ──────────────────────────────────────────────────────────────────────────────
# Duck-typed agent stubs (no BaseAgent inheritance)
# ──────────────────────────────────────────────────────────────────────────────


class _FakeAgent:
    """Minimal agent stub: returns success immediately."""

    def __init__(self, **kwargs):
        self.agent_type = "fake_agent"

    async def process_request(self, request):
        return _AgentResponse(
            request_id=request.request_id,
            agent_type=self.agent_type,
            status="success",
            result={"echo": request.payload},
            metadata={"model": "test-model", "prompt_tokens": 10, "completion_tokens": 5},
        )


class _FailingAgent:
    """Agent stub that always returns an error response."""

    def __init__(self, **kwargs):
        self.agent_type = "failing_agent"

    async def process_request(self, request):
        return _AgentResponse(
            request_id=request.request_id,
            agent_type=self.agent_type,
            status="error",
            result=None,
            error="deliberate test failure",
        )


# Register stub classes in sys.modules so _import_agent_class can find them.
_THIS_MODULE = "llc.tests.test_autobot_agent_adapter"
_FAKE_AGENT_PATH = f"{_THIS_MODULE}._FakeAgent"
_FAILING_AGENT_PATH = f"{_THIS_MODULE}._FailingAgent"

# Ensure the current test module is discoverable via importlib.
sys.modules.setdefault(_THIS_MODULE, sys.modules[__name__])


# ──────────────────────────────────────────────────────────────────────────────
# _import_agent_class
# ──────────────────────────────────────────────────────────────────────────────


def test_import_agent_class_valid():
    cls = _import_agent_class(_FAKE_AGENT_PATH)
    assert cls is _FakeAgent


def test_import_agent_class_no_dot_raises():
    with pytest.raises(ImportError, match="must be <module>.<ClassName>"):
        _import_agent_class("NoModuleHere")


def test_import_agent_class_bad_module_raises():
    with pytest.raises((ImportError, ModuleNotFoundError)):
        _import_agent_class("nonexistent_module_xyz.SomeClass")


def test_import_agent_class_bad_class_raises():
    with pytest.raises(AttributeError):
        _import_agent_class(f"{_THIS_MODULE}.NonExistentClass")


# ──────────────────────────────────────────────────────────────────────────────
# _build_agent_request
# ──────────────────────────────────────────────────────────────────────────────


def test_build_agent_request_maps_context_fields():
    ctx = {
        "title": "Fix the widget",
        "description": "Widget is broken",
        "acceptance_criteria": "It works",
        "goal_ancestry": ["Goal A", "Goal B"],
        "kb_context": "Some KB text",
        "action": "summarize",
    }
    req = _build_agent_request("run-1", ctx)
    assert req.request_id == "run-1"
    assert req.action == "summarize"
    assert req.payload["title"] == "Fix the widget"
    assert req.payload["goal_ancestry"] == ["Goal A", "Goal B"]
    assert req.context["source"] == "llc_heartbeat"


def test_build_agent_request_default_action():
    req = _build_agent_request("run-2", {"title": "T"})
    assert req.action == "execute"


def test_build_agent_request_extra_keys_forwarded():
    req = _build_agent_request("run-3", {"title": "T", "custom_key": "val"})
    assert req.payload["custom_key"] == "val"


# ──────────────────────────────────────────────────────────────────────────────
# AutoBotAgentAdapter construction
# ──────────────────────────────────────────────────────────────────────────────


def test_adapter_init_validates_class():
    adapter = AutoBotAgentAdapter({"agent_class": _FAKE_AGENT_PATH})
    assert adapter._agent_cls is _FakeAgent


def test_adapter_init_missing_class_raises():
    with pytest.raises(ValueError, match="agent_class"):
        AutoBotAgentAdapter({})


def test_adapter_init_bad_class_path_raises():
    with pytest.raises((ImportError, AttributeError, ModuleNotFoundError)):
        AutoBotAgentAdapter({"agent_class": "no.such.Class"})


# ──────────────────────────────────────────────────────────────────────────────
# invoke / status / cancel
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invoke_returns_run_id_then_completed():
    adapter = AutoBotAgentAdapter({"agent_class": _FAKE_AGENT_PATH})
    ctx = {"title": "Test task", "description": "Do stuff"}

    run_id = await adapter.invoke({}, ctx)
    assert isinstance(run_id, str) and len(run_id) > 0

    await asyncio.sleep(0)

    status = await adapter.status({}, run_id)
    assert status.status == LLCRunStatus.COMPLETED
    assert status.exit_code == 0


@pytest.mark.asyncio
async def test_status_running_before_completion():
    """Status is RUNNING immediately after invoke (before event loop yields)."""

    class _SlowAgent:
        def __init__(self, **_):
            self.agent_type = "slow"

        async def process_request(self, req):
            await asyncio.sleep(9999)
            return _AgentResponse(req.request_id, "slow", "success", {})

    adapter = AutoBotAgentAdapter.__new__(AutoBotAgentAdapter)
    adapter._agent_cls = _SlowAgent
    adapter._agent_kwargs = {}
    adapter._budget_session_factory = None
    adapter._run_log_store = None
    adapter._tasks = {}
    adapter._logs = {}

    run_id = await adapter.invoke({}, {"title": "T"})
    status = await adapter.status({}, run_id)
    assert status.status == LLCRunStatus.RUNNING

    await adapter.cancel({}, run_id)


@pytest.mark.asyncio
async def test_status_unknown_run_id_returns_failed():
    adapter = AutoBotAgentAdapter({"agent_class": _FAKE_AGENT_PATH})
    status = await adapter.status({}, "nonexistent-run-id")
    assert status.status == LLCRunStatus.FAILED
    assert "Unknown run_id" in (status.error or "")


@pytest.mark.asyncio
async def test_failing_agent_maps_to_failed_status():
    adapter = AutoBotAgentAdapter({"agent_class": _FAILING_AGENT_PATH})
    run_id = await adapter.invoke({}, {"title": "Test"})
    await asyncio.sleep(0)
    status = await adapter.status({}, run_id)
    assert status.status == LLCRunStatus.FAILED
    assert status.exit_code == 1


@pytest.mark.asyncio
async def test_cancel_cancels_task():
    """Cancel a slow agent; status must become CANCELLED."""

    class _SlowAgent:
        def __init__(self, **_):
            self.agent_type = "slow"

        async def process_request(self, req):
            await asyncio.sleep(9999)

    adapter = AutoBotAgentAdapter.__new__(AutoBotAgentAdapter)
    adapter._agent_cls = _SlowAgent
    adapter._agent_kwargs = {}
    adapter._budget_session_factory = None
    adapter._run_log_store = None
    adapter._tasks = {}
    adapter._logs = {}

    run_id = await adapter.invoke({}, {"title": "Slow"})
    await adapter.cancel({}, run_id)
    status = await adapter.status({}, run_id)
    assert status.status == LLCRunStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_noop_on_completed_task():
    adapter = AutoBotAgentAdapter({"agent_class": _FAKE_AGENT_PATH})
    run_id = await adapter.invoke({}, {"title": "T"})
    await asyncio.sleep(0)
    await adapter.cancel({}, run_id)  # should not raise


# ──────────────────────────────────────────────────────────────────────────────
# Log capture
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_store_write_called_when_agent_prints():
    class _PrintingAgent:
        def __init__(self, **_):
            self.agent_type = "printer"

        async def process_request(self, req):
            print("hello from agent")  # noqa: T201
            return _AgentResponse(req.request_id, self.agent_type, "success", {})

    store = MagicMock()
    store.write = AsyncMock()

    adapter = AutoBotAgentAdapter.__new__(AutoBotAgentAdapter)
    adapter._agent_cls = _PrintingAgent
    adapter._agent_kwargs = {}
    adapter._budget_session_factory = None
    adapter._run_log_store = store
    adapter._tasks = {}
    adapter._logs = {}

    run_id = await adapter.invoke({}, {"title": "Printer test"})
    await asyncio.sleep(0.05)

    store.write.assert_called_once()
    call_run_id, log_text = store.write.call_args.args
    assert call_run_id == run_id
    assert "hello from agent" in log_text


@pytest.mark.asyncio
async def test_get_log_returns_captured_output():
    adapter = AutoBotAgentAdapter({"agent_class": _FAKE_AGENT_PATH})
    run_id = await adapter.invoke({}, {"title": "T"})
    await asyncio.sleep(0.05)
    log = adapter.get_log(run_id)
    assert log is not None  # key present after completion


# ──────────────────────────────────────────────────────────────────────────────
# Cost forwarding
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cost_forwarded_to_budget_service():
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    # session_factory() must return an async context manager, not a coroutine.
    def session_factory():
        return mock_session

    with patch("llc.services.budget.BudgetService") as MockBS:
        MockBS.return_value.ingest_cost_event = AsyncMock()

        adapter = AutoBotAgentAdapter(
            {"agent_class": _FAKE_AGENT_PATH},
            budget_session_factory=session_factory,
        )
        run_id = await adapter.invoke({}, {"title": "T", "agent_id": "agent-xyz"})
        await asyncio.sleep(0.05)

        MockBS.return_value.ingest_cost_event.assert_called_once()
        args = MockBS.return_value.ingest_cost_event.call_args.args
        # positional: session, agent_id, tokens_in, tokens_out, model
        assert args[1] == "agent-xyz"
        assert args[2] == 10  # prompt_tokens from _FakeAgent metadata
        assert args[3] == 5   # completion_tokens


@pytest.mark.asyncio
async def test_cost_not_forwarded_when_no_factory():
    adapter = AutoBotAgentAdapter({"agent_class": _FAKE_AGENT_PATH})
    run_id = await adapter.invoke({}, {"title": "T", "agent_id": "agent-xyz"})
    await asyncio.sleep(0.05)
    status = await adapter.status({}, run_id)
    assert status.status == LLCRunStatus.COMPLETED


# ──────────────────────────────────────────────────────────────────────────────
# cleanup_completed
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cleanup_completed_removes_done_tasks():
    adapter = AutoBotAgentAdapter({"agent_class": _FAKE_AGENT_PATH})
    run_id = await adapter.invoke({}, {"title": "T"})
    await asyncio.sleep(0.05)

    assert run_id in adapter._tasks
    removed = adapter.cleanup_completed()
    assert removed == 1
    assert run_id not in adapter._tasks


# ──────────────────────────────────────────────────────────────────────────────
# AdapterRegistry (base.py)
# ──────────────────────────────────────────────────────────────────────────────


def test_register_and_get_adapter():
    adapter = AutoBotAgentAdapter({"agent_class": _FAKE_AGENT_PATH})
    register_adapter("_test_fake", adapter)
    retrieved = get_adapter("_test_fake")
    assert retrieved is adapter


def test_get_adapter_unknown_raises():
    with pytest.raises(KeyError, match="No LLC adapter registered"):
        get_adapter("absolutely_nonexistent_adapter_type_xyz_999")


def test_llcadapter_protocol_satisfied():
    """AutoBotAgentAdapter satisfies the runtime-checkable LLCAdapter Protocol."""
    adapter = AutoBotAgentAdapter({"agent_class": _FAKE_AGENT_PATH})
    assert isinstance(adapter, LLCAdapter)


# ──────────────────────────────────────────────────────────────────────────────
# Integration: dispatch SummarizationAgent stub on a work item (needs live LLM)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_summarization_agent_reaches_completed():
    """Dispatch the real SummarizationAgent on a stub work item.

    Requires a configured LLM backend.  Skipped in unit CI via the
    ``integration`` marker.

    Verifies the run record reaches ``COMPLETED`` (maps to GH#8227's
    "succeeded" language; GH#8261 unified both into ``LLCRunStatus.COMPLETED``).
    """
    adapter = AutoBotAgentAdapter(
        {"agent_class": "agents.summarization_agent.SummarizationAgent"}
    )
    context = {
        "title": "Summarize the widget documentation",
        "description": "The widget docs are 3 pages long.",
        "acceptance_criteria": "Produce a 2-sentence summary.",
        "action": "summarize",
        "text": "The widget is a reusable UI component. It supports dark mode. It is accessible.",
    }
    run_id = await adapter.invoke({}, context)
    assert run_id

    for _ in range(60):
        await asyncio.sleep(0.5)
        st = await adapter.status({}, run_id)
        if st.status != LLCRunStatus.RUNNING:
            break

    assert st.status == LLCRunStatus.COMPLETED, f"Expected COMPLETED, got {st.status}: {st.error}"
