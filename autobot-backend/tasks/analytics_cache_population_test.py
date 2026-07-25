# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the daily analytics /cached population job (Issue #12365).

Verifies: each module's Celery task is dispatched (reusing the existing
analyze + store-write task, not a reimplementation), dispatches are staggered,
anti-pattern is dispatched without a redis_prefix pointer (it self-caches
inside analyze()), one module's dispatch failure doesn't abort the others,
and the beat schedule registers analytics.populate_all_caches at the
configured hour.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tasks.analytics_cache_population import _build_modules, _dispatch, _populate_all


class TestBuildModules:
    def test_returns_all_six_modules_in_dispatch_order(self):
        modules = _build_modules("/fake/project/root")
        names = [m[0] for m in modules]
        assert names == [
            "dependencies",
            "duplicates",
            "import_tree",
            "bug_prediction",
            "security_score",
            "anti_pattern",
        ]

    def test_anti_pattern_has_no_redis_prefix(self):
        """AntiPatternDetector.analyze() writes its own cache directly --
        no latest_task_id pointer needed, unlike the other 5 modules."""
        modules = _build_modules("/fake/project/root")
        by_name = {m[0]: m for m in modules}
        assert by_name["anti_pattern"][3] is None

    def test_other_five_modules_have_distinct_redis_prefixes(self):
        modules = _build_modules("/fake/project/root")
        by_name = {m[0]: m for m in modules}
        prefixes = {
            by_name[name][3]
            for name in ("dependencies", "duplicates", "import_tree", "bug_prediction", "security_score")
        }
        assert None not in prefixes
        assert len(prefixes) == 5  # all distinct -- no cross-module cache collisions

    def test_path_taking_tasks_receive_project_root(self):
        """bug_prediction, security_score, and anti_pattern take an explicit
        path argument (their Celery tasks have no source/cwd-relative
        default); dependencies/duplicates/import_tree self-resolve internally."""
        modules = _build_modules("/fake/project/root")
        by_name = {m[0]: m for m in modules}
        assert by_name["bug_prediction"][2][0] == "/fake/project/root"
        assert by_name["security_score"][2] == ("/fake/project/root",)
        assert by_name["anti_pattern"][2] == ("/fake/project/root",)
        assert by_name["dependencies"][2] == ()
        assert by_name["duplicates"][2] == ()
        assert by_name["import_tree"][2] == ()


class TestDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_stores_latest_task_id_when_prefix_given(self):
        mock_result = MagicMock(id="task-abc")
        mock_task = MagicMock()
        mock_task.apply_async.return_value = mock_result

        with patch(
            "tasks.analytics_cache_population.store_latest_task_id",
            AsyncMock(),
        ) as mock_store:
            task_id = await _dispatch(mock_task, (), "some_prefix:", countdown=120)

        assert task_id == "task-abc"
        mock_task.apply_async.assert_called_once_with(args=(), countdown=120)
        mock_store.assert_awaited_once_with("some_prefix:", "task-abc")

    @pytest.mark.asyncio
    async def test_dispatch_skips_store_when_no_prefix(self):
        mock_result = MagicMock(id="task-anti")
        mock_task = MagicMock()
        mock_task.apply_async.return_value = mock_result

        with patch(
            "tasks.analytics_cache_population.store_latest_task_id",
            AsyncMock(),
        ) as mock_store:
            task_id = await _dispatch(mock_task, ("/root",), None, countdown=0)

        assert task_id == "task-anti"
        mock_store.assert_not_awaited()


