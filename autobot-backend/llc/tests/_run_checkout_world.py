# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Runs and work-item checkouts answering a session by the predicates the code asks with (#19601).

A release the code does not ask for is a release that does not happen: the session returns an item
only when its ``checkout_run_id`` is among the statement's bound values, and a run only for a
statement on ``LLCHeartbeatRun``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from testkit.fake_async_session import FakeAsyncSession
from testkit.fake_result import FakeResult


class Item:
    """A work item with only what a release reads and writes."""

    def __init__(self, company_id: uuid.UUID, checkout_run_id: Optional[uuid.UUID | str] = None) -> None:
        self.id = uuid.uuid4()
        self.company_id = company_id
        self.assignee_agent_id = uuid.uuid4()
        self.checkout_run_id = str(checkout_run_id) if checkout_run_id else None
        self.checkout_locked_at = datetime.now(timezone.utc) if checkout_run_id else None
        self.version = 1
        self.status = "in_progress"
        self.identifier = f"WI-{self.id.hex[:6]}"
        self.parent_id = self.goal_id = self.project_id = None

    @property
    def fence(self) -> str:
        """The fence value ``checkout`` wrote for this item."""
        return f"{self.assignee_agent_id}#{self.checkout_run_id}"


def bound_values(statement: Any) -> list:
    values: list = []
    for value in statement.compile().params.values():
        values.extend(value if isinstance(value, (list, tuple)) else [value])
    return values


class RoutedSession(FakeAsyncSession):
    """Answers ``LLCHeartbeatRun`` statements with *runs* and ``LLCWorkItem`` ones by ``checkout_run_id``."""

    def __init__(self, runs: list, items: list) -> None:
        super().__init__(assign_ids=uuid.uuid4, default_result=FakeResult([]))
        self.runs, self.items = runs, items

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> FakeResult:
        self.statements.append(statement)
        described = getattr(statement, "column_descriptions", None)
        entity = described[0]["entity"].__name__ if described else None
        if entity == "LLCHeartbeatRun":
            return FakeResult(self.runs)
        if entity == "LLCWorkItem":
            bound = bound_values(statement)
            return FakeResult([i for i in self.items if i.checkout_run_id in bound])
        return FakeResult([])


class AgedRoutedSession(RoutedSession):
    """A :class:`RoutedSession` that also applies a run query's ``started_at < cutoff`` bound.

    Only for code that selects runs by age: a run is returned when its ``started_at`` is before the datetime
    the statement binds, so a run younger than the cutoff is not recovered by this fake any more than by SQL.
    """

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> FakeResult:
        result = await super().execute(statement, *args, **kwargs)
        described = getattr(statement, "column_descriptions", None)
        if not described or described[0]["entity"].__name__ != "LLCHeartbeatRun":
            return result
        cutoff = next(v for v in bound_values(statement) if isinstance(v, datetime))
        return FakeResult([r for r in self.runs if r.started_at < cutoff])


class Recorder:
    """The activity log: keeps each entry written."""

    def __init__(self) -> None:
        self.entries: list[dict] = []

    async def record(self, session: Any, **entry: Any) -> None:
        self.entries.append(entry)


class QueueSession(FakeAsyncSession):
    """Answers the work queue's SELECT by the predicates it binds: ``ready``, no checkout, this agent's or unassigned.

    The queue's own WHERE clauses decide what is offered; a sqlite fake cannot run them, so the bound values
    stand in: an item is returned when its status is among them, it holds no checkout and its assignee is bound.
    """

    def __init__(self, items: list) -> None:
        super().__init__(assign_ids=uuid.uuid4, default_result=FakeResult([]))
        self.items = items

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> FakeResult:
        bound = bound_values(statement)
        return FakeResult(
            [i for i in self.items if i.status in bound and i.checkout_run_id is None and i.assignee_agent_id in bound]
        )
