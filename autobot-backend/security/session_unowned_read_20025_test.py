# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Nobody becomes the owner of an existing session by touching it (#20025).

A session with no owner is a defect: an admin may act on it, everyone else sees a missing session,
and nothing is written. Only a write on an id with no session at all may record an owner.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from chat_history.session_file import session_file_exists
from security.session_ownership import SessionOwnershipValidator
from security.session_posture import _strict_owner_check, unowned_access

_USER = {"username": "u", "role": "user"}
_ADMIN = {"username": "a", "role": "admin"}


@pytest.fixture(name="store")
def _store(tmp_path, monkeypatch):
    """A real session file behind the manager's real path rules."""
    manager = MagicMock()
    manager._get_chats_directory.return_value = str(tmp_path)
    monkeypatch.setattr("utils.chat_utils.get_chat_history_manager", lambda _request: manager)
    (tmp_path / "exists_chat.json").write_text(json.dumps({"metadata": {}}), encoding="utf-8")
    return manager


def _request(method: str) -> MagicMock:
    return MagicMock(method=method)


@pytest.mark.parametrize("method", ["GET", "HEAD", "POST", "PUT", "DELETE"])
@pytest.mark.asyncio
async def test_a_non_admin_on_an_existing_ownerless_session_gets_a_missing_session(store, method) -> None:
    with pytest.raises(HTTPException) as denied:
        await unowned_access("exists", _USER, _request(method))
    assert denied.value.status_code == 404 and denied.value.detail == "Chat session not found"


@pytest.mark.asyncio
async def test_an_admin_may_act_and_gets_no_claim(store) -> None:
    verdict = await unowned_access("exists", _ADMIN, _request("DELETE"))
    assert verdict["authorized"] is True and verdict["reason"] == "admin_unowned_access"


@pytest.mark.asyncio
async def test_no_session_a_read_is_a_quiet_404_and_a_write_may_create_it(store, caplog) -> None:
    with pytest.raises(HTTPException):
        await unowned_access("absent", _USER, _request("GET"))
    assert "has no owner" not in caplog.text, "any user could emit error lines with a made-up id"
    assert await unowned_access("absent", _USER, _request("POST")) is None


@pytest.mark.asyncio
async def test_not_knowing_whether_it_exists_denies(store) -> None:
    store._get_chats_directory.side_effect = OSError("gone")
    with pytest.raises(HTTPException) as denied:
        await unowned_access("exists", _USER, _request("POST"))
    assert denied.value.status_code == 403


def _validator() -> SessionOwnershipValidator:
    validator = SessionOwnershipValidator.__new__(SessionOwnershipValidator)
    validator._durable_owner = AsyncMock(return_value=None)
    validator.set_session_owner = AsyncMock()
    return validator


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
@pytest.mark.asyncio
async def test_the_default_path_writes_no_owner_on_an_existing_session(store, method) -> None:
    validator = _validator()
    with pytest.raises(HTTPException):
        await validator._owner_when_cache_is_empty("exists", "u", _USER, _request(method))
    validator.set_session_owner.assert_not_awaited()


@pytest.mark.asyncio
async def test_contrast_a_first_write_on_a_new_id_records_its_owner(store) -> None:
    validator = _validator()
    owner, early = await validator._owner_when_cache_is_empty("absent", "u", _USER, _request("POST"))
    validator.set_session_owner.assert_awaited_once()
    assert owner == "u" and early["reason"] == "legacy_migration"


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
@pytest.mark.asyncio
async def test_the_strict_path_denies_an_existing_ownerless_session(store, method) -> None:
    store.get_session_owner = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as denied:
        await _strict_owner_check("exists", _USER, _request(method))
    assert denied.value.status_code == 404


@pytest.mark.asyncio
async def test_the_store_answers_from_the_real_file(store) -> None:
    assert await session_file_exists(store, "exists") is True
    assert await session_file_exists(store, "absent") is False
