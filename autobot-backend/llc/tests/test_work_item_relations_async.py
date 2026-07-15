# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11684: _relations_to_list must access relationships via awaitable_attrs so a
not-yet-loaded relationship (create/get/update paths) doesn't raise
MissingGreenlet under an AsyncSession. Emulates the awaitable_attrs interface.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


class _Awaitable:
    """Mimic SQLAlchemy's awaitable_attrs: attribute access returns a coroutine."""

    def __init__(self, **values):
        self._values = values

    def __getattr__(self, name):
        value = self._values[name]

        async def _coro():
            return value

        return _coro()


def _rel(rid, target):
    return SimpleNamespace(
        id=rid,
        relation_type="blocks",
        target_id="t-1",
        awaitable_attrs=_Awaitable(target=target),
    )


@pytest.mark.asyncio
async def test_relations_to_list_awaits_unloaded_relationship():
    from llc.api import work_items

    tgt = SimpleNamespace(identifier="MVT-9", title="Target", status="open")
    item = SimpleNamespace(awaitable_attrs=_Awaitable(outgoing_relations=[_rel("r-1", tgt)]))

    rows = await work_items._relations_to_list(item)

    assert rows == [
        {
            "id": "r-1",
            "type": "blocks",
            "target_id": "t-1",
            "target_identifier": "MVT-9",
            "target_title": "Target",
            "target_status": "open",
        }
    ]


@pytest.mark.asyncio
async def test_relations_to_list_empty_for_freshly_created_item():
    # The create path: a brand-new item has no relations — must return [] without
    # a MissingGreenlet.
    from llc.api import work_items

    item = SimpleNamespace(awaitable_attrs=_Awaitable(outgoing_relations=[]))
    assert await work_items._relations_to_list(item) == []


@pytest.mark.asyncio
async def test_relations_to_list_handles_null_target():
    # A relation whose target could not be resolved serializes None fields, not a crash.
    from llc.api import work_items

    item = SimpleNamespace(awaitable_attrs=_Awaitable(outgoing_relations=[_rel("r-2", None)]))
    rows = await work_items._relations_to_list(item)
    assert rows == [
        {
            "id": "r-2",
            "type": "blocks",
            "target_id": "t-1",
            "target_identifier": None,
            "target_title": None,
            "target_status": None,
        }
    ]
