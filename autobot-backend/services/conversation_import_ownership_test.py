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

import uuid
from types import SimpleNamespace
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


@pytest.fixture(autouse=True)
def stored_record(monkeypatch):
    """``session_file_exists`` answers from the manager's ``record_exists`` flag instead of the disk."""

    async def _exists(manager, session_id):
        return manager.record_exists and session_id == _DOCUMENT["session_id"]  # a fresh id is always free

    monkeypatch.setattr(conversation_export, "session_file_exists", _exists)


def _manager(
    *,
    exists: bool = False,
    owner: Any = None,
    owner_raises: bool = False,
    empty: bool = False,
):
    manager = AsyncMock()
    manager.save_session = AsyncMock()
    manager.record_exists = exists
    # Existence comes from the stored record (`session_file_exists`, answered by the `stored_record`
    # fixture from `record_exists`), not from the messages; `load_session` only matters for `empty`.
    manager.load_session = AsyncMock(
        return_value=[{"role": "user", "content": "existing"}] if exists and not empty else []
    )
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
    assert result["session_id"] != "sess-abc"  # #21731: a free id is not kept either
    metadata = manager.save_session.call_args.kwargs["metadata"]
    assert metadata is not None, "import produced a session with no owner (#14026)"
    assert metadata["owner"] == "alice"
    assert metadata["username"] == "alice"
    assert metadata["user_id"] == "u-1"


@pytest.mark.asyncio
async def test_replace_never_overwrites_another_users_session() -> None:
    manager = _manager(exists=True, owner="alice")

    result = await import_conversation(manager, dict(_DOCUMENT), on_conflict="replace", user_data=_BOB)

    _assert_saved_under_a_fresh_id(manager, result)


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
async def test_an_import_over_an_ownerless_session_takes_a_fresh_id_for_a_non_admin(
    on_conflict,
) -> None:
    """#21668: nobody claims a session with no owner by writing; #21731: a non-admin gets a fresh id."""
    manager = _manager(exists=True, owner=None)

    result = await import_conversation(manager, dict(_DOCUMENT), on_conflict=on_conflict, user_data=_BOB)

    _assert_saved_under_a_fresh_id(manager, result)


@pytest.mark.asyncio
async def test_an_admin_import_over_an_ownerless_session_is_refused_not_stamped(
    owner_index,
) -> None:
    """#21668: an admin's owner assignment goes through the approval queue (#17038), not an import."""
    manager = _manager(exists=True, owner=None)

    result = await import_conversation(
        manager,
        dict(_DOCUMENT),
        on_conflict="replace",
        user_data={"username": "root", "role": "admin"},
    )

    assert result["success"] is False and result["conflict"] is True
    assert "approval queue" in result["message"]
    manager.save_session.assert_not_awaited()
    owner_index.set_session_owner.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_merge_import_never_merges_into_another_users_session() -> None:
    """The default conflict path (no replace) must not merge into someone else's session (#20908)."""
    manager = _manager(exists=True, owner="alice")

    result = await import_conversation(manager, dict(_DOCUMENT), on_conflict="merge", user_data=_BOB)

    _assert_saved_under_a_fresh_id(manager, result)


@pytest.mark.asyncio
async def test_a_merge_import_is_refused_when_the_owner_is_unreadable() -> None:
    manager = _manager(exists=True, owner_raises=True)

    with pytest.raises(HTTPException) as denied:
        await import_conversation(manager, dict(_DOCUMENT), on_conflict="merge", user_data=_BOB)

    assert denied.value.status_code == 403 and denied.value.detail == UNREADABLE_OWNER_DETAIL
    manager.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unreadable_store_fails_closed_instead_of_reading_as_no_session(
    monkeypatch,
) -> None:
    manager = _manager()

    async def _gone(manager, session_id):
        raise OSError("disk gone")

    monkeypatch.setattr(conversation_export, "session_file_exists", _gone)

    with pytest.raises(OSError):
        await import_conversation(manager, dict(_DOCUMENT), on_conflict="replace", user_data=_BOB)

    manager.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_checks_and_the_save_run_inside_the_session_lease(
    monkeypatch,
) -> None:
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
    listed = await owned_session_ids(owner_index, "alice", ["s-old", result["session_id"]], AsyncMock())
    assert listed == {"s-old", result["session_id"]}


