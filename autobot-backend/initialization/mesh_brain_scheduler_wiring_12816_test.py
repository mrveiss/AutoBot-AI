# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""MeshBrainScheduler lifespan wiring (#12816).

The scheduler was registered in the canonical scheduler registry, fully
described, and never started — its own registry entry admitted "currently
inert", and `grep mesh_brain lifespan.py` found only individual components
(EdgeLearner, PersonalizedPageRank, CommunityClusterer), never the scheduler
that drives them.

It is now wired, but DEFAULT-OFF. That is deliberate: of its five jobs
`mesh_pruner` DELETES data on a 7-day cadence and node_promoter/edge_discoverer
mutate node and edge state, so enabling it is a data-retention decision, not a
wiring change. These tests pin both halves — the wiring exists, and it stays off
unless explicitly enabled.

Mirrors the issue's own Verification section:
  - startup spawns the scheduler when the flag is on and does not when off
  - shutdown cancels every task start() launched
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def app():
    return SimpleNamespace(state=SimpleNamespace())


async def _run_init(app, enabled: bool, scheduler: MagicMock | None = None):
    from initialization.lifespan import _init_mesh_brain_scheduler

    scheduler = scheduler or MagicMock(start=AsyncMock(), stop=AsyncMock())
    cfg = SimpleNamespace(misc=SimpleNamespace(mesh_brain_scheduler_enabled=enabled))
    with patch("autobot_shared.ssot_config.config", cfg):
        with patch.dict(
            "sys.modules",
            {"services.mesh_brain.scheduler": MagicMock(MeshBrainScheduler=lambda: scheduler)},
        ):
            await _init_mesh_brain_scheduler(app)
    return scheduler


class TestFlagGating:
    @pytest.mark.asyncio
    async def test_disabled_by_default_does_not_start(self, app):
        """The whole point: fixing the wiring must not enable data-deleting jobs."""
        scheduler = await _run_init(app, enabled=False)
        scheduler.start.assert_not_awaited()
        assert app.state.mesh_brain_scheduler is None

    @pytest.mark.asyncio
    async def test_enabled_starts_the_scheduler(self, app):
        scheduler = await _run_init(app, enabled=True)
        scheduler.start.assert_awaited_once()
        assert app.state.mesh_brain_scheduler is scheduler

    def test_config_flag_defaults_to_off(self):
        """Default-off must hold in the shipped config, not just in this test."""
        from autobot_shared.ssot_config import MiscConfig

        assert MiscConfig().mesh_brain_scheduler_enabled is False

    @pytest.mark.asyncio
    async def test_startup_failure_is_non_fatal(self, app):
        """A broken scheduler must not take the whole backend down with it."""
        from initialization.lifespan import _init_mesh_brain_scheduler

        cfg = SimpleNamespace(misc=SimpleNamespace(mesh_brain_scheduler_enabled=True))
        boom = MagicMock(start=AsyncMock(side_effect=RuntimeError("boom")), stop=AsyncMock())
        with patch("autobot_shared.ssot_config.config", cfg):
            with patch.dict(
                "sys.modules",
                {"services.mesh_brain.scheduler": MagicMock(MeshBrainScheduler=lambda: boom)},
            ):
                await _init_mesh_brain_scheduler(app)  # must not raise
        assert app.state.mesh_brain_scheduler is None


class TestRegistryTruthfulness:
    """The registry must not keep claiming the scheduler is unwired."""

    def test_entry_now_has_a_startup_marker(self):
        from services.scheduler_registry import REGISTRY

        job = next(j for j in REGISTRY if j.name == "MeshBrainScheduler")
        assert job.startup_marker == "initialization/lifespan.py::_init_mesh_brain_scheduler"

    def test_startup_marker_points_at_a_symbol_that_exists(self):
        """A marker naming a function that isn't there would be worse than none."""
        from pathlib import Path

        src = (Path(__file__).resolve().parent / "lifespan.py").read_text(encoding="utf-8")
        assert "async def _init_mesh_brain_scheduler" in src
        assert "await _init_mesh_brain_scheduler(app)" in src

    def test_inert_reason_still_records_the_open_retention_decision(self):
        """The wiring gap is closed; the mesh_pruner retention call is NOT."""
        from services.scheduler_registry import REGISTRY

        job = next(j for j in REGISTRY if j.name == "MeshBrainScheduler")
        assert "data-retention decision" in job.inert_reason


