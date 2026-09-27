#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Moving a fact's locator drops the observations of the old one (#17545).

The #17615 review found the durable half of a mis-attribution: `update_fact` can
change `metadata.file_path`, and until now it left `source_checked_at` /
`source_seen_at` / `source_last_probe` / `source_check_failures` untouched. Those
four are statements about the document the OLD locator named. Carried across a
relocation, `source_seen_at` says a file nobody has looked at was seen -- and
#17538's retention policy reads that field as "last known good", so the wrong
facts survive a retention pass and the right ones do not.

*Never checked* is the truthful state for a locator no probe has visited, which is
what these tests pin.

The session is a fake: what is under test is which columns a relocation resets,
and a real database would add a schema round-trip without adding evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from knowledge import fact_store
from models.knowledge_fact import KnowledgeFact

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
OBSERVATION_COLUMNS = ("source_checked_at", "source_seen_at", "source_last_probe", "source_check_failures")


def _observed_fact(locator: str) -> KnowledgeFact:
    """A fact whose source was probed and resolved while at *locator*."""
    row = KnowledgeFact(id="fact-1", content="c", metadata_json={"file_path": locator})
    row.source_checked_at = NOW
    row.source_seen_at = NOW
    row.source_last_probe = "resolved"
    row.source_check_failures = 0
    return row


class _FakeSession:
    def __init__(self, row):
        self._row = row
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, fact_id):
        return self._row if self._row is not None and self._row.id == fact_id else None

    async def commit(self):
        self.committed = True


@pytest.fixture
def row_factory(monkeypatch):
    """Installs a fake session factory and hands back the row it serves."""

    def _install(row):
        monkeypatch.setattr(fact_store, "get_async_session_factory", lambda: lambda: _FakeSession(row))
        return row

    return _install


class TestARelocationResetsTheObservations:
    @pytest.mark.asyncio
    async def test_a_moved_locator_clears_all_four_observations(self, row_factory) -> None:
        row = row_factory(_observed_fact("/srv/before.pdf"))

        assert await fact_store.update_fact("fact-1", "c", {"file_path": "/srv/after.pdf"}) is True

        assert row.source_checked_at is None
        assert row.source_seen_at is None
        assert row.source_last_probe is None
        assert row.source_check_failures == 0

    @pytest.mark.asyncio
    async def test_an_unchanged_locator_keeps_them(self, row_factory) -> None:
        """The reset must not fire on every update -- a content edit is not a move."""
        row = row_factory(_observed_fact("/srv/same.pdf"))

        await fact_store.update_fact("fact-1", "new content", {"file_path": "/srv/same.pdf"})

        assert row.source_checked_at == NOW
        assert row.source_seen_at == NOW
        assert row.source_last_probe == "resolved"

    @pytest.mark.asyncio
    async def test_dropping_the_locator_entirely_also_clears_them(self, row_factory) -> None:
        """A fact that stops naming a file has no source to have seen."""
        row = row_factory(_observed_fact("/srv/before.pdf"))

        await fact_store.update_fact("fact-1", "c", {})

        assert all(getattr(row, column) in (None, 0) for column in OBSERVATION_COLUMNS)

    @pytest.mark.asyncio
    async def test_acquiring_a_locator_clears_them_too(self, row_factory) -> None:
        """None -> a path is a change of subject in the same way a move is."""
        row = _observed_fact("/srv/x.pdf")
        row.metadata_json = {}
        row_factory(row)

        await fact_store.update_fact("fact-1", "c", {"file_path": "/srv/new.pdf"})

        assert row.source_checked_at is None

    @pytest.mark.asyncio
    async def test_the_witnessed_event_is_left_alone(self, row_factory) -> None:
        """`source_gone_at` is #17546's event, and this layer does not overrule it.

        Clearing it here would be this code deciding a witnessed deletion did not
        happen. What a relocation means for that event belongs with the code that
        writes it -- stated in `update_fact`'s docstring rather than left implied.
        """
        row = _observed_fact("/srv/before.pdf")
        row.source_gone_at = NOW
        row_factory(row)

        await fact_store.update_fact("fact-1", "c", {"file_path": "/srv/after.pdf"})

        assert row.source_gone_at == NOW

    @pytest.mark.asyncio
    async def test_a_missing_fact_is_still_false(self, row_factory) -> None:
        row_factory(None)
        assert await fact_store.update_fact("nope", "c", {"file_path": "/srv/a.pdf"}) is False
