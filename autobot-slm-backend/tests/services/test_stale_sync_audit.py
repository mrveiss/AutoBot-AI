# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The stale-file cleanup audit goes through the SLM's one ``audit_logs`` writer, never a store of its own (#22033).

``rollback_audit.record_audit_step`` is that writer (#17225 lists it); these checks run it with the session
and the row constructor stubbed: the row it adds, a session that fails, and an outcome outside the four.
"""

from __future__ import annotations

import sys
import types
from contextlib import asynccontextmanager

import pytest

from services import rollback_audit, stale_sync_audit


def _session_module(monkeypatch, added: list, fail: bool = False) -> None:
    @asynccontextmanager
    async def get_slm_session():
        if fail:
            raise OSError("database down")
        yield types.SimpleNamespace(add=added.append)

    module = types.ModuleType("user_management.database")
    module.get_slm_session = get_slm_session
    monkeypatch.setitem(sys.modules, "user_management.database", module)
    rows = types.ModuleType("autobot_shared.user_management.audit_rows")
    rows.audit_row = lambda **fields: types.SimpleNamespace(**fields)  # the one row constructor, recorded as built
    monkeypatch.setitem(sys.modules, "autobot_shared.user_management.audit_rows", rows)


async def test_a_cleanup_step_is_one_audit_logs_row_through_the_shared_writer(monkeypatch) -> None:
    added: list = []
    _session_module(monkeypatch, added)
    await stale_sync_audit.record_cleanup_step(actor="a", node_id="n1", outcome="success", phase="intent", stale=2)
    (row,) = added
    assert row.action == stale_sync_audit.ACTION
    assert row.details["phase"] == "intent" and row.details["stale"] == 2


async def test_a_store_that_fails_is_the_cleanups_own_error_and_nothing_else(monkeypatch) -> None:
    _session_module(monkeypatch, [], fail=True)
    with pytest.raises(stale_sync_audit.StaleFileAuditUnavailable):
        await stale_sync_audit.record_cleanup_step(actor="a", node_id="n1", outcome="success", phase="intent")
    with pytest.raises(rollback_audit.RollbackAuditUnavailable):
        await rollback_audit.record_rollback(actor="a", commit="c", outcome="success", phase="requested")


async def test_an_outcome_outside_the_four_is_refused_before_any_write(monkeypatch) -> None:
    added: list = []
    _session_module(monkeypatch, added)
    with pytest.raises(ValueError):
        await stale_sync_audit.record_cleanup_step(actor="a", node_id="n1", outcome="maybe", phase="intent")
    assert added == []
