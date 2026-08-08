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
