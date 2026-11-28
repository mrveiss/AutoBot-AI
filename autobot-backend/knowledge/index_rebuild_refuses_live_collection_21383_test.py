# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""``rebuild_chromadb_index`` deletes its target first, so it refuses the live collection (#21383).

Fakes only: no ChromaDB is opened.
"""

import types
from unittest.mock import AsyncMock

import pytest

from knowledge.index import IndexMixin

LIVE = "autobot_knowledge"


def _kb():
    kb = IndexMixin.__new__(IndexMixin)
    kb.initialized = True
    kb.chromadb_collection = LIVE
    kb.chromadb_path = "/nonexistent"
    return kb


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [LIVE])
async def test_a_target_equal_to_the_live_collection_is_refused_before_anything_is_opened(monkeypatch, target):
    kb = _kb()
    opened = AsyncMock()
    monkeypatch.setattr("knowledge.backends.get_default_client", opened)
    reply = await kb.rebuild_chromadb_index(new_collection_name=target)
    assert reply["status"] == "error" and "live collection" in reply["message"]
    opened.assert_not_called()


@pytest.mark.asyncio
async def test_another_target_is_not_refused_by_that_check(monkeypatch):
    kb = _kb()
    seen = types.SimpleNamespace(called=False)

    def open_client(**kwargs):
        seen.called = True
        raise RuntimeError("stop here")

    monkeypatch.setattr("knowledge.backends.get_default_client", open_client)
    reply = await kb.rebuild_chromadb_index(new_collection_name=f"{LIVE}_optimized")
    assert seen.called and reply["status"] == "error" and "live collection" not in reply["message"]
