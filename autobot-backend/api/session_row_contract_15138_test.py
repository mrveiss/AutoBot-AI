# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The session and message rows are described, and describing them costs nothing (#15138).

`SessionListData.sessions` and `SessionMessagesData.messages` were both
`List[Any]`, so the backend declared the *envelope* of these two routes and said
nothing at all about a row. A generated client got `Any`; a reader got nothing;
and `repo_tests/sdk_response_model_contract_test.py` had to carry `sdk.Session`
and `sdk.ChatMessage` in its UNPAIRED table naming this issue as the blocker.

Two things are asserted, and the second matters more than the first.

1. The declared models accept the keys the builders actually write.
2. Declaring them **drops nothing**. These routes serialise dictionaries
   assembled in several places over several years, so the risk of typing them is
   a silently truncated response — a field that vanishes because no one listed
   it. `extra="allow"` plus all-optional fields is what makes that impossible,
   and these tests are what prove it rather than assuming it.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from api.schemas_chat_rows import SessionListData, SessionMessage, SessionMessagesData, SessionSummary


def _session_row(**overrides: Any) -> Dict[str, Any]:
    """The literal keys `_build_session_entry` writes (chat_history/session_listing.py)."""
    row = {
        "id": "chat-1",
        "chatId": "chat-1",
        "title": "A conversation",
        "name": "A conversation",
        "messages": [],
        "messageCount": 3,
        "createdAt": "2026-09-01T10:00:00",
        "createdTime": "2026-09-01T10:00:00",
        "updatedAt": "2026-09-01T11:00:00",
        "lastModified": "2026-09-01T11:00:00",
        "updatedAtEpoch": 1788000000.0,
        "isActive": False,
        "fileSize": 2048,
        "fast_mode": True,
        "companyId": "",
        "sessionKind": "user",
    }
    row.update(overrides)
    return row


def _message_row(**overrides: Any) -> Dict[str, Any]:
    """The literal keys `_build_message_dict` writes (chat_history/messages.py)."""
    row = {
        "id": "11111111-2222-3333-4444-555555555555",
        "sender": "user",
        "text": "hello",
        "messageType": "text",
        "metadata": {"raw": True},
        "timestamp": "2026-09-01 11:00:00",
        "sources": [],
    }
    row.update(overrides)
    return row


# --- the three list_sessions branches -------------------------------------


@pytest.mark.parametrize(
    "branch,row,envelope",
    [
        ("user", _session_row(), {"count": 1}),
        (
            "org",
            _session_row(companyId="co-7", sessionKind="org"),
            {"count": 1, "scope": "org", "org_id": "co-7"},
        ),
        (
            "team",
            _session_row(companyId="co-7", sessionKind="team"),
            {"count": 1, "scope": "team", "org_id": "co-7", "team_id": "t-2"},
        ),
        ("shared", _session_row(sessionKind="shared"), {"count": 1, "scope": "shared"}),
    ],
)
def test_a_row_from_each_scope_branch_round_trips_intact(branch, row, envelope) -> None:
    """No key dropped, no value nulled, for any branch the route can take."""
    payload = SessionListData(sessions=[row], **envelope)

    emitted = payload.model_dump()["sessions"][0]

    missing = {k for k in row if k not in emitted}
    changed = {k: (row[k], emitted[k]) for k in row if k in emitted and emitted[k] != row[k]}
    assert not missing, f"{branch}: keys dropped by the model: {sorted(missing)}"
    assert not changed, f"{branch}: values altered by the model: {changed}"


def test_a_message_row_round_trips_intact() -> None:
    payload = SessionMessagesData(
        messages=[_message_row()], session_id="chat-1", total_count=1, page=1, per_page=50
    )

    emitted = payload.model_dump()["messages"][0]
    row = _message_row()

    assert not {k for k in row if k not in emitted}
    assert all(emitted[k] == row[k] for k in row)


def test_the_optional_message_keys_are_absent_rather_than_null() -> None:
    """`toolMarkers` and `authorId` are only written when present.

    Emitting them as explicit nulls would change the payload for every message
    that has neither — a regression introduced by the act of describing it.
    """
    emitted = SessionMessage(**_message_row()).model_dump(exclude_none=True)

    assert "toolMarkers" not in emitted
    assert "authorId" not in emitted


def test_an_unlisted_key_survives() -> None:
    """The guard against this change being a silent truncation.

    A key added to a builder tomorrow, before anyone updates the model, must
    still reach the client. Without `extra="allow"` this test fails and the
    response quietly loses a field.
    """
    row = _session_row(someFutureField="kept")

    emitted = SessionListData(sessions=[row], count=1).model_dump()["sessions"][0]

    assert emitted.get("someFutureField") == "kept"


def test_the_models_are_not_vacuously_permissive() -> None:
    """Guard the guard: `extra="allow"` must not mean the fields are undeclared.

    If the declarations were empty, every test above would pass while the
    contract still described nothing — which is the state this issue is about.
    """
    assert {"id", "title", "messageCount", "sessionKind"} <= set(SessionSummary.model_fields)
    assert {"id", "sender", "text", "timestamp"} <= set(SessionMessage.model_fields)
