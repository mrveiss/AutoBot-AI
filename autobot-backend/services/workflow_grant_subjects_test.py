# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#22180: the grant subject rewrite re-checks every row, and one that changed is left untouched."""

from __future__ import annotations

import importlib
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
    with patch.object(subjects, "_apply_one", AsyncMock(side_effect=[None, subjects._APPLIED, "why"])):
        count, already, skipped = await subjects.apply_remap(MagicMock(), [_ITEM, _ITEM, _ITEM])
    assert count == 1 and already == 1 and skipped == ["wf:alice: why"]


_UID = str(uuid.uuid4())


def _result(items) -> MagicMock:
    """A query result whose rows are *items*, however the code reads them."""
    out = MagicMock()
    out.all.return_value = list(items)
    out.scalars.return_value = MagicMock(
        all=MagicMock(return_value=list(items)), first=MagicMock(return_value=(items or [None])[0])
    )
    return out


def _ref_session(*results) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[_result(r) for r in results])
    return session


async def test_a_user_id_resolves_only_when_the_account_is_active() -> None:
    uid = uuid.UUID(_UID)
    assert await subjects.resolve_user_ref(_ref_session([uid]), _UID) == _UID
    assert await subjects.resolve_user_ref(_ref_session([]), _UID) is None  # deleted or inactive: filtered out


async def test_a_username_resolves_only_when_the_account_is_active() -> None:
    assert await subjects.resolve_user_ref(_ref_session([("alice", _UID)]), "alice") == _UID
    assert await subjects.resolve_user_ref(_ref_session([]), "alice") is None  # unknown, deleted or inactive


async def test_the_id_and_name_paths_apply_the_same_active_filter() -> None:
    id_session, name_session = _ref_session([]), _ref_session([])
    await subjects.resolve_user_ref(id_session, _UID)
    await subjects.resolve_user_ref(name_session, "alice")
    for session in (id_session, name_session):
        sql = str(session.execute.await_args.args[0])
        assert "is_active" in sql and "deleted_at IS NULL" in sql


async def test_a_blank_target_is_unknown_without_a_query() -> None:
    session = _ref_session()
    assert await subjects.resolve_user_ref(session, "  ") is None
    session.execute.assert_not_awaited()


async def test_a_name_held_by_two_rows_is_ambiguous_not_picked() -> None:
    session = _ref_session([("alice", "u-1"), ("alice", "u-2"), ("bob", "u-3")])
    assert await subjects.usernames_to_ids(session, {"alice", "bob"}) == {"bob": "u-3"}


async def test_plan_remap_maps_known_names_and_reports_the_rest_in_one_name_query() -> None:
    perms = [
        SimpleNamespace(id=uuid.uuid4(), workflow_id="wf", user_id="alice"),
        SimpleNamespace(id=uuid.uuid4(), workflow_id="wf", user_id="ghost"),
        SimpleNamespace(id=uuid.uuid4(), workflow_id="wf", user_id=_UID),
    ]
    session = _ref_session(perms, [uuid.UUID(_UID)], [("alice", "u-1")])
    mappings, unmapped = await subjects.plan_remap(session)
    assert [(m["old"], m["new"]) for m in mappings] == [("alice", "u-1")]
    assert [u["old"] for u in unmapped] == ["ghost"]
    assert session.execute.await_count == 3  # rows, known ids, ONE batched name lookup


async def test_a_row_already_at_the_proposed_subject_counts_as_applied() -> None:
    session = _session(_row(user_id="u-1"))
    assert await subjects._apply_one(session, _ITEM) == subjects._APPLIED
    session.commit.assert_not_awaited()


async def test_replaying_an_applied_proposal_records_it_done() -> None:
    approval = SimpleNamespace(context={"mappings": [_ITEM]})
    with (
        patch.object(subjects, "_apply_one", AsyncMock(return_value=subjects._APPLIED)),
        patch.object(subjects, "record_cleanup_outcome", AsyncMock()) as record,
    ):
        await subjects.execute_grant_remap(approval, MagicMock())
    assert record.await_args.kwargs["done"] is True
    assert "0 of 1 rows rewritten, 1 already applied" in record.await_args.kwargs["summary"]


def test_the_action_is_registered_server_only_and_admin_only() -> None:
    from services import approval_execution as registry

    subjects.register_grant_remap_action()
    assert subjects.ACTION in registry._SERVER_ONLY
    assert subjects.ACTION in registry._ADMIN_ONLY
    assert registry.registered_action_proposers()[subjects.ACTION] == subjects.PROPOSED_BY


def test_the_pending_proposal_index_matches_the_migration_and_the_adoption_marker() -> None:
    from migrations.baseline import INDEX_MARKERS
    from models import approval

    migration = importlib.import_module(
        "migrations.versions.20261124_124_approvals_pending_workflow_grant_remap_unique"
    )
    assert approval.PENDING_GRANT_REMAP_INDEX == migration._INDEX
    assert migration._where(migration._ACTION) == approval.PENDING_GRANT_REMAP_WHERE
    assert migration._ACTION == subjects.ACTION and migration._KEY == "scope"
    assert {i.name: i.unique for i in approval.Approval.__table__.indexes}[migration._INDEX]
    assert ("approvals", migration._INDEX) in INDEX_MARKERS[migration.revision]