@pytest.mark.asyncio
async def test_replacing_ones_own_session_keeps_it_indexed(owner_index) -> None:
    await import_conversation(
        _manager(exists=True, owner="alice"),
        dict(_DOCUMENT),
        on_conflict="replace",
        user_data=_ALICE,
    )

    owner_index.set_session_owner.assert_awaited_once_with("sess-abc", "alice")


# --- #21731: a non-owner's collision takes a fresh id and answers as a new session does --


def _assert_saved_under_a_fresh_id(manager, result) -> None:
    """The import succeeded without a conflict flag, under a new id; the original session is untouched."""
    assert result["success"] is True and result["conflict"] is False, result
    assert result["session_id"] != "sess-abc"
    assert uuid.UUID(result["session_id"]).version == 4, "the fresh id is server-generated, not derived (#21731)"
    kwargs = manager.save_session.call_args.kwargs
    assert kwargs["session_id"] == result["session_id"]
    assert kwargs["replace"] is False
    assert kwargs["metadata"]["owner"] == "bob"


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["alice", None])
@pytest.mark.parametrize("on_conflict", ["skip", "rename"])
async def test_a_non_owner_collision_is_a_200_with_a_new_id(owner, on_conflict) -> None:
    manager = _manager(exists=True, owner=owner)

    result = await import_conversation(manager, dict(_DOCUMENT), on_conflict=on_conflict, user_data=_BOB)

    _assert_saved_under_a_fresh_id(manager, result)
    manager.save_session.assert_awaited_once()


def _normalise(result: Dict[str, Any]) -> Dict[str, Any]:
    """The response with its random id masked, so two responses compare on everything else."""
    return {**result, "session_id": "ID", "message": result["message"].replace(result["session_id"], "ID")}


@pytest.mark.asyncio
@pytest.mark.parametrize("on_conflict", ["skip", "replace", "merge", "rename"])
async def test_a_free_id_and_a_foreign_id_answer_identically(on_conflict) -> None:
    """#21731: the response must not reveal whether the requested id exists under another owner."""
    free, foreign = _manager(), _manager(exists=True, owner="alice")

    r_free = await import_conversation(free, dict(_DOCUMENT), on_conflict=on_conflict, user_data=_BOB)
    r_foreign = await import_conversation(foreign, dict(_DOCUMENT), on_conflict=on_conflict, user_data=_BOB)

    assert r_free.keys() == r_foreign.keys()
    for result in (r_free, r_foreign):
        assert result["session_id"] != "sess-abc"
        assert result["message"] == f"Imported 1 messages into session {result['session_id']!r}"
    assert _normalise(r_free) == _normalise(r_foreign)
    assert free.save_session.call_args.kwargs.keys() == foreign.save_session.call_args.kwargs.keys()
    assert free.get_session_owner.await_count == foreign.get_session_owner.await_count == 1


@pytest.mark.asyncio
async def test_the_foreign_session_is_untouched_by_the_import() -> None:
    manager = _manager(exists=True, owner="alice")

    result = await import_conversation(manager, dict(_DOCUMENT), on_conflict="replace", user_data=_BOB)

    manager.save_session.assert_awaited_once()
    assert manager.save_session.call_args.kwargs["session_id"] == result["session_id"] != "sess-abc"
    assert manager.save_session.call_args.kwargs["replace"] is False


@pytest.mark.asyncio
async def test_imports_in_the_same_second_get_distinct_ids(monkeypatch) -> None:
    """The id no longer comes from the clock: same-second imports cannot collide and merge."""
    monkeypatch.setattr("time.time", lambda: 1_700_000_000.0)

    ids = {(await import_conversation(_manager(), dict(_DOCUMENT), user_data=_BOB))["session_id"] for _ in range(20)}

    assert len(ids) == 20


