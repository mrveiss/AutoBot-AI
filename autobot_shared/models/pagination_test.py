# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for autobot_shared.models.pagination (#3546)."""

from unittest.mock import MagicMock

from autobot_shared.models.pagination import PaginationParams, apply_pagination

# ---------------------------------------------------------------------------
# apply_pagination tests
# ---------------------------------------------------------------------------


def test_apply_pagination_normal_case() -> None:
    """Returns the correct slice for a mid-list offset and modest limit."""
    items = list(range(10))
    p = MagicMock(spec=PaginationParams)
    p.offset = 2
    p.limit = 3
    assert apply_pagination(items, p) == [2, 3, 4]


def test_apply_pagination_empty_list() -> None:
    """Returns an empty list when the source list is empty."""
    p = MagicMock(spec=PaginationParams)
    p.offset = 0
    p.limit = 50
    assert apply_pagination([], p) == []


def test_apply_pagination_offset_beyond_end() -> None:
    """Returns an empty list when offset exceeds list length."""
    items = [1, 2, 3]
    p = MagicMock(spec=PaginationParams)
    p.offset = 10
    p.limit = 5
    assert apply_pagination(items, p) == []


def test_apply_pagination_limit_one() -> None:
    """Returns exactly one item when limit=1."""
    items = list(range(5))
    p = MagicMock(spec=PaginationParams)
    p.offset = 0
    p.limit = 1
    assert apply_pagination(items, p) == [0]


def test_apply_pagination_limit_exceeds_remaining() -> None:
    """Does not raise when limit would go past the end of the list."""
    items = [10, 20, 30]
    p = MagicMock(spec=PaginationParams)
    p.offset = 1
    p.limit = 100
    assert apply_pagination(items, p) == [20, 30]


def test_apply_pagination_offset_zero() -> None:
    """Returns first N items when offset is 0."""
    items = list(range(20))
    p = MagicMock(spec=PaginationParams)
    p.offset = 0
    p.limit = 5
    assert apply_pagination(items, p) == list(range(5))


# ---------------------------------------------------------------------------
# PaginationParams instantiation tests (defaults and boundaries)
# ---------------------------------------------------------------------------


def _make_params(limit=50, offset=0) -> PaginationParams:
    """Bypass FastAPI Query parsing and construct directly."""
    obj = object.__new__(PaginationParams)
    obj.limit = limit
    obj.offset = offset
    return obj


def test_pagination_params_defaults() -> None:
    """Default limit is 50 and default offset is 0."""
    p = _make_params()
    assert p.limit == 50
    assert p.offset == 0


def test_pagination_params_custom_values() -> None:
    """Custom limit and offset are stored correctly."""
    p = _make_params(limit=200, offset=100)
    assert p.limit == 200
    assert p.offset == 100
