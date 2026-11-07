# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Source lookups of the visibility pass are de-duplicated and bounded (#16665)."""

import threading

import pytest

from autobot_shared.scoping import Principal
from knowledge import summary_visibility
from knowledge.read_path_fakes_16665 import FakeKB
from knowledge.search_filters import KbReader


class _CountingKB(FakeKB):
    def __init__(self):
        super().__init__()
        self.calls, self.live, self.peak = [], 0, 0
        self.lock = threading.Lock()

    def get_fact(self, fact_id):
        with self.lock:
            self.calls.append(fact_id)
            self.live += 1
            self.peak = max(self.peak, self.live)
        import time

        time.sleep(0.01)
        with self.lock:
            self.live -= 1
        return {"fact_id": fact_id, "metadata": {"owner_id": "x", "visibility": "system"}}


@pytest.mark.asyncio
async def test_each_source_is_looked_up_once_and_concurrency_is_bounded(monkeypatch):
    monkeypatch.setattr(summary_visibility, "SOURCE_LOOKUP_CONCURRENCY", 3)
    kb = _CountingKB()
    items = [{"id": str(i), "source_document_id": f"d{i % 10}"} for i in range(40)]
    reader = KbReader(Principal(user_id="u", company_id=None, group_ids=frozenset(), is_authenticated=True))

    kept = await summary_visibility.visible_events(items, kb, reader)

    assert len(kept) == 40 and sorted(kb.calls) == sorted({f"d{i}" for i in range(10)})
    assert 1 < kb.peak <= 3
