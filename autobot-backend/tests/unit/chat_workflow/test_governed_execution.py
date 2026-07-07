# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Governed execution identity at the production tool seam (GH#11159 / GH#11160).

Threads a governed agent identity and a work item's declared approval categories
from the request context into LLMIterationContext, so the enforcement wired in
#11145 (forbidden_work) and the new work-item approval gate actually bite at
`_dispatch_tool_call` — the single production seam.
"""

from types import SimpleNamespace

import pytest

from chat_workflow.models import build_governed_identity
from chat_workflow.tool_handler import ToolHandlerMixin, _approval_category_for


def _mixin() -> ToolHandlerMixin:
    return ToolHandlerMixin.__new__(ToolHandlerMixin)


def _ctx(agent_id=None, categories=None, work_item_id=None) -> SimpleNamespace:
    ac, _, _ = build_governed_identity({"agent_id": agent_id} if agent_id else {}, "sess")
    return SimpleNamespace(
        agent_context=ac,
        requires_approval_before=categories or [],
        work_item_id=work_item_id,
    )


# --- build_governed_identity ----------------------------------------------


def test_build_governed_identity_extracts_all():
    ac, wid, cats = build_governed_identity(
        {"agent_id": "research_agent", "work_item_id": "wi-1", "requires_approval_before": ["pushing commits"]},
        "sess-1",
    )
    assert ac is not None and ac.agent_id == "research_agent" and ac.session_id == "sess-1"
    assert wid == "wi-1"
    assert cats == ["pushing commits"]


def test_build_governed_identity_empty_when_absent():
    ac, wid, cats = build_governed_identity({}, "sess-1")
    assert ac is None and wid is None and cats == []


# --- approval category matcher --------------------------------------------


def test_approval_category_matches_exact_and_prefix():
    assert _approval_category_for("git_push", ["pushing commits"]) == "pushing commits"
    assert _approval_category_for("deploy_service", ["publishing"]) == "publishing"  # prefix
    assert _approval_category_for("web_search", ["pushing commits"]) is None
    assert _approval_category_for("git_push", []) is None  # category not declared
    assert _approval_category_for("bash", ["unknown category"]) is None


# --- #11159: governed identity → forbidden_work bites ----------------------


def test_governed_agent_context_blocks_forbidden_tool():
    """A run carrying agent_id=research_agent now hard-blocks bash at the seam."""
    mixin = _mixin()
    results: list[dict] = []
    msg = mixin._enforce_forbidden_work({"name": "bash"}, _ctx(agent_id="research_agent"), results)
    assert msg is not None
    assert msg.metadata.get("forbidden_by_manifest") is True


# --- #11160: work-item approval gate --------------------------------------


def test_work_item_approval_holds_declared_category():
    mixin = _mixin()
    results: list[dict] = []
    msg = mixin._enforce_work_item_approval(
        {"name": "git_push"}, _ctx(categories=["pushing commits"], work_item_id="wi-1"), results
    )
    assert msg is not None
    assert msg.type == "approval_required"
    assert msg.metadata["category"] == "pushing commits"
    assert results[0]["status"] == "pending_approval"
    assert results[0]["work_item_id"] == "wi-1"


def test_work_item_approval_noop_without_declaration():
    mixin = _mixin()
    results: list[dict] = []
    assert mixin._enforce_work_item_approval({"name": "git_push"}, _ctx(), results) is None
    assert results == []


@pytest.mark.asyncio
async def test_dispatch_holds_approval_gated_tool():
    """End-to-end: a declared 'destructive operations' gate holds bash at dispatch."""
    mixin = _mixin()
    results: list[dict] = []
    messages = []
    async for item in mixin._dispatch_tool_call(
        {"name": "bash", "params": {"command": "rm -rf /"}},
        "s",
        "t",
        "http://x",
        "m",
        results,
        [],
        ctx=_ctx(categories=["destructive operations"], work_item_id="wi-9"),
    ):
        messages.append(item)
    assert len(messages) == 1
    assert messages[0].type == "approval_required"
    assert results[0]["status"] == "pending_approval"
