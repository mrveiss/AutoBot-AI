# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""next_cron_run runs on the engine the shared validator checks (#18449)."""

from datetime import datetime, timezone

import pytest

from services import trigger_service
from services.trigger_service import next_cron_run

BASE = datetime(2026, 10, 12, 12, 0, 30, tzinfo=timezone.utc)  # a Monday


def test_trigger_service_uses_the_shared_validator():
    from autobot_shared import cron_expression

    assert trigger_service.validate_cron_expression is cron_expression.validate_cron_expression


def test_every_expression_the_validator_accepts_has_a_next_run():
    """The old split (loose validator, narrow parser) would register what it could not run."""
    for expr in ("* * * * MON", "0 0 * * 7", "0 12 * JAN *"):
        assert next_cron_run(expr, after=BASE) > BASE


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("*/5 * * * *", datetime(2026, 10, 12, 12, 5, tzinfo=timezone.utc)),
        ("0 9 * * 1-5", datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)),
    ],
)
def test_common_expressions_have_the_expected_next_run(expression, expected):
    assert next_cron_run(expression, after=BASE) == expected


def test_day_names_now_schedule():
    assert next_cron_run("0 9 * * MON", after=BASE) == datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)


def test_day_of_month_and_weekday_are_still_anded():
    """Owner decision (#18449): no stored trigger changes frequency. `0 0 1 * 1` fires only on a
    Monday that is the 1st (standard cron would also fire every Monday and every 1st)."""
    assert next_cron_run("0 0 1 * 1", after=BASE) == datetime(2027, 2, 1, 0, 0, tzinfo=timezone.utc)
    assert next_cron_run("0 0 1 * 1", after=datetime(2027, 2, 1, 0, 0, tzinfo=timezone.utc)) == datetime(
        2027, 3, 1, 0, 0, tzinfo=timezone.utc
    )


def test_six_field_cron_is_refused_with_the_contract_code():
    with pytest.raises(ValueError, match="schedule.invalid_cron"):
        next_cron_run("* * * * * *", after=BASE)


def test_impossible_date_raises_value_error():
    with pytest.raises(ValueError):
        next_cron_run("0 0 31 2 *", after=BASE)


# --- stored schedules: a bad one is skipped and reported, never fatal (#18449) ---

import asyncio  # noqa: E402
import logging  # noqa: E402

from services.trigger_service import TriggerDefinition, TriggerService, TriggerType  # noqa: E402


def _cron_def(trigger_id: str, expression: str) -> TriggerDefinition:
    return TriggerDefinition(
        id=trigger_id,
        trigger_type=TriggerType.CRON,
        workflow_id="wf",
        config={"cron_expression": expression},
        conditions=[],
        enabled=True,
        created_at="2026-10-12T00:00:00+00:00",
    )


async def _start_with(monkeypatch, definitions):
    svc = TriggerService()

    async def _all():
        return definitions

    monkeypatch.setattr(svc, "_load_all_triggers", _all)

    async def _launcher(workflow_id, payload):
        return None

    await svc.start(_launcher)
    return svc


@pytest.mark.asyncio
async def test_a_bad_stored_cron_is_skipped_and_reported_while_the_others_run(monkeypatch, caplog):
    defs = [
        _cron_def("good-1", "*/5 * * * *"),
        _cron_def("bad-six-field", "* * * * * *"),
        _cron_def("bad-range", "0 0 * 0-7 *"),
        _cron_def("good-2", "0 9 * * 1"),
    ]
    with caplog.at_level(logging.WARNING, logger=trigger_service.logger.name):
        svc = await _start_with(monkeypatch, defs)
    try:
        assert set(svc._tasks) == {"good-1", "good-2"}
        assert all(not t.done() for t in svc._tasks.values())
        assert svc.invalid_schedules() == {
            "bad-six-field": "schedule.invalid_cron",
            "bad-range": "schedule.invalid_cron",
        }
        text = caplog.text
        assert "bad-six-field" in text and "bad-range" in text and "schedule.invalid_cron" in text
        assert "good-1" not in text.replace("Spawned", "")
    finally:
        await svc.stop()


@pytest.mark.asyncio
async def test_the_cron_loop_reports_and_exits_on_an_invalid_expression_without_raising(caplog):
    svc = TriggerService()
    with caplog.at_level(logging.WARNING, logger=trigger_service.logger.name):
        await asyncio.wait_for(svc._cron_loop(_cron_def("late-bad", "* * * * * *")), timeout=5)
    assert svc.invalid_schedules() == {"late-bad": "schedule.invalid_cron"}
    assert "late-bad" in caplog.text and "schedule.invalid_cron" in caplog.text


def test_list_serialisation_surfaces_the_schedule_error():
    svc = TriggerService()
    svc._invalid_schedules["bad"] = "schedule.invalid_cron"
    by_id = {
        t["id"]: t for t in svc.serialise_triggers([_cron_def("bad", "* * * * * *"), _cron_def("ok", "* * * * *")])
    }
    assert by_id["bad"]["schedule_error"] == "schedule.invalid_cron"
    assert "schedule_error" not in by_id["ok"]


@pytest.mark.asyncio
async def test_a_value_error_from_the_workflow_launch_is_not_a_schedule_error(monkeypatch):
    """Only the cron computation may flag a trigger; a launch failure keeps the loop alive."""
    svc = TriggerService()
    tdef = _cron_def("launch-fails", "*/5 * * * *")
    calls = {"n": 0}

    async def _load(_id):
        return tdef

    async def _launch(_tdef, _payload):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("workflow rejected the payload")
        raise asyncio.CancelledError

    async def _no_sleep(_delay):
        return None

    monkeypatch.setattr(svc, "_load_trigger", _load)
    monkeypatch.setattr(svc, "_launch_workflow", _launch)
    monkeypatch.setattr(trigger_service.asyncio, "sleep", _no_sleep)
    await asyncio.wait_for(svc._cron_loop(tdef), timeout=5)
    assert calls["n"] == 2  # survived the ValueError and fired again
    assert svc.invalid_schedules() == {}
