# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC agent (CEO) conversations must not leak into the ordinary chat list (#12685).

Before this fix, ``GET /api/chat/sessions`` returned every session owned by the
caller with no company/agent scoping at all — an LLC agent heartbeat/CEO-chat
conversation was indistinguishable from an ordinary chat except by parsing its
display title ("CEO · <company_id>"). With more than one company, every
company's agent conversations piled into that one flat list.

These tests drive ``list_sessions`` — the real ``GET /chat/sessions`` route
function, not ``_is_agent_scoped_session`` in isolation — so the assertion is
at the same boundary the reported symptom was observed at.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import chat_sessions

_ALL_SESSIONS = [
    {"id": "s-mine", "title": "My chat", "companyId": "", "sessionKind": "user"},
    {
        "id": "s-ceo-company-a",
        "title": "CEO · company-a",
        "companyId": "company-a",
        "sessionKind": "agent",
    },
    {
        "id": "s-ceo-company-b",
        "title": "CEO · company-b",
        "companyId": "company-b",
        "sessionKind": "agent",
    },
    # A session created before this fix shipped: no scoping fields at all.
    # #12685's migration decision — NOT retroactively reclassified, so it
    # must keep showing exactly as it did before (no data loss).
    {"id": "s-legacy-untagged", "title": "Untitled", "companyId": "", "sessionKind": "user"},
]


def _manager(sessions=None):
    manager = MagicMock(spec=["list_sessions_fast"])
    manager.list_sessions_fast = AsyncMock(return_value=list(sessions if sessions is not None else _ALL_SESSIONS))
    return manager


def _validator_owning_everything():
    """Ownership validator that owns every session — isolates the assertions
    below to the tenancy-scoping filter, not the (separately tested)
    ownership filter."""
    v = MagicMock()
    v.get_user_sessions = AsyncMock(return_value=[s["id"] for s in _ALL_SESSIONS])
    return v


async def _list_sessions_for(username: str, sessions=None):
    request = MagicMock()
    current_user = {"username": username}

    with patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock()):
        with patch.object(chat_sessions, "get_chat_history_manager", return_value=_manager(sessions)):
            with patch.object(
                chat_sessions, "_build_ownership_validator", return_value=_validator_owning_everything()
            ):
                response = await chat_sessions.list_sessions(request, current_user, scope=None, team_id=None)

    return response


def _session_ids(response) -> set:
    import json

    payload = response.body if hasattr(response, "body") else response
    if isinstance(payload, (bytes, bytearray)):
        payload = json.loads(payload)
    data = payload.get("data", payload)
    return {s["id"] for s in data["sessions"]}


class TestAgentSessionsExcludedFromOrdinaryList:
    """AC: an agent session does not appear in an ordinary user's GET /api/chat/sessions."""

    @pytest.mark.asyncio
    async def test_ceo_chat_session_is_excluded(self):
        response = await _list_sessions_for("alice")
        ids = _session_ids(response)

        assert "s-ceo-company-a" not in ids
        assert "s-ceo-company-b" not in ids
        assert "s-mine" in ids, "the caller's own ordinary session must still be returned"

    @pytest.mark.asyncio
    async def test_agent_scoped_session_absent_regardless_of_which_company(self):
        """The reported symptom: with two companies, BOTH piled into one flat
        list. Post-fix, neither company's agent session is in the list at all
        — company A's session does not leak next to company B's, or anyone
        else's, in the general list."""
        response = await _list_sessions_for("alice")
        ids = _session_ids(response)

        agent_ids = {s["id"] for s in _ALL_SESSIONS if chat_sessions._is_agent_scoped_session(s)}
        assert agent_ids == {"s-ceo-company-a", "s-ceo-company-b"}
        assert ids.isdisjoint(agent_ids)


class TestLegacyUntaggedSessionsAreNotLost:
    """Migration safety: a session predating #12685 (no companyId/sessionKind)
    must not be dropped or silently re-scoped — it keeps appearing exactly as
    it did before this fix."""

    @pytest.mark.asyncio
    async def test_legacy_session_without_scoping_fields_still_appears(self):
        response = await _list_sessions_for("alice")
        ids = _session_ids(response)

        assert "s-legacy-untagged" in ids


class TestIsAgentScopedSessionHelper:
    """Cheap structural pins on the discriminator itself."""

    def test_company_id_alone_is_sufficient(self):
        assert chat_sessions._is_agent_scoped_session({"companyId": "co-1"}) is True

    def test_session_kind_alone_is_sufficient(self):
        assert chat_sessions._is_agent_scoped_session({"sessionKind": "agent"}) is True

    def test_ordinary_session_is_not_agent_scoped(self):
        assert chat_sessions._is_agent_scoped_session({"companyId": "", "sessionKind": "user"}) is False

    def test_missing_fields_default_to_not_agent_scoped(self):
        assert chat_sessions._is_agent_scoped_session({}) is False
