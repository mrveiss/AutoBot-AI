# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for Postgres-dependent startup gating in single_user (#9783).

In single_user mode get_async_session_factory() hard-raises. These startup
steps must skip cleanly (one INFO line) instead of proceeding to the session
factory and catching a scary RuntimeError as a WARNING.

NOTE: initialization.lifespan is imported lazily inside the fixture (not at
module top). Importing it resolves the ambiguous top-level ``tests`` package to
the repo-root namespace, which would shadow ``autobot-backend/tests`` and break
sibling tests' ``from tests.fixtures`` import if it happened at collection time.
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def gated(monkeypatch):
    """Patch Postgres off and intercept the session factory; yield the module."""
    import initialization.lifespan as L
    import user_management.database as db

    monkeypatch.setattr(L, "_llc_postgres_available", lambda: False)
    # If any gate is missing the step reaches this factory (which raises in
    # single_user). Replace it with a sentinel we can assert was never touched.
    factory = MagicMock(name="get_async_session_factory")
    monkeypatch.setattr(db, "get_async_session_factory", factory)
    return SimpleNamespace(L=L, factory=factory)


def _app():
    return SimpleNamespace(state=SimpleNamespace())


def _skipped(caplog):
    return any("skipped (Postgres disabled" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_heartbeat_scheduler_skips_when_postgres_disabled(gated, caplog):
    app = _app()
    with caplog.at_level(logging.INFO):
        await gated.L._init_heartbeat_scheduler(app)
    assert app.state.heartbeat_scheduler is None
    gated.factory.assert_not_called()
    assert _skipped(caplog)


@pytest.mark.asyncio
async def test_process_adapter_skips_when_postgres_disabled(gated, caplog):
    app = _app()
    with caplog.at_level(logging.INFO):
        await gated.L._init_process_adapter(app)
    assert app.state.process_adapter_service is None
    gated.factory.assert_not_called()
    assert _skipped(caplog)


@pytest.mark.asyncio
async def test_agent_registry_seed_skips_when_postgres_disabled(gated, caplog):
    with caplog.at_level(logging.INFO):
        await gated.L._seed_agent_registry()
    gated.factory.assert_not_called()
    assert _skipped(caplog)


@pytest.mark.asyncio
async def test_routine_scheduler_skips_when_postgres_disabled(gated, caplog):
    app = _app()
    with caplog.at_level(logging.INFO):
        await gated.L._init_llc_routine_scheduler(app)
    assert _skipped(caplog)