class TestPopulateAll:
    def _make_mock_module(self, name: str, prefix: str | None):
        task = MagicMock()
        task.apply_async.return_value = MagicMock(id=f"{name}-task-id")
        return name, task, (), prefix

    @pytest.mark.asyncio
    async def test_dispatches_all_modules_staggered(self):
        modules = [
            self._make_mock_module("dependencies", "dep_task:"),
            self._make_mock_module("duplicates", "dup_task:"),
            self._make_mock_module("anti_pattern", None),
        ]

        with (
            patch("tasks.analytics_cache_population._build_modules", return_value=modules),
            patch("tasks.analytics_cache_population.store_latest_task_id", AsyncMock()),
            patch("tasks.analytics_cache_population._STAGGER_SECONDS", 100),
        ):
            results = await _populate_all("/fake/root")

        assert results["dependencies"] == {"status": "dispatched", "task_id": "dependencies-task-id", "countdown": 0}
        assert results["duplicates"] == {"status": "dispatched", "task_id": "duplicates-task-id", "countdown": 100}
        assert results["anti_pattern"] == {"status": "dispatched", "task_id": "anti_pattern-task-id", "countdown": 200}

    @pytest.mark.asyncio
    async def test_one_module_failure_does_not_abort_others(self):
        """A dispatch failure for one module must not prevent the rest from
        being scheduled (Issue #12365 requirement)."""
        failing_task = MagicMock()
        failing_task.apply_async.side_effect = RuntimeError("broker unavailable")
        ok_task = MagicMock()
        ok_task.apply_async.return_value = MagicMock(id="ok-task-id")

        modules = [
            ("dependencies", failing_task, (), "dep_task:"),
            ("duplicates", ok_task, (), "dup_task:"),
        ]

        with (
            patch("tasks.analytics_cache_population._build_modules", return_value=modules),
            patch("tasks.analytics_cache_population.store_latest_task_id", AsyncMock()),
        ):
            results = await _populate_all("/fake/root")

        assert results["dependencies"]["status"] == "failed"
        assert "broker unavailable" in results["dependencies"]["error"]
        # The second module still dispatched despite the first one failing.
        assert results["duplicates"]["status"] == "dispatched"
        assert results["duplicates"]["task_id"] == "ok-task-id"

    @pytest.mark.asyncio
    async def test_all_six_real_modules_dispatch(self):
        """Integration-style check against the real _build_modules wiring:
        every one of the 6 modules dispatches without raising, using mocked
        Celery apply_async so no broker is needed."""
        with (
            patch("tasks.analytics_tasks.run_dependency_analysis") as dep,
            patch("tasks.analytics_tasks.run_duplicate_analysis") as dup,
            patch("tasks.analytics_tasks.run_import_tree_analysis") as imp,
            patch("tasks.analytics_tasks.run_bug_prediction_analysis") as bug,
            patch("tasks.analytics_tasks.run_security_analysis") as sec,
            patch("tasks.analytics_tasks.run_anti_pattern_analysis") as anti,
            patch("tasks.analytics_cache_population.store_latest_task_id", AsyncMock()),
        ):
            for i, mock_task in enumerate([dep, dup, imp, bug, sec, anti]):
                mock_task.apply_async.return_value = MagicMock(id=f"id-{i}")

            results = await _populate_all("/fake/root")

        assert len(results) == 6
        assert all(r["status"] == "dispatched" for r in results.values())


class TestBeatScheduleRegistration:
    """celery_app.py is heavy and pytest-stubbed (#7766: the stub Celery app
    has no beat_schedule), so read source text the same way
    celery_beat_registration_test.py does, rather than importing the real
    module. GH#12318's generic ``test_every_beat_scheduled_task_is_registered``
    already asserts analytics.populate_all_caches resolves in the task
    registry; these tests check this entry's specifics: it exists, uses the
    configurable (not hardcoded) schedule, and is dispatched at an off-peak hour.
    """

    def _celery_app_source(self) -> str:
        from pathlib import Path

        return (Path(__file__).resolve().parents[1] / "celery_app.py").read_text(encoding="utf-8")

    def test_populate_all_caches_registered_in_beat_schedule(self):
        src = self._celery_app_source()
        assert '"task": "analytics.populate_all_caches"' in src

    def test_schedule_is_configurable_not_hardcoded(self):
        """The entry must read ssot_config.analytics_cache_population_schedule
        (env-var-backed), not a bare crontab(hour=N) literal -- per project
        convention (never hard-code a schedule/TTL; module-level constant
        sourced from config/env var)."""
        src = self._celery_app_source()
        assert "crontab_from_string(ssot_config.analytics_cache_population_schedule)" in src

    def test_configured_hour_is_off_peak(self):
        """Sanity-check the default schedule lands in the existing off-peak
        maintenance window (00:00-06:00 UTC), not business hours."""
        from utils.celery_schedules import crontab_from_string

        from autobot_shared.ssot_config import AutoBotConfig

        default_schedule = AutoBotConfig.model_fields["analytics_cache_population_schedule"].default
        parsed = crontab_from_string(default_schedule)
        (hour,) = parsed.hour
        assert 0 <= hour <= 6, f"expected an off-peak UTC hour (0-6), got {hour}"

    def test_anti_pattern_and_population_tasks_registered(self):
        """GH#12318: both new tasks (the per-module wrapper and the
        orchestrator) must be reachable via the same registration surface
        celery_app.py loads at startup, or beat/worker silently drops them."""
        import importlib
        import sys

        for module in ("tasks", "workers", "llc.scheduler", "services.pricing_refresh"):
            importlib.import_module(module)
        celery_app_mod = sys.modules.get("celery_app")
        assert celery_app_mod is not None, "celery_app stub missing — check conftest.py"
        registered = set(celery_app_mod.celery_app.tasks)
        assert "analytics.run_anti_pattern_analysis" in registered
        assert "analytics.populate_all_caches" in registered