@contextlib.contextmanager
def _stubbed_cleanup_legs(redis_close=None):
    """Stub cleanup_services()'s unconditional real-I/O legs.

    Mirrors the helper in lifespan_test.py: these legs are unrelated to the
    scheduler under test and can reach real network timeouts depending on the
    environment.
    """
    handoff_svc = MagicMock(shutdown=AsyncMock())
    connector_scheduler = MagicMock(stop_all=AsyncMock())

    with (
        patch("initialization.lifespan.shutdown_slm_client", new=AsyncMock()),
        patch("initialization.lifespan.shutdown_tracing", new=AsyncMock()),
        patch("services.documentation_watcher.stop_documentation_watcher", new=AsyncMock()),
        patch("services.kb_folder_watcher.stop_kb_folder_watcher", new=AsyncMock()),
        patch("llc.api.work_items._get_handoff_service", return_value=handoff_svc),
        patch("workflow_scheduler.stop_autonomous_loop", new=AsyncMock()),
        patch("api.analytics.analytics_controller.metrics_collector.stop_collection", new=AsyncMock()),
        patch("knowledge.connectors.scheduler.get_connector_scheduler", return_value=connector_scheduler),
        patch("autobot_shared.redis_client.close_all_redis_connections", new=(redis_close or AsyncMock())),
    ):
        yield


class TestShutdown:
    """The scheduler is stopped, and its failure does not abort the teardown.

    Both of these asserted on the SOURCE TEXT of lifespan.py — one greping for
    an await expression, the other for a log message. #13585 replaced that log
    call with a shared failure recorder, and the second test went red without
    anything about the property it names having changed. A test that breaks on a
    rename while the property survives was not testing the property; these drive
    cleanup_services and assert on what it does.
    """

    @pytest.mark.asyncio
    async def test_shutdown_stops_the_scheduler(self):
        """stop() cancels every per-job task start() spawned, so none survive."""
        from initialization.lifespan import cleanup_services

        scheduler = MagicMock(stop=AsyncMock())
        app = SimpleNamespace(state=SimpleNamespace(mesh_brain_scheduler=scheduler))

        with _stubbed_cleanup_legs():
            failed = await cleanup_services(app)

        scheduler.stop.assert_awaited_once()
        assert "MeshBrainScheduler stop" not in failed

    @pytest.mark.asyncio
    async def test_a_failing_stop_does_not_abort_the_rest_of_teardown(self):
        """A raise here must cost one step, not every step below it.

        The teardown sits inside one broad `except Exception`; an unguarded raise
        would jump straight to it and skip everything after. Asserting a LATER
        step still ran is the whole point — asserting only that nothing
        propagated would pass on the aborted version too.
        """
        from initialization.lifespan import cleanup_services

        ran_later: list[str] = []

        async def _boom() -> None:
            raise RuntimeError("scheduler stop exploded")

        async def _redis_close() -> None:
            ran_later.append("redis_close")

        scheduler = MagicMock(stop=AsyncMock(side_effect=_boom))
        app = SimpleNamespace(state=SimpleNamespace(mesh_brain_scheduler=scheduler))

        with _stubbed_cleanup_legs(redis_close=_redis_close):
            failed = await cleanup_services(app)

        assert "MeshBrainScheduler stop" in failed, f"the failure was not recorded: {failed}"
        assert ran_later == ["redis_close"], "a step after the failure did not run"
