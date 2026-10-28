# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The canned answer ``FakeAsyncSession.execute`` returns (#18883)."""

from __future__ import annotations

from typing import Any, Iterator, List, Optional

from sqlalchemy.exc import MultipleResultsFound, NoResultFound


class FakeScalars:
    """What ``FakeResult.scalars()`` returns."""

    def __init__(self, rows: List[Any]) -> None:
        self._rows = rows

    def all(self) -> List[Any]:
        return list(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def __iter__(self) -> Iterator[Any]:
        return iter(self._rows)


class FakeResult:
    """A fixed list of rows with the read methods production code calls on a ``Result``."""

    def __init__(self, rows: Any = (), rowcount: Optional[int] = None) -> None:
        self._rows: List[Any] = list(rows)
        #: What a write's ``CursorResult.rowcount`` would say. ``None`` means the canned
        #: answer does not model a write; queue ``FakeResult(rowcount=0)`` to test the
        #: "matched nothing" branch (e.g. a lost RUNNING claim, #19582).
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> Any:
        if len(self._rows) > 1:
            raise MultipleResultsFound("Multiple rows were found")
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        if not self._rows:
            raise NoResultFound("No row was found when one was required")
        return self.scalar_one_or_none()

    def scalar(self) -> Any:
        return self._rows[0] if self._rows else None

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> List[Any]:
        return list(self._rows)

    def scalars(self) -> FakeScalars:
        return FakeScalars(self._rows)

    def mappings(self) -> FakeScalars:
        """``result.mappings().first()`` / ``.all()`` / iteration, over the rows as given."""
        return FakeScalars(self._rows)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._rows)
