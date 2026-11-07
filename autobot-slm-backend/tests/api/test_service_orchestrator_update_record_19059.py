# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``ServiceOrchestrator._update_service_record`` goes through the shared upsert core (#19059)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_orm_import import import_modules_with_real_orm  # noqa: E402

# `services` is a stub tree in this suite, so a plain import yields MagicMocks; load the real
# chain by file -- the categorizer and the unit-name guard decide what the core writes.
_SERVICES = Path(__file__).resolve().parents[2] / "services"
_categorizer, _unit_names, _upsert, _orch = import_modules_with_real_orm(
    import_names=(),
    path_loaded={
        "services.service_categorizer": _SERVICES / "service_categorizer.py",
        "services.unit_names": _SERVICES / "unit_names.py",
        "services.service_upsert": _SERVICES / "service_upsert.py",
        "services.service_orchestrator": _SERVICES / "service_orchestrator.py",
    },
)
categorize_service = _categorizer.categorize_service
ServiceOrchestrator = _orch.ServiceOrchestrator
_LOGGER = _orch.logger.name

_NODE = "node-1"


def _db(existing=None) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


def test_the_real_chain_was_loaded_not_a_stub():
    assert not isinstance(ServiceOrchestrator, MagicMock)
    assert not isinstance(categorize_service, MagicMock)


def _orchestrator():
    return ServiceOrchestrator.__new__(ServiceOrchestrator)


@pytest.mark.asyncio
async def test_new_row_gets_categorized_and_commits():
    db = _db()
    await _orchestrator()._update_service_record(db, _NODE, "redis-server.service", "running")
    row = db.add.call_args.args[0]
    assert row.category == categorize_service("redis-server.service")
    assert (row.node_id, row.service_name, row.status) == (_NODE, "redis-server.service", "running")
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_existing_row_is_updated_not_added():
    existing = MagicMock()
    db = _db(existing)
    await _orchestrator()._update_service_record(db, _NODE, "redis-server.service", "stopped")
    assert existing.status == "stopped"
    assert existing.last_checked is not None
    db.add.assert_not_called()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_refused_name_warns_naming_service_and_node(caplog):
    db = _db()
    bad = "evil\nFORGED level=CRITICAL"
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        await _orchestrator()._update_service_record(db, _NODE, bad, "running")
    msgs = [r.getMessage() for r in caplog.records if r.name == _LOGGER]
    # #19123 review: the refused service is named with the node, in one line, escaped and bounded.
    assert any(_NODE in m and "evil\\nFORGED" in m for m in msgs), msgs
    assert not any("\n" in m for m in msgs), "a raw newline would let node input forge a log line"
    db.add.assert_not_called()