@pytest.mark.asyncio
async def test_a_fresh_id_that_already_has_a_record_is_never_used(monkeypatch) -> None:
    """Create-only: an id with a stored record is skipped, so the save cannot merge into it."""
    taken = "00000000-0000-4000-8000-000000000001"
    ids = iter([uuid.UUID(taken), uuid.UUID("00000000-0000-4000-8000-000000000002")])
    monkeypatch.setattr(conversation_export, "uuid", SimpleNamespace(uuid4=lambda: next(ids)))  # not the global uuid

    async def _exists(manager, session_id):
        return session_id == taken

    monkeypatch.setattr(conversation_export, "session_file_exists", _exists)

    result = await import_conversation(_manager(), dict(_DOCUMENT), user_data=_BOB)

    assert result["session_id"] == "00000000-0000-4000-8000-000000000002"


@pytest.mark.asyncio
async def test_the_owner_skipping_their_own_session_still_reports_a_conflict() -> None:
    manager = _manager(exists=True, owner="alice")

    result = await import_conversation(manager, dict(_DOCUMENT), on_conflict="skip", user_data=_ALICE)

    assert result["success"] is False and result["conflict"] is True
    manager.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_owner_renaming_their_own_session_is_unchanged() -> None:
    manager = _manager(exists=True, owner="alice")

    result = await import_conversation(manager, dict(_DOCUMENT), on_conflict="rename", user_data=_ALICE)

    assert result["success"] is True and result["conflict"] is True
    assert result["session_id"] != "sess-abc" and uuid.UUID(result["session_id"]).version == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("on_conflict", ["skip", "replace", "merge"])
async def test_an_owned_session_with_no_messages_still_exists_and_is_not_taken_over(
    on_conflict,
) -> None:
    """#21668: a stored record with an owner but no messages must not read as absent."""
    manager = _manager(exists=True, owner="alice", empty=True)

    result = await import_conversation(manager, dict(_DOCUMENT), on_conflict=on_conflict, user_data=_BOB)

    _assert_saved_under_a_fresh_id(manager, result)
    manager.set_session_owner.assert_not_called()


@pytest.mark.asyncio
async def test_a_new_import_carries_the_active_company(monkeypatch) -> None:
    """#21997: an imported chat is a new chat, so it is stamped with the active company like any other."""
    manager = _manager()

    result = await import_conversation(
        manager, dict(_DOCUMENT), user_data=_ALICE, company_metadata={"company_id": "co-1"}
    )

    assert result["success"] is True
    metadata = manager.save_session.call_args.kwargs["metadata"]
    assert metadata["company_id"] == "co-1" and metadata["owner"] == "alice"


@pytest.mark.asyncio
async def test_an_import_with_no_active_company_stays_unassigned() -> None:
    manager = _manager()

    await import_conversation(manager, dict(_DOCUMENT), user_data=_ALICE)

    assert "company_id" not in manager.save_session.call_args.kwargs["metadata"]


@pytest.mark.asyncio
async def test_replacing_ones_own_chat_does_not_re_tag_it() -> None:
    manager = _manager(exists=True, owner="alice")
    manager.get_session_company = AsyncMock(return_value="co-1")

    await import_conversation(
        manager,
        dict(_DOCUMENT),
        on_conflict="replace",
        user_data=_ALICE,
        company_metadata={"company_id": "co-1"},
    )

    assert "company_id" not in manager.save_session.call_args.kwargs["metadata"]


@pytest.mark.asyncio
@pytest.mark.parametrize("on_conflict", ["replace", "rename", "skip"])
async def test_an_import_onto_ones_own_chat_of_another_company_is_refused(on_conflict) -> None:
    """#21997: the owned existing id resolves, and the company check refuses before anything is written."""
    manager = _manager(exists=True, owner="alice")
    manager.get_session_company = AsyncMock(return_value="co-b")

    with pytest.raises(HTTPException) as refused:
        await import_conversation(
            manager,
            dict(_DOCUMENT),
            on_conflict=on_conflict,
            user_data=_ALICE,
            company_metadata={"company_id": "co-a"},
        )

    assert (refused.value.status_code, refused.value.detail) == (403, "Forbidden")
    manager.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_import_onto_ones_own_chat_of_the_active_company_replaces_it() -> None:
    manager = _manager(exists=True, owner="alice")
    manager.get_session_company = AsyncMock(return_value="co-a")

    result = await import_conversation(
        manager, dict(_DOCUMENT), on_conflict="replace", user_data=_ALICE, company_metadata={"company_id": "co-a"}
    )

    assert result["success"] is True
