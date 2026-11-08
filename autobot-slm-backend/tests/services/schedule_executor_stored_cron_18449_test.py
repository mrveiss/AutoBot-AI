# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Stored SLM schedules: the startup scan reports an invalid cron and changes nothing (#18449)."""

import importlib.util
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from testkit.fake_async_session import FakeAsyncSession

_PATH = Path(__file__).resolve().parents[2] / "services" / "schedule_executor.py"


@pytest.fixture
def executor():
    try:
        spec = importlib.util.spec_from_file_location("_schedule_executor_18449", _PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except ImportError as exc:  # the executor needs the live SLM service graph
        pytest.skip(f"schedule_executor not importable in this harness: {exc}")
    return module


def _schedule(sid, expr):
    return SimpleNamespace(id=sid, cron_expression=expr, last_run_status=None, last_run_message=None)


@pytest.mark.asyncio
async def test_startup_scan_warns_per_invalid_schedule_and_changes_nothing(executor, monkeypatch, caplog):
    rows = [_schedule("s-six", "* * * * * *"), _schedule("s-ok", "*/5 * * * *"), _schedule("s-range", "0 0 * 0-7 *")]
    monkeypatch.setattr(executor, "db_service", SimpleNamespace(session=lambda: FakeAsyncSession(default_result=rows)))
    monkeypatch.setattr(executor, "select", lambda *_a: object())  # models.database is stubbed in this harness
    with caplog.at_level(logging.WARNING, logger=executor.logger.name):
        assert await executor.report_stored_schedules() == 2
    assert "s-six" in caplog.text and "s-range" in caplog.text and "schedule.invalid_cron" in caplog.text
    assert "s-ok" not in caplog.text
    assert all(r.last_run_status is None and r.last_run_message is None for r in rows)


@pytest.mark.asyncio
async def test_startup_scan_survives_a_database_failure(executor, monkeypatch):
    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(executor, "db_service", SimpleNamespace(session=_boom))
    assert await executor.report_stored_schedules() == 0


def test_slm_keeps_croniters_standard_or_semantics(executor):
    """Unchanged by #18449: the SLM executor computes with croniter's default day handling."""
    from datetime import datetime, timezone

    base = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)  # a Monday
    assert executor.calculate_next_run("0 0 1 * 1", base) == datetime(2026, 10, 19, 0, 0, tzinfo=timezone.utc)
