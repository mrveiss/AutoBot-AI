# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The app-side triggers of the secrets uniqueness constraint (#17850); the DDL itself runs in the migration tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services import secret_duplicate_cleanup_action as action
from services import secret_unique_constraint as unique

_ID = "11111111-1111-1111-1111-111111111111"


def _approval():
    return SimpleNamespace(
        id="ap", decided_by_user="admin", context={"survivor_id": _ID, "removal_ids": []}, status="approved"
    )


@pytest.mark.asyncio
async def test_the_executor_triggers_the_ensure_after_its_removals(monkeypatch):
    ensure = AsyncMock()
    monkeypatch.setattr(action, "ensure_after_duplicate_removal", ensure)
    monkeypatch.setattr(action, "_review_of", AsyncMock(return_value=SimpleNamespace(removals=[])))
    monkeypatch.setattr(action, "_comment", AsyncMock())
    session = AsyncMock()
    await action.execute_secret_duplicate_cleanup(_approval(), session)
    ensure.assert_awaited_once_with(session)


@pytest.mark.asyncio
@pytest.mark.parametrize("remaining, ensured", [([object()], 0), ([], 1)])
async def test_the_post_removal_hook_ensures_only_when_no_group_remains(monkeypatch, remaining, ensured):
    import services.secret_duplicates as dup

    ensure = AsyncMock(return_value="created")
    monkeypatch.setattr(dup, "find_duplicate_groups", AsyncMock(return_value=remaining))
    monkeypatch.setattr(unique, "ensure_constraint_in", ensure)
    await unique.ensure_after_duplicate_removal(MagicMock())
    assert ensure.await_count == ensured


@pytest.mark.asyncio
async def test_a_failed_ensure_is_logged_by_type_only_and_never_raised(caplog):
    session = MagicMock(connection=AsyncMock(side_effect=ValueError("secret-name-xyz")), rollback=AsyncMock())
    assert await unique.ensure_constraint_in(session) is None
    assert "ValueError" in caplog.text and "secret-name-xyz" not in caplog.text


@pytest.mark.asyncio
async def test_the_startup_check_never_raises(monkeypatch):
    import user_management.database as database

    monkeypatch.setattr(database, "get_async_session_factory", MagicMock(side_effect=RuntimeError("down")))
    await unique.ensure_secret_unique_at_startup()
