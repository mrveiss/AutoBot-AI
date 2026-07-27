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


class TestShutdown:
    def test_shutdown_awaits_stop(self):
        """stop() cancels every per-job task start() spawned, so none survive."""
        from pathlib import Path

        src = (Path(__file__).resolve().parent / "lifespan.py").read_text(encoding="utf-8")
        assert "await app.state.mesh_brain_scheduler.stop()" in src

    def test_shutdown_stop_is_independently_guarded(self):
        """A failing stop() must not abort the rest of teardown.

        The whole shutdown block lives inside ONE broad `except Exception`, so an
        unguarded raise here would jump to that handler and skip every remaining
        shutdown step. Startup is already non-fatal; shutdown must match.
        """
        from pathlib import Path

        src = (Path(__file__).resolve().parent / "lifespan.py").read_text(encoding="utf-8")
        block = src[src.index("Stop MeshBrainScheduler") :][:900]
        assert "try:" in block
        assert "MeshBrainScheduler stop failed (non-fatal)" in block
