# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An imported conversation must be owned, and must not overwrite someone else's (#14026, #14033).

Two defects that compounded:

* ``import_conversation`` took no user identity and called ``save_session``
  with no metadata, so every import produced an **ownerless** session.
* ``conversation_files.py`` and ``websockets.py`` read "no owner" as "legacy
  session, allow access", so those ownerless sessions were readable by anyone.

The second half is #14033: ``get_session_owner`` returned ``None`` for four
different states — file absent, no owner recorded, ``OSError``, and a decrypt
failure — so a caller could not tell "nobody owns this" from "I could not find
out". A transient read error therefore granted access. It now raises
``SessionOwnerUnreadable`` for the unknowable cases and reserves ``None`` for a
genuine "no owner recorded".

``on_conflict="replace"`` had no ownership check at all, so an import carrying a
known ``session_id`` could destroy another user's conversation.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from security.session_owner_errors import SessionOwnerUnreadable
from security.session_owner_index import owned_session_ids
from security.session_owner_index_21664_test import _Store
from security.session_owner_index_21664_test import _validator as _index_validator
from security.session_posture import UNREADABLE_OWNER_DETAIL
from services import conversation_export
from services.conversation_export import import_conversation

_DOCUMENT: Dict[str, Any] = {
    "format": "autobot-conversation-v1",
    "version": "1.0",
    "session_id": "sess-abc",
    "name": "imported",
    "messages": [{"role": "user", "content": "hi"}],
}

_ALICE = {"username": "alice", "user_id": "u-1"}
_BOB = {"username": "bob", "user_id": "u-2"}


@pytest.fixture(autouse=True)
def owner_index(monkeypatch):
    """alice's owner index, marked complete with one older session (#21664); no real Redis."""
    store = _Store(members={"s-old"}, marked=True)
    validator = _index_validator(store)
    monkeypatch.setattr(conversation_export, "_owner_validator", AsyncMock(return_value=validator))
    return validator


def _manager(*, exists: bool = False, owner: Any = None, owner_raises: bool = False):
    manager = AsyncMock()
    manager.save_session = AsyncMock()
    # `_session_exists` calls load_session and treats a non-empty message list
    # as "exists" — mocking anything else makes every conflict test skip the
    # branch it is meant to exercise.
    manager.load_session = AsyncMock(return_value=[{"role": "user", "content": "existing"}] if exists else [])
    if owner_raises:
        manager.get_session_owner = AsyncMock(side_effect=SessionOwnerUnreadable("sess-abc"))
    else:
        manager.get_session_owner = AsyncMock(return_value=owner)
    return manager


@pytest.mark.asyncio
async def test_an_import_stamps_the_importing_user_as_owner() -> None:
    """An ownerless session is readable by anyone — that is the whole defect."""
    manager = _manager()

    result = await import_conversation(manager, dict(_DOCUMENT), user_data=_ALICE)

    assert result["success"] is True, result["message"]
    metadata = manager.save_session.call_args.kwargs["metadata"]
    assert metadata is not None, "import produced a session with no owner (#14026)"
    assert metadata["owner"] == "alice"
    assert metadata["username"] == "alice"
    assert metadata["user_id"] == "u-1"


@pytest.mark.asyncio
async def test_replace_refuses_to_overwrite_another_users_session() -> None:
    manager = _manager(exists=True, owner="alice")

    with pytest.raises(HTTPException) as refused:
        await import_conversation(manager, dict(_DOCUMENT), on_conflict="replace", user_data=_BOB)

    assert refused.value.status_code == 404
    manager.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_replace_allows_the_owner_to_overwrite_their_own_session() -> None:
    manager = _manager(exists=True, owner="alice")

    result = await import_conversation(manager, dict(_DOCUMENT), on_conflict="replace", user_data=_ALICE)

    assert result["success"] is True
    manager.save_session.assert_awaited()


@pytest.mark.asyncio
async def test_replace_refuses_when_ownership_cannot_be_read() -> None:
    """Unreadable is not unowned — the #14033 distinction, applied.

    Without this an OSError reads as "no owner", and "no owner" was the branch
    that let the overwrite through.
    """
    manager = _manager(exists=True, owner_raises=True)

    with pytest.raises(HTTPException) as denied:
        await import_conversation(manager, dict(_DOCUMENT), on_conflict="replace", user_data=_BOB)

    assert denied.value.status_code == 403 and denied.value.detail == UNREADABLE_OWNER_DETAIL
    manager.save_session.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("on_conflict", ["replace", "merge"])
