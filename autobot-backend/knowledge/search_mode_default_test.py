# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``mode="auto"`` -> hybrid default in ``SearchMixin.search`` (#14047).

``search()`` is heavy (vector engine, reranking, ...), so the "filtered" path
is exercised (``category`` set, no advanced params) which routes through
``_run_search`` after building a ``SearchContext``. ``_run_search`` is
stubbed to capture the resolved ``mode`` without doing real work.
"""

import pytest

from constants.threshold_constants import CategoryDefaults
from knowledge.search import SearchMixin


class _CapturingSearch(SearchMixin):
    def __init__(self):
        self.captured_mode = None

    async def _run_search(self, **kwargs):  # noqa: D401 - test stub
        self.captured_mode = kwargs["mode"]
        return []


@pytest.mark.asyncio
async def test_mode_auto_resolves_to_hybrid_default():
    mixer = _CapturingSearch()

    await mixer.search("q", category="docs", mode="auto")

    assert mixer.captured_mode == CategoryDefaults.SEARCH_MODE_HYBRID


@pytest.mark.asyncio
async def test_explicit_mode_overrides_auto_default():
    mixer = _CapturingSearch()

    await mixer.search("q", category="docs", mode="semantic")

    assert mixer.captured_mode == "semantic"
