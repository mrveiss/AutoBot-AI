# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Shared pagination helpers for FastAPI endpoints (#3546).

Provides a reusable :class:`PaginationParams` dependency and an
:func:`apply_pagination` helper so every list endpoint gets consistent
``limit`` / ``offset`` query parameters without repeating the same
``Query(...)`` declarations.

Usage::

    from autobot_shared.models.pagination import PaginationParams, apply_pagination
    from fastapi import Depends

    @router.get("/items")
    async def list_items(pagination: PaginationParams = Depends()):
        items = await fetch_all_items()
        return apply_pagination(items, pagination)
"""

from fastapi import Query


class PaginationParams:
    """FastAPI dependency that injects standard ``limit`` / ``offset`` query params.

    Use with ``Depends()``::

        async def my_endpoint(pagination: PaginationParams = Depends()) -> None:
            ...
            results = await svc.list(limit=pagination.limit, offset=pagination.offset)

    Attributes:
        limit: Maximum number of items to return (1–1000, default 50).
        offset: Number of items to skip before returning results (default 0).
    """

    def __init__(
        self,
        limit: int = Query(
            default=50,
            ge=1,
            le=1000,
            description="Maximum number of items to return",
        ),
        offset: int = Query(
            default=0,
            ge=0,
            description="Number of items to skip before returning results",
        ),
    ) -> None:
        self.limit = limit
        self.offset = offset


def apply_pagination(items: list, pagination: PaginationParams) -> list:
    """Slice *items* according to *pagination*.

    Intended for in-memory lists that are already fully loaded. For
    database-backed queries pass ``pagination.limit`` and
    ``pagination.offset`` directly to the query layer instead.

    Args:
        items: Full list of items to paginate.
        pagination: Resolved :class:`PaginationParams` dependency.

    Returns:
        A slice of *items* starting at ``pagination.offset`` with at most
        ``pagination.limit`` elements. Returns an empty list when
        ``pagination.offset`` is beyond the end of the list.
    """
    return items[pagination.offset : pagination.offset + pagination.limit]
