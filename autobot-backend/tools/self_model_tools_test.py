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


def _slm(graph):
    """A fake SLM: applies the kind, name, node_id and status filters, then pages with limit and offset."""

    async def fake(filters):
        rows = [
            e
            for e in graph["entities"]
            if all(
                [
                    not filters.get("kind") or e["kind"] == filters["kind"],
                    not filters.get("name") or filters["name"].lower() in e["name"].lower(),
                    not filters.get("node_id") or e.get("node_id") == filters["node_id"],
                    not filters.get("status") or e["status"] == filters["status"],
                ]
            )
        ]
        start = int(filters.get("offset", 0))
        return {
            "revision": graph["revision"],
            "total": len(rows),
            "entities": rows[start : start + int(filters["limit"])],
        }

    return fake


@pytest.fixture
def seen(monkeypatch):
    calls = []
    fake = _slm(GRAPH)

    async def recording(filters):
        calls.append(filters)
        return await fake(filters)

    monkeypatch.setattr(self_model_tools, "query_entities", recording)
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


@pytest.mark.asyncio
async def test_filters_are_pushed_to_the_slm_not_applied_to_a_crowded_page(seen, role):
    result = await ToolRegistry().query_self_model({"kind": "service", "name": "worker"}, "admin-1")
    assert _names(result) == {"service worker-node"}
    assert {"kind": "service", "name": "worker", "limit": self_model_tools.SLM_PAGE, "offset": 0} in seen


@pytest.mark.asyncio
async def test_a_set_larger_than_a_page_is_read_in_pages(monkeypatch, role):
    many = {"revision": 1, "entities": [_entity("route", f"r{i}") for i in range(5)] + GRAPH["entities"]}
    monkeypatch.setattr(self_model_tools, "query_entities", _slm(many))
    monkeypatch.setattr(self_model_tools, "SLM_PAGE", 2)
    names = _names(await ToolRegistry().query_self_model({"kind": "route", "limit": 100}, "admin-1"))
    assert names == {f"route r{i}" for i in range(5)}


@pytest.mark.asyncio
async def test_a_set_the_read_could_not_finish_is_reported_as_incomplete(monkeypatch, role):
    many = {"revision": 1, "entities": [_entity("route", f"r{i}") for i in range(6)]}
    monkeypatch.setattr(self_model_tools, "query_entities", _slm(many))
    monkeypatch.setattr(self_model_tools, "SLM_PAGE", 2)
    monkeypatch.setattr(self_model_tools, "MAX_PAGES", 2)
    text = (await ToolRegistry().query_self_model({"kind": "route"}, "admin-1"))["result"]
    assert "4 of 4 visible" in text and "holds more matching rows than were read" in text


@pytest.mark.asyncio
async def test_the_header_counts_visible_matches_not_what_the_page_cut(seen, role):
    text = (await ToolRegistry().query_self_model({"kind": "node", "limit": 1}, "admin-1"))["result"]
    assert text.splitlines()[0].startswith("1 of 2 visible matching entities")


@pytest.mark.asyncio
async def test_real_tool_records_make_their_serving_node_visible(monkeypatch, role):
    """End to end over ``tool_records()``: a permitted real tool reveals the node it is served from."""
    from tools.tool_records import tool_records

    role["is"] = "user"
    records = [r for r in tool_records() if r["node_id"]]
    host = records[0]["node_id"]
    tools = [
        _entity(
            "tool", r["name"], node_id=r["node_id"], parent_key=f"service:{r['serving_service']}", attrs=r["fields"]
        )
        for r in records
    ]
    graph = {"revision": 1, "entities": [*tools, _entity("node", host, node_id=host), _entity("node", "stranger")]}
    monkeypatch.setattr(self_model_tools, "query_entities", _slm(graph))
    names = _names(await ToolRegistry().query_self_model({"kind": "node"}, "user-1"))
    assert names == {f"node {host}"}


@pytest.mark.asyncio
async def test_the_shell_tool_is_hidden_from_a_role_without_shell_permission(monkeypatch, role):
    from tools.tool_records import tool_records

    role["is"] = "user"
    shell = next(r for r in tool_records() if r["name"] == "execute_command")
    graph = {"revision": 1, "entities": [_entity("tool", "execute_command", attrs=shell["fields"])]}
    monkeypatch.setattr(self_model_tools, "query_entities", _slm(graph))
    names = _names(await ToolRegistry().query_self_model({"kind": "tool"}, "user-1"))
    assert "tool execute_command" not in names
