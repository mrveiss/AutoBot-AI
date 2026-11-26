# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``query_self_model`` against a fixture graph (#22278)."""

import pytest

from tools import self_model_tools
from tools.tool_records import REGISTRY_TOOLS, SELF_MODEL_QUERY_TOOL_NAME
from tools.tool_registry import ToolRegistry

GRAPH = {
    "revision": 7,
    "total": 2,
    "entities": [
        {
            "kind": "command",
            "name": "ffmpeg",
            "status": "absent",
            "last_seen": "2026-01-01T00:00:00+00:00",
            "node_id": "n1",
            "version": None,
            "available": True,
            "unavailable_because": [],
        },
        {
            "kind": "tool",
            "name": "transcode",
            "status": "declared",
            "last_seen": "2026-01-02T00:00:00+00:00",
            "node_id": "n1",
            "version": "1",
            "available": False,
            "unavailable_because": ["ffmpeg"],
        },
    ],
}


@pytest.fixture
def seen(monkeypatch):
    calls = []

    async def fake(filters):
        calls.append(filters)
        return GRAPH

    monkeypatch.setattr(self_model_tools, "query_entities", fake)
    return calls


@pytest.mark.asyncio
async def test_returns_status_last_seen_and_unavailability_for_each_entity(seen):
    result = await ToolRegistry().query_self_model({"node_id": "n1", "status": "absent"}, "user-1")
    assert result["status"] == "success"
    assert "command ffmpeg | status=absent | last_seen=2026-01-01T00:00:00+00:00 | node=n1" in result["result"]
    assert "UNAVAILABLE (needs ffmpeg)" in result["result"]
    assert seen[0]["node_id"] == "n1" and seen[0]["status"] == "absent" and seen[0]["limit"] == 25


@pytest.mark.asyncio
async def test_no_user_sees_nothing_and_the_model_is_not_queried(seen):
    result = await ToolRegistry().query_self_model({"kind": "tool"}, None)
    assert result["status"] == "error" and seen == []


@pytest.mark.asyncio
async def test_unreachable_self_model_is_an_error_not_an_empty_answer(monkeypatch):
    async def down(filters):
        raise self_model_tools.SelfModelUnavailable("SLM client is not initialised")

    monkeypatch.setattr(self_model_tools, "query_entities", down)
    result = await ToolRegistry().query_self_model({}, "user-1")
    assert result["status"] == "error" and "not reachable" in result["result"]


@pytest.mark.asyncio
async def test_limit_is_clamped_and_dispatch_reaches_the_tool(seen):
    registry = ToolRegistry()
    await registry.execute_tool("query_self_model", {"limit": 10**6}, "user-1")
    assert seen[0]["limit"] == self_model_tools.MAX_LIMIT


def test_tool_is_in_the_catalogue():
    assert SELF_MODEL_QUERY_TOOL_NAME in REGISTRY_TOOLS
