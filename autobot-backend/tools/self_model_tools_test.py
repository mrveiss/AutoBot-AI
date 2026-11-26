# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``query_self_model`` against a fixture graph (#22278)."""

import pytest

from tools import self_model_tools
from tools.tool_records import REGISTRY_TOOLS, SELF_MODEL_QUERY_TOOL_NAME
from tools.tool_registry import ToolRegistry


def _entity(kind, name, **fields):
    base = {
        "kind": kind,
        "name": name,
        "status": "declared",
        "last_seen": "2026-01-01T00:00:00+00:00",
        "node_id": None,
        "version": None,
        "entity_key": f"{kind}:{name}",
        "parent_key": None,
        "attrs": {},
        "available": True,
        "unavailable_because": [],
    }
    return {**base, **fields}


#: A permitted tool (no permission needed) on node n1 needing ffmpeg; a shell-gated tool needing git; strays.
GRAPH = {
    "revision": 7,
    "total": 9,
    "entities": [
        _entity("service", "worker-node"),
        _entity(
            "tool",
            "transcode",
            node_id="n1",
            parent_key="service:worker-node",
            attrs={"required_permission": None, "requires": ["ffmpeg"]},
        ),
        _entity(
            "tool",
            "shell",
            node_id="n2",
            parent_key="service:worker-node",
            attrs={"required_permission": "allow_shell_execute", "requires": ["git"]},
        ),
        _entity("node", "n1", node_id="n1"),
        _entity("node", "n2", node_id="n2"),
        _entity("node", "n3", node_id="n3"),
        _entity("command", "ffmpeg", status="absent", node_id="n1"),
        _entity("command", "git", node_id="n2"),
        _entity("package", "numpy", node_id="n3"),
    ],
}


@pytest.fixture(autouse=True)
def role(monkeypatch):
    """The caller's role, as the user store would answer; a test sets ``role["is"]``."""
    state = {"is": "admin"}

    async def fake_role(user_id):
        return state["is"]

    monkeypatch.setattr(self_model_tools, "role_for_user_id", fake_role)
    return state


@pytest.fixture
def seen(monkeypatch):
    calls = []

    async def fake(filters):
        calls.append(filters)
        return GRAPH

    monkeypatch.setattr(self_model_tools, "query_entities", fake)
    return calls


def _names(result):
    return {line.split(" | ")[0] for line in result["result"].splitlines()[1:]}


@pytest.mark.asyncio
async def test_permitted_tool_and_its_dependencies_are_visible_with_status(seen, role):
    role["is"] = "user"
    result = await ToolRegistry().query_self_model({}, "user-1")
    assert result["status"] == "success"
    assert {"tool transcode", "service worker-node", "node n1", "command ffmpeg"} <= _names(result)
    assert "command ffmpeg | status=absent | last_seen=2026-01-01T00:00:00+00:00 | node=n1" in result["result"]


@pytest.mark.asyncio
async def test_unpermitted_tool_and_its_exclusive_dependencies_are_hidden(seen, role):
    role["is"] = "user"
    names = _names(await ToolRegistry().query_self_model({}, "user-1"))
    assert not names & {"tool shell", "node n2", "command git", "node n3", "package numpy"}


@pytest.mark.asyncio
async def test_a_role_holding_the_permission_sees_the_tool_and_what_it_runs_on(seen, role):
    names = _names(await ToolRegistry().query_self_model({}, "admin-1"))
    assert {"tool shell", "node n2", "command git"} <= names and "node n3" not in names


@pytest.mark.asyncio
async def test_filters_apply_to_what_is_visible(seen, role):
    role["is"] = "user"
    names = _names(await ToolRegistry().query_self_model({"kind": "command", "node_id": "n2"}, "user-1"))
    assert names == set()


@pytest.mark.asyncio
async def test_an_unknown_account_sees_nothing(seen, role):
    role["is"] = None
    result = await ToolRegistry().query_self_model({}, "ghost")
    assert result["status"] == "error"


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
    result = await registry.execute_tool("query_self_model", {"limit": 3}, "user-1")
    assert len(result["result"].splitlines()) == 1 + 3
    assert self_model_tools._clamped_limit(10**6) == self_model_tools.MAX_LIMIT


def test_tool_is_in_the_catalogue():
    assert SELF_MODEL_QUERY_TOOL_NAME in REGISTRY_TOOLS
