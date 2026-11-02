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
async def test_a_canned_all_unscored_report_counts_none_as_complete_or_failing() -> None:
    summary = (await _metrics_for([_phase("a", None), _phase("b", None)]))["metrics"]["phase_summary"]
    assert (summary["completed_phases"], summary["phases_not_started"], summary["phases_unscored"]) == (0, 0, 2)


def _real_generator(scores: list[float | None]):
    """The real generator class on real-shaped validator results; only gathering them is stubbed."""
    generator_class = _load_generator_class()
    gen = generator_class.__new__(generator_class)
    results = {
        # phase_score.py leaves `completion_percentage` ABSENT on an unscored phase, not None (#17089)
        "phases": {
            f"phase_{i}": {
                "complete": False,
                "status": "incomplete",
                **({} if score is None else {"completion_percentage": score}),
            }
            for i, score in enumerate(scores)
        },
        "overall_assessment": {"structural_presence_score": 50.0, "development_stage": "integration"},
    }
    gen._gather_validation_data = AsyncMock(
        return_value=(results, gen._get_default_state_summary(), gen._get_default_progression_status())
    )
    return gen


@pytest.mark.asyncio
async def test_the_real_generator_reports_no_figure_when_every_phase_is_unscored() -> None:
    report = await _real_generator([None, None]).generate_real_time_report()
    stats = report["metrics"]["completion_statistics"]
    assert (stats["average_completion"], stats["min_completion"], stats["max_completion"]) == (None, None, None)
    assert (stats["phases_above_50"], stats["phases_above_90"]) == (0, 0)


@pytest.mark.asyncio
async def test_the_real_generator_still_averages_the_scored_phases() -> None:
    report = await _real_generator([100.0, None, 50.0]).generate_real_time_report()
    stats = report["metrics"]["completion_statistics"]
    assert (stats["average_completion"], stats["min_completion"], stats["max_completion"]) == (75.0, 50.0, 100.0)


@pytest.mark.asyncio
async def test_the_metrics_route_answers_on_the_real_generator_when_every_phase_is_unscored() -> None:
    with patch.object(vd, "get_dashboard_generator", return_value=_real_generator([None, None])):
        result = await vd.get_dashboard_metrics()
    assert result["status"] == "success"
    assert result["metrics"]["phase_summary"]["phases_unscored"] == 2


@pytest.mark.asyncio
async def test_the_html_dashboard_says_its_empty_chart_has_no_history() -> None:
    gen = _real_generator([None, 50.0])
    gen.refresh_interval = 30  # __init__ is skipped: it builds the validator and state tracker
    html = gen._create_dashboard_html(await gen.generate_real_time_report())
    assert "No stored trend history is available yet." in html


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
