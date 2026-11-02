# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20523: /validation-dashboard/metrics on an unscored phase, and trends that are not invented.

The generator publishes ``completion_percentage: None`` for a phase that defers to dedicated gates
(#17089). ``None >= 95.0`` raised ``TypeError`` and the route answered 500. An unscored phase is
neither complete nor failing: it is counted on its own.
"""

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import validation_dashboard as vd


def _phase(name: str, pct: float | None) -> dict:
    return {"name": name, "completion_percentage": pct, "scored": pct is not None}


def _generator(phases: list[dict]) -> MagicMock:
    gen = MagicMock()
    gen.generate_real_time_report = AsyncMock(
        return_value={
            "system_overview": {},
            "metrics": {},
            "alerts": [],
            "recommendations": [],
            "phase_details": phases,
        }
    )
    return gen


def _load_generator_class() -> type:
    """The generator lives in a script directory that is not a package (#18288); load it by path."""
    path = (
        Path(__file__).resolve().parents[3] / "autobot-infrastructure/shared/scripts/validation_dashboard_generator.py"
    )
    spec = importlib.util.spec_from_file_location("validation_dashboard_generator_20523", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ValidationDashboardGenerator


async def _metrics_for(phases: list[dict]) -> dict:
    with patch.object(vd, "get_dashboard_generator", return_value=_generator(phases)):
        return await vd.get_dashboard_metrics()


@pytest.mark.asyncio
async def test_an_unscored_phase_does_not_break_the_route() -> None:
    result = await _metrics_for([_phase("a", 100.0), _phase("b", None)])
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_an_unscored_phase_is_neither_complete_nor_failing() -> None:
    summary = (await _metrics_for([_phase("a", 100.0), _phase("b", 70.0), _phase("c", 10.0), _phase("d", None)]))[
        "metrics"
    ]["phase_summary"]
    assert summary == {
        "total_phases": 4,
        "completed_phases": 1,
        "phases_in_progress": 1,
        "phases_not_started": 1,
        "phases_unscored": 1,
    }


@pytest.mark.asyncio
async def test_all_phases_unscored_counts_none_as_complete_or_failing() -> None:
    summary = (await _metrics_for([_phase("a", None), _phase("b", None)]))["metrics"]["phase_summary"]
    assert (summary["completed_phases"], summary["phases_not_started"], summary["phases_unscored"]) == (0, 0, 2)


@pytest.mark.asyncio
async def test_trends_say_they_are_unavailable_instead_of_inventing_a_series() -> None:
    generator_class = _load_generator_class()
    gen = generator_class.__new__(generator_class)
    trends = await gen._generate_trend_data()
    assert trends == {"maturity_trend": [], "phase_completion_trend": [], "capability_growth": []}


@pytest.mark.asyncio
async def test_the_trends_route_flags_that_there_is_no_history() -> None:
    gen = MagicMock()
    gen._generate_trend_data = AsyncMock(return_value={"maturity_trend": []})
    with patch.object(vd, "get_dashboard_generator", return_value=gen):
        result = await vd.get_trend_data()
    assert result["available"] is False
    assert result["trends"] == {"maturity_trend": []}
