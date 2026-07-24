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


def _rel(rid, target_id="t-1"):
    return SimpleNamespace(id=rid, relation_type="blocks", target_id=target_id)


class _FakeSession:
    """Session whose execute() returns the given target column-rows (#11686:
    _relations_to_list bulk-fetches target identifier/title/status by id)."""

    def __init__(self, *target_rows):
        self._rows = list(target_rows)

    async def execute(self, *_args, **_kwargs):
        return list(self._rows)


def _target_row(tid, identifier, title, status):
    return SimpleNamespace(id=tid, identifier=identifier, title=title, status=status)


@pytest.mark.asyncio
async def test_relations_to_list_serializes_target_fields():
    from llc.api import work_items

    item = SimpleNamespace(awaitable_attrs=_Awaitable(outgoing_relations=[_rel("r-1")]))
    session = _FakeSession(_target_row("t-1", "MVT-9", "Target", "open"))

    rows = await work_items._relations_to_list(item, session)

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
    # a MissingGreenlet and without hitting the database.
    from llc.api import work_items

    item = SimpleNamespace(awaitable_attrs=_Awaitable(outgoing_relations=[]))
    assert await work_items._relations_to_list(item, _FakeSession()) == []


@pytest.mark.asyncio
async def test_relations_to_list_handles_null_target():
    # A relation whose target row is missing serializes None fields, not a crash.
    from llc.api import work_items

    item = SimpleNamespace(awaitable_attrs=_Awaitable(outgoing_relations=[_rel("r-2")]))
    rows = await work_items._relations_to_list(item, _FakeSession())  # no target rows
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


@pytest.mark.asyncio
async def test_relations_to_list_single_query_for_many_relations():
    # #11686: N relations resolve their targets in ONE bulk query, not N (no N+1).
    from llc.api import work_items

    rels = [_rel(f"r-{i}", target_id=f"t-{i}") for i in range(5)]
    item = SimpleNamespace(awaitable_attrs=_Awaitable(outgoing_relations=rels))

    class _CountingSession(_FakeSession):
        def __init__(self, *rows):
            super().__init__(*rows)
            self.execute_calls = 0

        async def execute(self, *a, **k):
            self.execute_calls += 1
            return await super().execute(*a, **k)

    session = _CountingSession(*[_target_row(f"t-{i}", f"MVT-{i}", f"T{i}", "open") for i in range(5)])

    rows = await work_items._relations_to_list(item, session)

    assert len(rows) == 5
    assert session.execute_calls == 1, "targets must be batch-fetched in a single query"
    assert rows[3]["target_identifier"] == "MVT-3"
