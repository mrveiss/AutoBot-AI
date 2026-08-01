# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed ownership lookup must not return an unfiltered session list (#12685).

`_filter_user_sessions` used to `return sessions` — every session on the
instance — whenever the Redis ownership lookup raised. On a tenancy filter that
is the wrong direction to fail: a Redis blip silently exposed other companies'
agent conversations (observed live as a `CEO · <company_id>` session appearing
in an ordinary user's chat list).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.chat_sessions import _filter_user_sessions
from api.chat_sessions_errors import OwnershipUnavailableError

_ALL = [
    {"id": "mine-1", "title": "My chat"},
    {"id": "other-1", "title": "Someone else's chat"},
    {"id": "agent-1", "title": "CEO · 22d907a9-31fd-4bb4-8b42-89"},
]


def _validator(owned):
    v = MagicMock()
    v.get_user_sessions = AsyncMock(return_value=owned)
    return v


@pytest.mark.asyncio
async def test_returns_only_the_users_own_sessions():
    with patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock()):
        with patch("api.chat_sessions._build_ownership_validator", return_value=_validator(["mine-1"])):
            result = await _filter_user_sessions(list(_ALL), "alice")

    assert [s["id"] for s in result] == ["mine-1"]


@pytest.mark.asyncio
async def test_agent_session_is_excluded_when_not_owned():
    """The reported symptom: a CEO agent conversation in a user's list."""
    with patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock()):
        with patch("api.chat_sessions._build_ownership_validator", return_value=_validator(["mine-1"])):
            result = await _filter_user_sessions(list(_ALL), "alice")

    assert not any("CEO ·" in s["title"] for s in result)


@pytest.mark.asyncio
async def test_lookup_failure_raises_instead_of_returning_everything():
    """The core fix: an error, not a silent unfiltered list."""
    with patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock(side_effect=RuntimeError("redis down"))):
        with pytest.raises(OwnershipUnavailableError) as exc:
            await _filter_user_sessions(list(_ALL), "alice")

    assert exc.value.status_code == 503, "a transient store outage is 503, not 500"


@pytest.mark.asyncio
async def test_validator_failure_also_raises():
    with patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock()):
        v = MagicMock()
        v.get_user_sessions = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("api.chat_sessions._build_ownership_validator", return_value=v):
            with pytest.raises(OwnershipUnavailableError):
                await _filter_user_sessions(list(_ALL), "alice")


@pytest.mark.asyncio
async def test_no_ownership_records_still_returns_all_but_warns(caplog):
    """Legacy-session path, deliberately unchanged — but no longer silent.

    Failing closed here would hide a user's own history on installs predating
    ownership tracking, so the decision is deferred to #12685. The exposure is
    logged so it is visible rather than invisible.
    """
    with patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock()):
        with patch("api.chat_sessions._build_ownership_validator", return_value=_validator([])):
            with caplog.at_level("WARNING"):
                result = await _filter_user_sessions(list(_ALL), "alice")

    assert len(result) == 3
    assert any("No ownership records" in r.getMessage() for r in caplog.records)
