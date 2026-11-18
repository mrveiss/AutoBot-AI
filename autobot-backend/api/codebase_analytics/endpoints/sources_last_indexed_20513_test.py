# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A source reports its own last_indexed, never the global stats document's (#20513)."""

from unittest.mock import AsyncMock, patch

import pytest

from api.codebase_analytics.endpoints.sources import _get_last_indexed

GLOBAL_DOC = {"last_indexed": "another-tree"}


def _collection(docs: dict) -> AsyncMock:
    async def get(ids, include):
        return {"metadatas": [docs[i] for i in ids if i in docs]}

    collection = AsyncMock()
    collection.get.side_effect = get
    return collection


async def _read(docs: dict) -> str | None:
    with patch(
        "api.codebase_analytics.storage.get_code_collection_async",
        new=AsyncMock(return_value=_collection(docs)),
    ):
        return await _get_last_indexed("a")


@pytest.mark.asyncio
async def test_a_source_reads_its_own_document() -> None:
    docs = {"codebase_stats_a": {"last_indexed": "mine"}, "codebase_stats": GLOBAL_DOC}
    assert await _read(docs) == "mine"


@pytest.mark.asyncio
async def test_a_source_without_a_document_does_not_read_the_global_one() -> None:
    assert await _read({"codebase_stats": GLOBAL_DOC}) is None


@pytest.mark.asyncio
async def test_a_source_does_not_read_another_sources_document() -> None:
    assert await _read({"codebase_stats_b": {"last_indexed": "theirs"}}) is None
