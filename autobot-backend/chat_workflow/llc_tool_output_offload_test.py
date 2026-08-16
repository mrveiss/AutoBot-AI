# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An LLC tool result is a dict, and the offload only understands strings (#14284).

``_handle_llc_tool`` (``chat_workflow/tool_handler.py``) used to store the raw
dict ``dispatch_llc_tool`` returns under ``output``. ``spill_execution_results``
(``agent_loop/tool_output_spill.py``) type-guards on ``str`` before it will even
look at a key:

    keys = [k for k in _EXECUTION_RESULT_TEXT_KEYS if isinstance(entry.get(k), str) and entry[k]]

so a dict payload was skipped silently no matter what the adapter's key list
contained, and an oversized LLC entity dump reached the model whole.

The fixture is built by driving the real ``dispatch_llc_tool``/``_handle_llc_tool``
path — mocking only the DB session and service layer, the same pattern as
``llc/tests/test_agent_tools.py`` — not a hand-written ``{"output": {...}}``
dict. A hand-written fixture is exactly the shape that let this hole survive
two prior key-list fixes: it proves the adapter forwards what it is given,
which was never the question.
"""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_loop import tool_output_spill as spill
from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.tool_handler import ToolHandlerMixin
from llc import agent_tools

pytestmark = pytest.mark.asyncio

_COMPANY = str(uuid.uuid4())
_USER = str(uuid.uuid4())
_BIG_TITLE = "T" * 40_000
_TASK_ID = "run-14284"


def _patch_session():
    """Same pattern as ``llc/tests/test_agent_tools.py::_patch_session``."""
    session = MagicMock()

    @asynccontextmanager
    async def _begin():
        yield

    session.begin = _begin

    @asynccontextmanager
    async def _sess_cm():
        yield session

    factory = MagicMock(return_value=_sess_cm())
    return patch.object(agent_tools, "_session_factory", return_value=factory)


async def _dispatch_create_task(title: str):
    """Drive ``_handle_llc_tool`` through the real LLC dispatch path.

    Only ``WorkItemService`` (the DB-facing collaborator) is mocked, exactly as
    ``test_agent_tools.py`` does — ``dispatch_llc_tool``, ``_create_task`` and
    ``_handle_llc_tool`` all run for real, so the resulting envelope is the one
    production actually builds.
    """
    handler = ToolHandlerMixin()
    execution_results: list = []
    item = MagicMock(id=uuid.uuid4())
    svc = MagicMock()
    svc.create = AsyncMock(return_value=item)
    ctx = SimpleNamespace(context={"company_id": _COMPANY, "user_id": _USER})
    tool_call = {"name": "create_task", "params": {"title": title, "priority": "high"}}

    with _patch_session(), patch("llc.services.work_item_service.WorkItemService", return_value=svc):
        messages = [m async for m in handler._handle_llc_tool("create_task", tool_call, execution_results, ctx)]

    return execution_results, messages


@pytest.fixture(autouse=True)
def _spill_on(tmp_path, monkeypatch):
    monkeypatch.setattr(spill, "SPILL_ENABLED", True)
    monkeypatch.setattr(spill, "SPILL_THRESHOLD_CHARS", 500)
    monkeypatch.setattr(spill, "SPILL_EXCERPT_CHARS", 100)
    monkeypatch.setenv("AUTOBOT_TOOL_OUTPUT_SPILL_ROOT", str(tmp_path))
    spill.bind_task(_TASK_ID)
    yield
    spill.bind_task(None)


class TestTheEnvelopeStaysAString:
    async def test_a_successful_llc_result_stores_a_str_not_a_dict(self):
        execution_results, _ = await _dispatch_create_task("Write Q3 report")

        assert execution_results[0]["status"] == "success"
        assert isinstance(execution_results[0]["output"], str)

    async def test_the_serialised_output_round_trips_the_real_result(self):
        """Nothing the caller reads (entity_type/entity_id) is lost by serialising."""
        execution_results, _ = await _dispatch_create_task("Write Q3 report")

        parsed = json.loads(execution_results[0]["output"])
        assert parsed["entity_type"] == "work_item"
        assert parsed["title"] == "Write Q3 report"
        assert "entity_id" in parsed

    async def test_as_output_text_still_renders_it(self):
        """AC: ``_as_output_text``/``_format_execution_step`` still work."""
        execution_results, _ = await _dispatch_create_task("Write Q3 report")
        mgr = ChatWorkflowManager.__new__(ChatWorkflowManager)

        rendered = mgr._format_execution_step(1, execution_results[0])

        assert "work_item" in rendered
        assert "Write Q3 report" in rendered
        assert "(no output)" not in rendered


class TestAnOversizedLLCResultOffloads:
    async def test_the_dict_payload_is_offloaded_with_excerpt_and_anchor(self):
        """AC: an oversized LLC tool result is offloaded, excerpt+anchor reach the model."""
        execution_results, _ = await _dispatch_create_task(_BIG_TITLE)
        original_output = execution_results[0]["output"]
        assert isinstance(original_output, str), "precondition: the producer serialises (#14284)"

        rewritten, count = spill.spill_execution_results(_TASK_ID, execution_results)

        assert count == 1
        assert len(rewritten[0]["output"]) < len(original_output)
        assert rewritten[0]["anchors"][0].startswith(f"autobot:spill:{_TASK_ID}:")
        assert "read_spilled_output" in rewritten[0]["output"]

    async def test_the_full_output_is_retrievable_through_the_anchor(self):
        execution_results, _ = await _dispatch_create_task(_BIG_TITLE)
        original_output = execution_results[0]["output"]

        rewritten, _ = spill.spill_execution_results(_TASK_ID, execution_results)
        window = spill.read_spilled_window(rewritten[0]["anchors"][0])

        assert window["found"] is True
        assert window["total_chars"] == len(original_output)

    async def test_the_envelope_survives(self):
        """``status``/``tool`` decide error handling downstream — must not be dropped."""
        execution_results, _ = await _dispatch_create_task(_BIG_TITLE)

        rewritten, _ = spill.spill_execution_results(_TASK_ID, execution_results)

        assert rewritten[0]["status"] == "success"
        assert rewritten[0]["tool"] == "create_task"
