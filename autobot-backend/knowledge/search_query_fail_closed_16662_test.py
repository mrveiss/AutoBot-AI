# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed filtered ChromaDB query returns nothing -- it never retries without the
filter, which may carry the caller's permission scope or the research quarantine (#16662).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from knowledge.search import SearchMixin

_EMPTY = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}


def _searcher(query: MagicMock) -> SearchMixin:
    searcher = SearchMixin.__new__(SearchMixin)
    searcher.vector_store = SimpleNamespace(_collection=SimpleNamespace(name="facts", query=query))
    return searcher


@pytest.mark.asyncio
async def test_a_failed_filtered_query_returns_nothing_and_is_not_retried_unfiltered():
    query = MagicMock(side_effect=ValueError("where matched fewer than n_results"))
    result = await _searcher(query)._query_chromadb([0.1], 5, where={"owner_id": "user-1"})

    assert result == _EMPTY
    assert query.call_count == 1
    assert all("where" in call.kwargs for call in query.call_args_list)


@pytest.mark.asyncio
async def test_an_unfiltered_query_is_still_retried_once():
    query = MagicMock(side_effect=[RuntimeError("transient"), {"ids": [["a"]]}])
    result = await _searcher(query)._query_chromadb([0.1], 5)

    assert result == {"ids": [["a"]]}
    assert query.call_count == 2
