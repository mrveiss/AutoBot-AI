# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21417 a deleted source's run record leaves only through an approved proposal; #21621 every run orders."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.codebase_analytics import run_status, source_service
from api.codebase_analytics.run_status import (
    describe_run_state,
    ordered_at,
    record_run_finished,
    record_run_started,
)
from services import source_run_record_cleanup_action as action_mod
from services import source_run_record_cleanup_proposals as proposals_mod


class _Collection:
    def __init__(self):
        self.docs = {}

    async def get(self, ids=None, where=None, include=None):
        found = [i for i in ids if i in self.docs]
        return {"ids": found, "metadatas": [self.docs[i] for i in found]}

    async def upsert(self, ids, documents, metadatas):
        for i, m in zip(ids, metadatas):
            self.docs[i] = dict(m)

    async def delete(self, ids=None, where=None):
        for i in ids or []:
            self.docs.pop(i, None)


@pytest.fixture
def collection():
    col = _Collection()
    with patch.object(run_status, "get_code_collection_async", AsyncMock(return_value=col)):
        yield col


def _source(name="atlas"):
    return SimpleNamespace(name=name, clone_path=None)


async def _delete_source(source_id, propose):
    with (
        patch("api.codebase_analytics.source_storage.delete_source", AsyncMock(return_value=True)),
        patch.object(source_service, "_purge_source_index", AsyncMock()),
        patch.object(proposals_mod, "propose_run_record_removal", propose),
    ):
        return await source_service.delete_source_and_cleanup(source_id, source=_source())


class TestDeleteOnlyProposes:
    @pytest.mark.asyncio
    async def test_the_record_survives_the_source_delete_and_a_proposal_names_it(self, collection):
        await record_run_started("src", "run-1")
        propose = AsyncMock(return_value="approval-1")
        assert await _delete_source("src", propose) is True
        propose.assert_awaited_once_with("src", "atlas")
        assert "codebase_run_src" in collection.docs, "deleting a source must not delete its record"

    @pytest.mark.asyncio
    async def test_an_approved_proposal_removes_exactly_that_record(self, collection):
        await record_run_started("src", "run-1")
        await record_run_started("other", "run-2")
        session = MagicMock(add=MagicMock(), commit=AsyncMock())
        approval = SimpleNamespace(
            id="a1", context={"action": action_mod.ACTION, "source_id": "src"}, decided_by_user="u"
        )
        with patch.object(action_mod, "audit_log", AsyncMock()) as audit:
            await action_mod.execute_source_run_record_cleanup(approval, session)
        assert "codebase_run_src" not in collection.docs
        assert "codebase_run_other" in collection.docs
        assert audit.await_args.kwargs["resource"] == "run_record:codebase_run_src"

    @pytest.mark.asyncio
    async def test_an_approval_without_a_source_fails_loudly(self, collection):
        approval = SimpleNamespace(id="a2", context={"action": action_mod.ACTION}, decided_by_user="u")
        with pytest.raises(ValueError):
            await action_mod.execute_source_run_record_cleanup(approval, MagicMock())

    @pytest.mark.asyncio
    async def test_no_proposal_is_filed_for_a_source_with_no_record(self, collection):
        assert await proposals_mod.propose_run_record_removal("never-indexed", "atlas") is None


class TestReaderNeverServesAnotherSourcesRecord:
    @pytest.mark.asyncio
    async def test_a_record_naming_another_source_is_not_this_sources_run(self, collection):
        await record_run_started("old", "run-1")
        collection.docs["codebase_run_new"] = dict(
            collection.docs["codebase_run_old"]
        )  # an id reused: owner stays "old"
        assert await describe_run_state("new") is None
        assert (await describe_run_state("old"))["run_id"] == "run-1"

    @pytest.mark.asyncio
    async def test_delete_run_record_leaves_a_record_owned_by_another_source(self, collection):
        await record_run_started("old", "run-1")
        collection.docs["codebase_run_new"] = dict(collection.docs["codebase_run_old"])
        assert await run_status.delete_run_record("new") is False
        assert "codebase_run_new" in collection.docs


class TestEveryRunStateOrders:
    @pytest.mark.asyncio
    async def test_a_started_run_orders_by_its_start(self, collection):
        await record_run_started("src", "run-1")
        state = await describe_run_state("src")
        assert state["ordered_at"] == ordered_at({"latest_started_at": state["started_at"]}) != ""

    @pytest.mark.asyncio
    async def test_a_run_whose_start_was_never_recorded_orders_by_its_end(self, collection):
        await record_run_started("src", "run-1")
        await record_run_finished("src", "run-1", "completed")
        await record_run_finished("src", "run-2", "killed", "exit -9")  # run 2's start write was lost
        state = await describe_run_state("src")
        assert state["started_at"] == ""
        assert state["ordered_at"] == ordered_at({"latest_finished_at": state["finished_at"]}) != ""

    @pytest.mark.parametrize(
        "meta",
        [
            {},
            {"latest_started_at": ""},
            {"latest_started_at": "garbage"},
            {"latest_started_at": None, "latest_finished_at": ""},
        ],
    )
    def test_the_ordering_field_is_never_empty(self, meta):
        value = ordered_at(meta)
        assert value and value.endswith("+00:00")

    def test_a_naive_timestamp_is_ordered_as_utc(self):
        assert ordered_at({"latest_started_at": "2020-01-01T00:00:00"}) == "2020-01-01T00:00:00+00:00"


class TestHandlersExistAtStartup:
    def test_the_approvals_router_registers_both_cleanup_actions_without_the_proposers_loaded(self):
        """After a restart nothing has imported a proposer yet; importing the router must be enough."""
        from api import approval_gates  # noqa: F401
        from services.approval_execution import is_registered_action
        from services.conversation_file_cleanup_action import ACTION as FILE_ACTION

        assert is_registered_action(action_mod.ACTION)
        assert is_registered_action(FILE_ACTION)


class TestProposalHardening:
    def test_a_long_source_name_still_fits_the_title_column(self):
        from models.approval import Approval

        title = proposals_mod._title("x" * 1000)
        assert len(title) <= Approval.title.type.length and title.endswith("…")
        assert proposals_mod._title("atlas").endswith("atlas")

    @pytest.mark.asyncio
    async def test_an_unavailable_store_is_logged_and_nothing_is_raised(self, caplog):
        with patch.object(run_status, "get_code_collection_async", AsyncMock(return_value=None)):
            assert await proposals_mod.propose_run_record_removal("src", "atlas") is None
        assert "src" in caplog.text and "codebase_run_src" in caplog.text

    @pytest.mark.asyncio
    async def test_the_removal_is_audited_durably_and_a_failed_audit_is_noted_not_repeated(self, collection):
        await record_run_started("src", "run-1")
        session = MagicMock(add=MagicMock(), commit=AsyncMock())
        approval = SimpleNamespace(
            id="a3", context={"action": action_mod.ACTION, "source_id": "src"}, decided_by_user="u"
        )
        with patch.object(action_mod, "audit_log", AsyncMock(return_value=False)) as audit:
            await action_mod.execute_source_run_record_cleanup(approval, session)
        assert audit.await_args.kwargs["durable"] is True
        assert session.add.call_count == 2, "the outcome comment and the audit-failure note"
        assert "codebase_run_src" not in collection.docs
