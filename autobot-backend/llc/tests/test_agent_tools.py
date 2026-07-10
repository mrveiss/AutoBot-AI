# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the LLC chat-agent tools (#11501 T1).

dispatch_llc_tool routes create_task/update_goal/request_approval/
record_decision to the existing llc/services, company-scoped, opening its own
DB session. These tests mock the session factory + services so no DB is needed.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc import agent_tools
from llc.agent_tools import LLC_TOOL_NAMES, LLC_TOOL_SCHEMAS, LLCToolError, dispatch_llc_tool

_COMPANY = str(uuid.uuid4())


def _patch_session():
    """Patch _session_factory so `async with factory()() as s: async with s.begin()` works."""
    session = MagicMock()

    @asynccontextmanager
    async def _begin():
        yield

    session.begin = _begin

    @asynccontextmanager
    async def _sess_cm():
        yield session

    factory = MagicMock(return_value=_sess_cm())
    return patch.object(agent_tools, "_session_factory", return_value=factory), session


# ---------------------------------------------------------------------------
# schema surface
# ---------------------------------------------------------------------------


def test_four_tools_registered():
    assert LLC_TOOL_NAMES == {"create_task", "update_goal", "request_approval", "record_decision"}
    for schema in LLC_TOOL_SCHEMAS.values():
        assert schema["type"] == "object" and "properties" in schema


def test_schemas_merged_into_builtin_validation():
    # #11501: LLC schemas must be validated like any built-in tool. Importing
    # chat_workflow pulls the full chat pipeline (heavy); skip where that chain
    # isn't importable in this env — it runs in CI where deps are present.
    try:
        from chat_workflow.tool_handler import _BUILTIN_TOOL_SCHEMAS
    except Exception as exc:  # noqa: BLE001 — env-dependent import chain
        pytest.skip(f"chat_workflow not importable here: {exc}")
    for name in LLC_TOOL_NAMES:
        assert name in _BUILTIN_TOOL_SCHEMAS


# ---------------------------------------------------------------------------
# company-context guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_company_id_raises():
    with pytest.raises(LLCToolError):
        await dispatch_llc_tool("create_task", {"title": "x"}, None)


@pytest.mark.asyncio
async def test_unknown_tool_raises():
    with pytest.raises(LLCToolError):
        await dispatch_llc_tool("nope", {}, _COMPANY)


# ---------------------------------------------------------------------------
# dispatch → service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_task_calls_work_item_service():
    p, session = _patch_session()
    item = MagicMock(id=uuid.uuid4())
    svc = MagicMock()
    svc.create = AsyncMock(return_value=item)
    with p, patch("llc.services.work_item_service.WorkItemService", return_value=svc):
        out = await dispatch_llc_tool("create_task", {"title": "Write Q3 report", "priority": "high"}, _COMPANY)
    assert out["status"] == "success" and out["entity_type"] == "work_item"
    assert svc.create.await_args.kwargs["company_id"] == _COMPANY
    assert svc.create.await_args.kwargs["title"] == "Write Q3 report"


@pytest.mark.asyncio
async def test_create_task_blank_title_is_tool_error():
    p, _ = _patch_session()
    with p:
        with pytest.raises(LLCToolError):
            await dispatch_llc_tool("create_task", {"title": "   "}, _COMPANY)


@pytest.mark.asyncio
async def test_request_approval_calls_service():
    p, _ = _patch_session()
    appr = MagicMock(id=uuid.uuid4())
    svc = MagicMock()
    svc.request_approval = AsyncMock(return_value=appr)
    with p, patch("llc.services.approval.ApprovalService", return_value=svc):
        out = await dispatch_llc_tool("request_approval", {"summary": "Approve the new hire"}, _COMPANY)
    assert out["status"] == "success" and out["entity_type"] == "approval"
    assert svc.request_approval.await_args.kwargs["company_id"] == uuid.UUID(_COMPANY)


@pytest.mark.asyncio
async def test_record_decision_needs_no_service():
    p, _ = _patch_session()
    with p:
        out = await dispatch_llc_tool("record_decision", {"decision": "Ship v2 on Friday"}, _COMPANY)
    assert out["status"] == "success" and out["entity_type"] == "decision"
    assert out["decision"] == "Ship v2 on Friday"
