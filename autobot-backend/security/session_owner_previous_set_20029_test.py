# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20029: a handed-over session leaves its old owner's list, which otherwise shows its title."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from security.session_ownership import SessionOwnershipValidator


def _validator(existing: str | None) -> SessionOwnershipValidator:
    validator = SessionOwnershipValidator.__new__(SessionOwnershipValidator)
    validator.redis = MagicMock(set=AsyncMock(), sadd=AsyncMock(), expire=AsyncMock(), srem=AsyncMock())
    validator.ownership_ttl = 60
    validator.get_session_owner = AsyncMock(return_value=existing)
    return validator


@pytest.mark.asyncio
async def test_a_transfer_leaves_the_old_owners_set() -> None:
    validator = _validator("old")
    assert await validator.set_session_owner("s1", "new", force=True)
    validator.redis.srem.assert_awaited_once_with("user_chat_sessions:old", "s1")


@pytest.mark.asyncio
async def test_a_named_previous_owner_is_used_when_the_key_expired() -> None:
    validator = _validator(None)
    assert await validator.set_session_owner("s1", "new", force=True, previous_owner="old")
    validator.redis.srem.assert_awaited_once_with("user_chat_sessions:old", "s1")


@pytest.mark.asyncio
async def test_contrast_refreshing_ones_own_session_removes_nothing() -> None:
    validator = _validator("same")
    assert await validator.set_session_owner("s1", "same")
    validator.redis.srem.assert_not_awaited()
