# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""memory.session_list / memory.session_read are owner-scoped (#11137). Synthetic data only."""

import json
from unittest.mock import patch

import pytest

from autobot_memory_graph.owner_scope import OwnerScope
from autobot_shared.ssot_config import config
from mcp_server.autobot_server import AutoBotMCPServer
from mcp_server.principal import bind_owner, unbind_owner

SECRET = "sess-test-secret"  # pragma: allowlist secret
TOKEN = f"{SECRET}:memory"
ALICE = OwnerScope.for_user("alice")
BOB = OwnerScope.for_user("bob")

CHUNKS = [
    ("a_t1_assistant", "alice reply", {"session_id": "s-a", "turn": 1, "timestamp": "2026-01-02", "user_id": "alice"}),
    ("a_t0_user", "alice ask", {"session_id": "s-a", "turn": 0, "timestamp": "2026-01-01", "user_id": "alice"}),
    ("b_t0_user", "bob secret", {"session_id": "s-b", "turn": 0, "timestamp": "2026-01-03", "user_id": "bob"}),
    ("n_t0_user", "no owner", {"session_id": "s-n", "turn": 0, "timestamp": "2026-01-04"}),
]


def _match(meta, where):
    if "$and" in where:
        return all(_match(meta, w) for w in where["$and"])
    return all(meta.get(k) == cond["$eq"] for k, cond in where.items())


class FakeCollection:
    """Honours the ChromaDB ``where`` filter, so a missing owner clause would leak and fail a test."""

    def __init__(self):
        self.wheres = []

    async def get(self, where=None, include=None, limit=None):
        self.wheres.append(where)
        rows = [c for c in CHUNKS if where is None or _match(c[2], where)][:limit]
        return {"ids": [r[0] for r in rows], "documents": [r[1] for r in rows], "metadatas": [r[2] for r in rows]}


@pytest.fixture(autouse=True)
def _env():
    coll = FakeCollection()

    async def _get_collection(self):
        return coll

    with (
        patch.object(config.misc, "mcp_token", SECRET),
        patch("memory.verbatim_store.VerbatimStore._get_collection", _get_collection),
    ):
        yield coll


async def _call(owner, name, arguments):
    bound = bind_owner(owner)
    try:
        resp = await AutoBotMCPServer()._dispatch_tool(name, arguments, ["memory"], 1)
    finally:
        unbind_owner(bound)
    return resp


def _result(resp):
    return json.loads(resp["result"]["content"][0]["text"])


@pytest.mark.asyncio
async def test_list_returns_only_the_callers_sessions():
    out = _result(await _call(ALICE, "memory.session_list", {}))
    assert [s["session_id"] for s in out["sessions"]] == ["s-a"]
    assert out["sessions"][0]["chunks"] == 2
    assert (out["sessions"][0]["first_at"], out["sessions"][0]["last_at"]) == ("2026-01-01", "2026-01-02")
    assert "bob" not in json.dumps(out) and "no owner" not in json.dumps(out)


@pytest.mark.asyncio
async def test_read_returns_own_session_in_turn_order():
    out = _result(await _call(ALICE, "memory.session_read", {"session_id": "s-a"}))
    assert [c["text"] for c in out["chunks"]] == ["alice ask", "alice reply"]


@pytest.mark.asyncio
async def test_another_owners_session_is_not_returned(_env):
    out = _result(await _call(ALICE, "memory.session_read", {"session_id": "s-b"}))
    assert out["error"] == "Session not found"
    assert "bob secret" not in json.dumps(out)
    assert all("alice" in json.dumps(w) for w in _env.wheres)  # the owner is in the store query itself


@pytest.mark.asyncio
async def test_unowned_chunks_are_invisible_and_bob_sees_his_own():
    assert _result(await _call(ALICE, "memory.session_read", {"session_id": "s-n"}))["error"] == "Session not found"
    out = _result(await _call(BOB, "memory.session_list", {}))
    assert [s["session_id"] for s in out["sessions"]] == ["s-b"]


@pytest.mark.asyncio
async def test_no_principal_fails_closed():
    resp = await AutoBotMCPServer().handle_request(
        "tools/call", {"name": "memory.session_list", "arguments": {}}, TOKEN, client_ip="stdio"
    )
    assert resp["error"]["code"] == -32003


@pytest.mark.asyncio
async def test_behind_the_memory_scope_only():
    server = AutoBotMCPServer()
    resp = await server.handle_request("tools/call", {"name": "memory.session_list", "arguments": {}}, f"{SECRET}:kb")
    assert resp["error"]["code"] == -32001
    listed = await server.handle_request("tools/list", {}, TOKEN)
    names = {t["name"] for t in listed["result"]["tools"]}
    assert {"memory.session_list", "memory.session_read", "memory.verbatim_search"} <= names


@pytest.mark.asyncio
async def test_bad_arguments_are_rejected():
    assert (await _call(ALICE, "memory.session_read", {"session_id": ""}))["error"]["code"] == -32602
    assert (await _call(ALICE, "memory.session_list", {"limit": 0}))["error"]["code"] == -32602
