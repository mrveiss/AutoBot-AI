# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""STRICT routes answer another user's conversation exactly like an unknown one (#20413).

Trace and the five conversation-file owner routes are pinned here (turn cancel is in
``chat_turn_17273_test.py``): status and body are byte-identical for a foreign and an unknown id, the owner
succeeds, and an unreadable owner stays 403 for both. The admin-only file routes reveal nothing either: a
non-admin gets the same 403 for an existing and an unknown id, and an admin passes the gate.
"""

# flake8: noqa: F811 -- fixtures imported from the sibling test modules are redefined as test arguments

from __future__ import annotations

import pytest

from api import chat_trace_19963_test as trace_tests
from api.conversation_files_owner_routes_20195_test import _call
from api.conversation_files_owner_upload_20133_test import _ADMIN, _ALICE, _BOB, _other_routes, world  # noqa: F401
from api.conversation_files_real_manager_20225_test import _SESSION, _seed, real  # noqa: F401
from security.session_posture import deny_unreadable_owner

_PANEL = ("list", "preview", "download", "delete")


# ---- trace -----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trace_foreign_and_unknown_are_byte_identical(monkeypatch):
    trace_tests._as_user(monkeypatch, "bob", "alice", trace_tests.HELD_TURN)
    foreign = await trace_tests._get("alices-chat")
    trace_tests._as_user(monkeypatch, "bob", None, [])
    unknown = await trace_tests._get("no-such-chat")

    assert foreign.status_code == unknown.status_code == 404
    assert foreign.content == unknown.content


@pytest.mark.asyncio
async def test_trace_owner_succeeds(monkeypatch):
    trace_tests._as_user(monkeypatch, "alice", "alice", trace_tests.HELD_TURN)

    assert (await trace_tests._get("alices-chat")).status_code == 200


@pytest.mark.asyncio
async def test_trace_unreadable_owner_stays_403_for_any_id(monkeypatch):
    trace_tests._as_user(monkeypatch, "alice", "alice", trace_tests.HELD_TURN)

    async def _boom(session_id, *_a, **_k):
        raise deny_unreadable_owner(session_id, "alice")

    monkeypatch.setattr("security.session_posture.read_owner", _boom)

    first, second = await trace_tests._get("alices-chat"), await trace_tests._get("no-such-chat")

    assert first.status_code == second.status_code == 403
    assert first.content == second.content


# ---- conversation-file owner routes ----------------------------------------------------------------------------


@pytest.mark.parametrize("kind", _PANEL)
def test_owner_routes_foreign_and_unknown_are_byte_identical(real, kind):
    file_id = _seed(real)
    real.user = dict(_BOB)
    foreign = _call(real, kind, file_id)
    unknown = _call(real, kind, file_id, session="no-such-chat")

    assert foreign.status_code == unknown.status_code == 404
    assert foreign.content == unknown.content


@pytest.mark.parametrize("kind", _PANEL)
def test_owner_routes_owner_succeeds(real, kind):
    file_id = _seed(real)
    real.user = dict(_ALICE)

    assert _call(real, kind, file_id).status_code == 200


def test_owner_upload_foreign_and_unknown_are_byte_identical(world):
    world.user, world.owner = dict(_BOB), "alice"
    foreign = world.client.post("/api/conversation/s-1/upload", files={"file": ("a.txt", b"x")})
    world.exists = False
    world.owner = None
    unknown = world.client.post("/api/conversation/no-such/upload", files={"file": ("a.txt", b"x")})

    assert foreign.status_code == unknown.status_code == 404
    assert foreign.content == unknown.content


@pytest.mark.parametrize("kind", _PANEL)
def test_owner_routes_unreadable_owner_stays_403_for_any_id(real, kind, monkeypatch):
    file_id = _seed(real)
    real.user = dict(_ALICE)

    async def _boom(session_id, *_a, **_k):
        raise deny_unreadable_owner(session_id, "alice")

    monkeypatch.setattr("security.session_posture.read_owner", _boom)
    first = _call(real, kind, file_id)
    second = _call(real, kind, file_id, session="no-such-chat")

    assert first.status_code == second.status_code == 403
    assert first.content == second.content


# ---- admin-only file routes (the recorded exception) -----------------------------------------------------------


def _admin_only_requests(world):
    for route in _other_routes(world):
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            yield method, route.path


def test_admin_only_routes_give_a_non_admin_the_same_403_for_existing_and_unknown(world):
    world.user, world.owner = dict(_BOB), "alice"
    for method, path in _admin_only_requests(world):
        fill = path.replace("{file_id}", "f1")
        existing = world.client.request(method, "/api" + fill.replace("{session_id}", "s-1"))
        world.exists = False
        unknown = world.client.request(method, "/api" + fill.replace("{session_id}", "no-such"))
        world.exists = True
        assert existing.status_code == unknown.status_code == 403, (method, path)
        assert existing.content == unknown.content, (method, path)


def test_an_admin_passes_the_gate_on_every_admin_only_route(world):
    world.user, world.owner = dict(_ADMIN), "alice"
    for method, path in _admin_only_requests(world):
        response = world.client.request(method, "/api" + path.replace("{session_id}", "s-1").replace("{file_id}", "f1"))
        assert response.status_code not in (401, 403), (method, path, response.status_code)
