# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`page` actually moves the window (#15186).

The route accepted `page`, validated it, echoed it back in the response — and
then called the fetch helper with `per_page` alone. Every page returned the
newest `per_page` messages, so page 2 was byte-identical to page 1 while the
payload said `"page": 2`. A response that reports a page it did not honour is
worse than one that rejects the parameter, because the client cannot tell.

These assert the property the route claims rather than the call shape: an
implementation that accepted `offset` and ignored it would pass a test that only
checked the argument was forwarded, which is the shape of the original defect.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from chat_history.messages import MessagesMixin


def _rows(count: int) -> List[Dict[str, Any]]:
    """Oldest first, matching what `load_session` returns."""
    return [{"id": f"m{i}", "text": f"message {i}"} for i in range(count)]


@pytest.fixture
def manager(monkeypatch):
    # The mixin, not a full manager: `get_session_messages` needs only
    # `load_session`, and constructing the real manager drags in file IO and a
    # context manager that have nothing to do with the slice under test.
    mgr = MessagesMixin.__new__(MessagesMixin)

    async def _load(_session_id):
        return _rows(10)

    monkeypatch.setattr(mgr, "load_session", _load, raising=False)
    return mgr


def _page(mgr, page: int, per_page: int) -> List[Dict[str, Any]]:
    return asyncio.run(mgr.get_session_messages("s1", limit=per_page, offset=(page - 1) * per_page))


def test_page_one_is_unchanged_by_the_fix(manager) -> None:
    """The direction that matters most: `limit` alone already meant "the newest
    N", and every existing caller passes only that. Page 1 must still be it."""
    assert [m["id"] for m in _page(manager, 1, 3)] == ["m7", "m8", "m9"]


def test_page_two_returns_different_rows_than_page_one(manager) -> None:
    """The defect, stated directly."""
    first = _page(manager, 1, 3)
    second = _page(manager, 2, 3)

    assert first != second, "page 2 returned the same rows as page 1 — `page` is not applied"
    assert [m["id"] for m in second] == ["m4", "m5", "m6"]


def test_the_window_walks_backwards_from_the_newest(manager) -> None:
    """Paging goes into the past, because that is what `limit` alone meant.

    Reversing the direction would have been a silent behaviour change for every
    caller that passes `limit` and no `offset`.
    """
    pages = [[m["id"] for m in _page(manager, p, 2)] for p in (1, 2, 3)]

    assert pages == [["m8", "m9"], ["m6", "m7"], ["m4", "m5"]]


def test_pages_do_not_overlap_and_cover_every_row(manager) -> None:
    seen: List[str] = []
    for page in range(1, 6):
        seen.extend(m["id"] for m in _page(manager, page, 2))

    assert len(seen) == len(set(seen)), f"pages overlap: {seen}"
    assert set(seen) == {f"m{i}" for i in range(10)}


def test_paging_past_the_beginning_returns_empty_not_the_first_page(manager) -> None:
    """A negative slice index would wrap and hand back the newest rows again —
    the same "looks like data, is the wrong data" failure the issue is about."""
    assert _page(manager, 99, 3) == []


def test_an_offset_larger_than_the_conversation_is_empty(manager) -> None:
    assert asyncio.run(manager.get_session_messages("s1", limit=5, offset=10)) == []


def test_a_partial_final_page_returns_what_remains(manager) -> None:
    """10 rows at 4 per page: the third page holds 2, not a padded 4."""
    assert [m["id"] for m in _page(manager, 3, 4)] == ["m0", "m1"]


def test_no_offset_is_identical_to_before(manager) -> None:
    """Explicit regression pin for the default argument."""
    with_default = asyncio.run(manager.get_session_messages("s1", limit=4))
    with_zero = asyncio.run(manager.get_session_messages("s1", limit=4, offset=0))

    assert with_default == with_zero == _rows(10)[-4:]
