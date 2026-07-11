# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11675: WorkItemService._next_identifier must bump organizations.issue_counter
(companies are Organization rows) — the legacy `llc_companies` table never
existed, so the old UPDATE raised UndefinedTable, and because it ran in the outer
transaction it aborted the whole create → every work-item INSERT failed with
InFailedSQLTransactionError. The bump now runs inside a SAVEPOINT so a failure
can't poison the create transaction.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _svc():
    try:
        from llc.services.work_item_service import WorkItemService
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"llc not importable here: {exc}")
    return WorkItemService()


class _NestedCM:
    entered = False

    async def __aenter__(self):
        type(self).entered = True
        return self

    async def __aexit__(self, *a):
        return False


def _session(execute):
    s = MagicMock()
    s.begin_nested = MagicMock(return_value=_NestedCM())
    s.execute = execute
    return s


@pytest.mark.asyncio
async def test_next_identifier_targets_organizations_in_savepoint():
    _NestedCM.entered = False
    captured = {}

    async def execute(clause, params):
        captured["sql"] = str(clause)
        return SimpleNamespace(fetchone=lambda: SimpleNamespace(issue_prefix="MVT", issue_counter=1))

    ident = await _svc()._next_identifier(_session(AsyncMock(side_effect=execute)), "co-1")

    assert ident == "MVT-1"
    assert "organizations" in captured["sql"]
    assert "llc_companies" not in captured["sql"]
    assert _NestedCM.entered, "the counter bump must run inside a SAVEPOINT (begin_nested)"


@pytest.mark.asyncio
async def test_next_identifier_falls_back_without_poisoning_on_failure():
    from sqlalchemy.exc import ProgrammingError

    _NestedCM.entered = False

    async def boom(clause, params):
        raise ProgrammingError("UPDATE organizations", {}, Exception("relation does not exist"))

    ident = await _svc()._next_identifier(_session(AsyncMock(side_effect=boom)), "co-1")

    # Fallback identifier, exception swallowed, SAVEPOINT was used for isolation.
    assert ident.startswith("WI-")
    assert _NestedCM.entered
