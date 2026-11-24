# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#22180: the grant subject rewrite re-checks every row, and one that changed is left untouched."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from services import workflow_grant_subjects as subjects

_ITEM = {"permission_id": str(uuid.uuid4()), "workflow_id": "wf", "old": "alice", "new": "u-1"}


def _session(row, clash=None) -> MagicMock:
    session = MagicMock()
    session.get = AsyncMock(return_value=row)
    session.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=clash), rowcount=1))
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _row(user_id="alice", workflow_id="wf") -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id, workflow_id=workflow_id)


async def test_a_row_that_still_matches_is_rewritten() -> None:
    session = _session(_row())
    with patch.object(subjects, "username_to_id", AsyncMock(return_value="u-1")):
        assert await subjects._apply_one(session, _ITEM) is None
    session.commit.assert_awaited_once()


async def test_a_row_whose_subject_changed_since_the_proposal_is_left_untouched() -> None:
    session = _session(_row(user_id="bob"))
    assert await subjects._apply_one(session, _ITEM) == "the row no longer matches the proposal"
    session.commit.assert_not_awaited()


async def test_a_name_that_now_names_another_account_is_left_untouched() -> None:
    session = _session(_row())
    with patch.object(subjects, "username_to_id", AsyncMock(return_value="u-2")):
        assert await subjects._apply_one(session, _ITEM) == "the name no longer identifies the proposed account"
    session.commit.assert_not_awaited()


async def test_a_user_that_already_holds_a_grant_is_not_overwritten() -> None:
    session = _session(_row(), clash=("existing",))
    with patch.object(subjects, "username_to_id", AsyncMock(return_value="u-1")):
        assert "already holds" in await subjects._apply_one(session, _ITEM)


async def test_apply_remap_reports_each_skipped_row() -> None:
    with patch.object(subjects, "_apply_one", AsyncMock(side_effect=[None, "why"])):
        count, skipped = await subjects.apply_remap(MagicMock(), [_ITEM, _ITEM])
    assert count == 1 and skipped == ["wf:alice: why"]
