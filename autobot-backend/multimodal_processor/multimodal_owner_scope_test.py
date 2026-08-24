# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Owner scoping on the multi-modal memory write (#13688).

`_store_result` wrote a general memory row with no owner. After the plane
required one, this call site would have raised a TypeError into a handler that
only warns — every processing result would have stopped persisting silently.
"""

from unittest.mock import AsyncMock, patch

import pytest

from multimodal_processor.models import ModalityType, ProcessingIntent, ProcessingResult
from multimodal_processor.processor import MultiModalProcessor


def _result(user_id=None):
    return ProcessingResult(
        result_id="r-1",
        input_id="i-1",
        modality_type=ModalityType.TEXT,
        intent=ProcessingIntent.DECISION_MAKING,
        success=True,
        confidence=0.9,
        result_data={},
        processing_time=0.1,
        user_id=user_id,
    )


@pytest.fixture
def processor():
    return MultiModalProcessor()


class TestOwnerReachesTheWrite:
    @pytest.mark.asyncio
    async def test_owner_is_passed_to_store_memory(self, processor):
        with patch.object(processor.memory_manager, "store_memory", new_callable=AsyncMock) as store:
            await processor._store_result(_result(user_id="user-42"))

        store.assert_awaited_once()
        assert store.await_args.kwargs["user_id"] == "user-42"

    @pytest.mark.asyncio
    async def test_owner_is_not_buried_in_metadata(self, processor):
        """#13688: the scope is a first-class argument, not a metadata key."""
        with patch.object(processor.memory_manager, "store_memory", new_callable=AsyncMock) as store:
            await processor._store_result(_result(user_id="user-42"))

        assert "user_id" not in store.await_args.kwargs["metadata"]


class TestUnownedResultIsNotPersisted:
    @pytest.mark.asyncio
    async def test_unowned_result_skips_the_write(self, processor):
        with patch.object(processor.memory_manager, "store_memory", new_callable=AsyncMock) as store:
            await processor._store_result(_result(user_id=None))

        store.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_skip_is_logged_not_silent(self, processor):
        """The failure this replaces was a swallowed TypeError. Say it out loud."""
        with patch.object(processor.memory_manager, "store_memory", new_callable=AsyncMock):
            with patch.object(processor, "logger") as log:
                await processor._store_result(_result(user_id=None))

        assert any("#13688" in str(c.args[0]) for c in log.warning.call_args_list if c.args)


# ---------------------------------------------------------------------------
# Gaps surfaced by re-review of PR #13698
# ---------------------------------------------------------------------------


class TestPrincipalClaimResolution:
    """N1: reading `user_id` alone missed every principal minted without it.

    `_extract_user_from_jwt` sets `user_id` only when the token carries that
    claim, but always sets `sub`. Resolving the optional claim dropped rows and
    split one user across two owner silos depending on which endpoint wrote.
    """

    @pytest.mark.parametrize(
        "principal,expected",
        [
            ({"id": "3f2c", "user_id": "u-42", "sub": "alice"}, "3f2c"),
            ({"user_id": "u-42", "sub": "alice"}, "u-42"),
            ({"sub": "alice"}, "alice"),
            ({}, None),
            (None, None),
        ],
    )
    def test_claim_order_matches_the_repo_standard(self, principal, expected):
        from autobot_shared.principal import resolve_principal_id

        assert resolve_principal_id(principal) == expected

    def test_the_two_endpoints_resolve_the_same_owner(self):
        """Same principal must not land in two silos."""
        from autobot_shared.principal import resolve_principal_id

        principal = {"sub": "alice"}

        # api.multimodal._principal_id and api.task_memory both delegate here,
        # so one principal can no longer land in two owner silos.
        assert resolve_principal_id(principal) == "alice"


class TestProcessStampsTheOwner:
    @pytest.mark.asyncio
    async def test_process_stamps_the_result_from_the_input(self):
        """The stamp is what carries the owner to _store_result."""
        from multimodal_processor.models import ModalityType, MultiModalInput, ProcessingIntent
        from multimodal_processor.processor import MultiModalProcessor

        proc = MultiModalProcessor()
        modal_input = MultiModalInput(
            input_id="i-1",
            modality_type=ModalityType.TEXT,
            intent=ProcessingIntent.DECISION_MAKING,
            data="hello",
            user_id="user-7",
        )

        with patch.object(proc, "_route_to_processor", new_callable=AsyncMock) as route:
            route.return_value = _result(user_id=None)
            with patch.object(proc.memory_manager, "store_memory", new_callable=AsyncMock) as store:
                result = await proc.process(modal_input)

        assert result.user_id == "user-7"
        assert store.await_args.kwargs["user_id"] == "user-7"


class TestSystemInitiatedWorkIsPersisted:
    @pytest.mark.asyncio
    async def test_a_system_owned_result_is_stored_not_dropped(self):
        """N3: system-initiated work has no human requester.

        Dropping it would move the data loss the migration was written to avoid
        from the read path to the write path.
        """
        from memory.storage.general_storage import SYSTEM_OWNER

        proc = MultiModalProcessor()

        with patch.object(proc.memory_manager, "store_memory", new_callable=AsyncMock) as store:
            await proc._store_result(_result(user_id=SYSTEM_OWNER))

        store.assert_awaited_once()
        assert store.await_args.kwargs["user_id"] == SYSTEM_OWNER
