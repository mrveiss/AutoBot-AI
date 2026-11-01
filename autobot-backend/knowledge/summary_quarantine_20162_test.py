# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A summary with no quarantine marker is withheld when its source fact is quarantined (#20162)."""

import pytest

from autobot_shared.scoping import Principal
from autobot_shared.ssot_config import config
from knowledge import summary_visibility
from knowledge.read_path_fakes_16665 import FakeKB
from knowledge.search_filters import KbReader

SOURCES = {
    "q": {"owner_id": "admin", "visibility": "system", "collection": config.research_quarantine_collection},
    "ok": {"owner_id": "admin", "visibility": "system"},
}


class _KB(FakeKB):
    def get_fact(self, fact_id):
        meta = SOURCES.get(fact_id)
        return {"fact_id": fact_id, "content": "x", "metadata": meta} if meta else None


def _summary(name, doc):
    return {"id": name, "metadata": {"document_id": doc, "level": "document"}}


def _reader(admin):
    principal = Principal(user_id="u", company_id=None, group_ids=frozenset(), is_authenticated=True)
    return KbReader(principal, is_admin=admin) if admin else KbReader(principal)


@pytest.mark.asyncio
@pytest.mark.parametrize("admin", [False, True])
async def test_a_markerless_summary_of_a_quarantined_source_is_withheld(admin):
    items = [_summary("old-q", "q"), _summary("old-ok", "ok"), _summary("orphan", "gone")]

    kept = await summary_visibility.visible_summaries(items, _KB(), _reader(admin))

    assert [s["id"] for s in kept] == ["old-ok"]


@pytest.mark.asyncio
async def test_document_is_visible_is_false_for_a_quarantined_source():
    kb, reader = _KB(), _reader(False)

    assert not await summary_visibility.document_is_visible("q", kb, reader)
    assert await summary_visibility.document_is_visible("ok", kb, reader)
