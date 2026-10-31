# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``DELETE /chats/{chat_id}`` against a REAL ``ChatHistoryManager`` (#18316 AC2, AC4).

The original bug -- ``delete_session`` called without ``await`` -- answered 200 while
the session survived, and a fake history object cannot show that: it is the real
manager's coroutine that was dropped. Here the real class writes its real session files
under ``tmp_path`` with a fakeredis cache in front, the real two-posture ownership
validator decides, and ``delete_chat_by_id`` itself runs. "Gone" is asserted on the
store: the session file, the Redis cache entry and ``get_session``.

The harness is the #18293 end-to-end world (``session_delete_legacy_transcript_18293_test``);
it stubs only the caller's identity, the side cleanups a delete also performs (terminal,
KB, conversation files, events, audit) and the Postgres write of a #17038 proposal.
"""

from pathlib import Path

import fakeredis
import pytest
from fastapi import HTTPException

import api.chat as chat_api
import api.chat_sessions as chat_sessions
from api.session_delete_legacy_transcript_18293_test import ALICE, BOB, OWN_ID, _World


@pytest.fixture
def world(tmp_path, monkeypatch) -> _World:
    built = _World(tmp_path, monkeypatch)
    built.history.redis_client = fakeredis.FakeRedis()  # the manager's real cache path, in memory
    return built


def _session_file(world: _World, session_id: str) -> Path:
    return Path(world.history._get_chats_directory()) / f"{session_id}_chat.json"


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


async def _delete_chat(world: _World, session_id: str, ownership: dict):
    route = chat_api.delete_chat_by_id.__wrapped__
    return await route(session_id, {"username": world.caller}, world.request(), ownership)


async def _alices_session(world: _World) -> Path:
    await world.create(OWN_ID)
    turns = [
        {"sender": "user", "text": "keep this", "messageType": "default"},
        {"sender": "assistant", "text": "kept", "messageType": "response"},
    ]
    await world.save(OWN_ID, await world.ownership(OWN_ID), turns)
    await world.history.load_session(OWN_ID)  # warm the Redis cache, so "gone" covers it too
    return _session_file(world, OWN_ID)


@pytest.mark.asyncio
async def test_delete_chat_by_id_really_removes_the_session(world) -> None:
    session_file = await _alices_session(world)
    assert session_file.exists() and world.history.redis_client.exists(f"chat:session:{OWN_ID}")

    response = await _delete_chat(world, OWN_ID, await world.ownership(OWN_ID))

    assert response.status_code == 200
    assert not session_file.exists()
    assert not world.history.redis_client.exists(f"chat:session:{OWN_ID}")
    assert await world.history.get_session(OWN_ID) is None
    assert await world.history.load_session(OWN_ID) == []


@pytest.mark.asyncio
async def test_bob_cannot_delete_alices_chat_and_nothing_of_hers_is_touched(world) -> None:
    session_file = await _alices_session(world)
    before = _bytes(session_file)
    world.caller = BOB

    with pytest.raises(HTTPException) as raised:
        await _delete_chat(world, OWN_ID, await world.ownership(OWN_ID))

    assert raised.value.status_code == 403
    assert _bytes(session_file) == before
    world.caller = ALICE
    assert [m["text"] for m in await world.history.load_session(OWN_ID)] == ["keep this", "kept"]
    chat_sessions._handle_conversation_files.assert_not_awaited()  # her conversation files untouched
