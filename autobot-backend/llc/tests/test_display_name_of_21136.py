# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`display_name_of` is the single-user form of `member_people` (#21136)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from llc.services import member_standing


@pytest.mark.asyncio
async def test_returns_the_resolved_name(monkeypatch):
    uid = uuid.uuid4()
    people = AsyncMock(return_value=({uid: "Alice A"}, {uid: True}))
    monkeypatch.setattr(member_standing, "member_people", people)
    assert await member_standing.display_name_of(MagicMock(), uid) == "Alice A"
    people.assert_awaited_once()
    assert people.await_args.args[1] == [uid]


@pytest.mark.asyncio
async def test_unknown_user_is_none(monkeypatch):
    monkeypatch.setattr(member_standing, "member_people", AsyncMock(return_value=({}, {})))
    assert await member_standing.display_name_of(MagicMock(), uuid.uuid4()) is None
