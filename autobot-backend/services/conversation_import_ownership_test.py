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

from chat_history.session import SessionOwnerUnreadable
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


def _manager(*, exists: bool = False, owner: Any = None, owner_raises: bool = False):
    manager = AsyncMock()
    manager.save_session = AsyncMock()
    # `_session_exists` calls load_session and treats a non-empty message list
    # as "exists" — mocking anything else makes every conflict test skip the
    # branch it is meant to exercise.
    manager.load_session = AsyncMock(
        return_value=[{"role": "user", "content": "existing"}] if exists else []
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
    metadata = manager.save_session.call_args.kwargs["metadata"]
    assert metadata is not None, "import produced a session with no owner (#14026)"
    assert metadata["owner"] == "alice"
    assert metadata["username"] == "alice"
    assert metadata["user_id"] == "u-1"


@pytest.mark.asyncio
async def test_replace_refuses_to_overwrite_another_users_session() -> None:
    manager = _manager(exists=True, owner="alice")

    result = await import_conversation(
        manager, dict(_DOCUMENT), on_conflict="replace", user_data=_BOB
    )

    assert result["success"] is False
    assert "another user" in result["message"]
    manager.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_replace_allows_the_owner_to_overwrite_their_own_session() -> None:
    manager = _manager(exists=True, owner="alice")

    result = await import_conversation(
        manager, dict(_DOCUMENT), on_conflict="replace", user_data=_ALICE
    )

    assert result["success"] is True
    manager.save_session.assert_awaited()


@pytest.mark.asyncio
async def test_replace_refuses_when_ownership_cannot_be_read() -> None:
    """Unreadable is not unowned — the #14033 distinction, applied.

    Without this an OSError reads as "no owner", and "no owner" was the branch
    that let the overwrite through.
    """
    manager = _manager(exists=True, owner_raises=True)

    result = await import_conversation(
        manager, dict(_DOCUMENT), on_conflict="replace", user_data=_BOB
    )

    assert result["success"] is False
    manager.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_replace_still_works_on_a_genuinely_unowned_session() -> None:
    """A real legacy session records no owner and stays replaceable."""
    manager = _manager(exists=True, owner=None)

    result = await import_conversation(
        manager, dict(_DOCUMENT), on_conflict="replace", user_data=_BOB
    )

    assert result["success"] is True
    manager.save_session.assert_awaited()
