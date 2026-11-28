# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A ``FakeAsyncSession`` that answers the approval gate's atomic claim (#18883).

``ApprovalGateService.approve`` / ``reject`` claim the row with one ``UPDATE ... RETURNING id``
and then re-read it. This session applies the UPDATE's SET values to the ``Approval`` that was
added, and answers every statement with that row, so propose-then-decide chains run end to end
without a database. Two test files used to carry identical copies of this logic.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from testkit.fake_async_session import FakeAsyncSession
from testkit.fake_result import FakeResult

_CLAIMED_COLUMNS = ("status", "decided_by_user", "decided_at")


class _ApprovalResult(FakeResult):
    """``first()`` is the claim's ``RETURNING id`` row; the readers return the row itself."""

    def first(self) -> Any:
        return (self._rows[0].id,)


def apply_update_claim(session: "ApprovalClaimSession", statement: Any) -> FakeResult:
    """Apply an UPDATE's SET values to the session's approval, then answer with that row."""
    approval = session.approval
    if getattr(statement, "is_update", False):
        params = statement.compile().params
        for column in _CLAIMED_COLUMNS:
            setattr(approval, column, params[column])
    return _ApprovalResult([approval])


class ApprovalClaimSession(FakeAsyncSession):
    """Mints uuid ids on add, and answers ``execute`` through :func:`apply_update_claim`."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("assign_ids", uuid.uuid4)
        kwargs.setdefault("default_result", lambda stmt: apply_update_claim(self, stmt))
        super().__init__(**kwargs)

    def add(self, instance: object, _warn: bool = True) -> None:
        # The claim reads ``approval.id`` straight after the proposal, so mint it on add.
        self._mint_id(instance)
        super().add(instance, _warn)

    @property
    def approval(self) -> Optional[Any]:
        """The most recently added ``Approval``, or ``None``."""
        from models.approval import Approval

        return next((o for o in reversed(self.added) if isinstance(o, Approval)), None)