async def test_an_import_over_an_ownerless_session_is_a_404_for_a_non_admin(on_conflict) -> None:
    """#21668: nobody claims a session with no owner by writing; the answer is a missing session's 404."""
    manager = _manager(exists=True, owner=None)

    with pytest.raises(HTTPException) as refused:
        await import_conversation(manager, dict(_DOCUMENT), on_conflict=on_conflict, user_data=_BOB)

    assert refused.value.status_code == 404
    manager.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_admin_import_over_an_ownerless_session_is_refused_not_stamped(owner_index) -> None:
    """#21668: an admin's owner assignment goes through the approval queue (#17038), not an import."""
    manager = _manager(exists=True, owner=None)

    result = await import_conversation(
        manager, dict(_DOCUMENT), on_conflict="replace", user_data={"username": "root", "role": "admin"}
    )

    assert result["success"] is False and result["conflict"] is True
    assert "approval queue" in result["message"]
    manager.save_session.assert_not_awaited()
    owner_index.set_session_owner.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_merge_import_into_another_users_session_is_refused() -> None:
    """The default conflict path (no replace) must not merge into someone else's session (#20908)."""
    manager = _manager(exists=True, owner="alice")

    with pytest.raises(HTTPException) as refused:
        await import_conversation(manager, dict(_DOCUMENT), on_conflict="merge", user_data=_BOB)

    assert refused.value.status_code == 404
    manager.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_merge_import_is_refused_when_the_owner_is_unreadable() -> None:
    manager = _manager(exists=True, owner_raises=True)

    with pytest.raises(HTTPException) as denied:
        await import_conversation(manager, dict(_DOCUMENT), on_conflict="merge", user_data=_BOB)

    assert denied.value.status_code == 403 and denied.value.detail == UNREADABLE_OWNER_DETAIL
    manager.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unreadable_store_fails_closed_instead_of_reading_as_no_session() -> None:
    manager = _manager()
    manager.load_session = AsyncMock(side_effect=OSError("disk gone"))

    with pytest.raises(OSError):
        await import_conversation(manager, dict(_DOCUMENT), on_conflict="replace", user_data=_BOB)

    manager.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_checks_and_the_save_run_inside_the_session_lease(monkeypatch) -> None:
    from contextlib import asynccontextmanager

    from services import conversation_export

    events: list[str] = []

    @asynccontextmanager
    async def _lease(session_id, operation, wait_s=None):
        events.append(f"enter:{operation}")
        yield None
        events.append("exit")

    monkeypatch.setattr(conversation_export, "session_lease", _lease)
    manager = _manager(exists=True, owner="alice")
    manager.save_session.side_effect = lambda **_: events.append("save")

    await import_conversation(manager, dict(_DOCUMENT), on_conflict="replace", user_data=_ALICE)

    assert events == ["enter:import", "save", "exit"]


# --- #21664: an import enters the importer's owner index ---------------------------------


@pytest.mark.asyncio
async def test_an_import_into_a_marked_index_is_listed(owner_index) -> None:
    result = await import_conversation(_manager(), dict(_DOCUMENT), user_data=_ALICE)

    assert result["success"] is True
    listed = await owned_session_ids(owner_index, "alice", ["s-old", "sess-abc"], AsyncMock())
    assert listed == {"s-old", "sess-abc"}


@pytest.mark.asyncio
async def test_replacing_ones_own_session_keeps_it_indexed(owner_index) -> None:
    await import_conversation(
        _manager(exists=True, owner="alice"), dict(_DOCUMENT), on_conflict="replace", user_data=_ALICE
    )

    owner_index.set_session_owner.assert_awaited_once_with("sess-abc", "alice")


# --- #21731: skip answers a non-owner exactly as a missing session does ------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["alice", None])
async def test_a_skip_import_by_a_non_owner_is_the_404_of_a_missing_session(owner) -> None:
    manager = _manager(exists=True, owner=owner)

    with pytest.raises(HTTPException) as refused:
        await import_conversation(manager, dict(_DOCUMENT), on_conflict="skip", user_data=_BOB)

    assert refused.value.status_code == 404
    manager.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_owner_skipping_their_own_session_still_reports_a_conflict() -> None:
    manager = _manager(exists=True, owner="alice")

    result = await import_conversation(manager, dict(_DOCUMENT), on_conflict="skip", user_data=_ALICE)

    assert result["success"] is False and result["conflict"] is True
    manager.save_session.assert_not_awaited()
