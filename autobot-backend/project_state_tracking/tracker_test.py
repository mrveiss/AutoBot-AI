# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the PhaseValidator absent-optional-dependency guard (#12458).

``ProjectStateTracker.__init__`` used to call ``PhaseValidator(project_root)``
unguarded. On any backend deployment where ``autobot-infrastructure`` is not
on ``PYTHONPATH`` (every autobot-backend deploy, per #12458), ``PhaseValidator``
is a ``MissingDep`` sentinel and calling it raises ``ImportError`` — which
propagated out of ``__init__`` and made the ``llm_awareness`` health probe
permanently ``down`` (``get_llm_self_awareness -> get_state_tracker ->
ProjectStateTracker()``).

These tests isolate the guard from the tracker's heavy collaborators
(Redis, SQLite, background asyncio task) via monkeypatching, matching the
already-tested guard pattern in ``PhaseProgressionManager.__init__`` (#10466).
"""

from unittest.mock import MagicMock

import pytest

import project_state_tracking.tracker as tracker_module
from autobot_shared.missing_dep import MissingDep


def _patch_heavy_collaborators(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize every non-validator side effect of ``ProjectStateTracker.__init__``."""
    monkeypatch.setattr(tracker_module, "get_progression_manager", lambda: MagicMock())
    monkeypatch.setattr(tracker_module, "ProjectStateManager", MagicMock)
    monkeypatch.setattr(tracker_module, "get_redis_client", lambda: MagicMock())
    monkeypatch.setattr(tracker_module, "get_error_boundary_manager", lambda: None)
    monkeypatch.setattr(tracker_module, "init_database", lambda *_a, **_k: None)
    monkeypatch.setattr(tracker_module.ProjectStateTracker, "_define_milestones", lambda self: None)
    monkeypatch.setattr(tracker_module.ProjectStateTracker, "_load_state", lambda self: None)
    monkeypatch.setattr(tracker_module.ProjectStateTracker, "_start_background_tracking", lambda self: None)


class TestPhaseValidatorGuard:
    """Issue #12458: absent optional PhaseValidator must not raise."""

    def test_missing_phase_validator_yields_none_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MissingDep sentinel (the real production state) -> validator is None, no raise."""
        _patch_heavy_collaborators(monkeypatch)
        sentinel = MissingDep("PhaseValidator", ImportError("No module named 'scripts.phase_validation_system'"))
        monkeypatch.setattr(tracker_module, "PhaseValidator", sentinel)

        tracker = tracker_module.ProjectStateTracker(db_path="unused.db")

        assert tracker.validator is None

    def test_available_phase_validator_is_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When PhaseValidator IS importable (infra repo on path), it is still wired up."""
        _patch_heavy_collaborators(monkeypatch)
        fake_validator_instance = MagicMock()
        fake_validator_cls = MagicMock(return_value=fake_validator_instance)
        monkeypatch.setattr(tracker_module, "PhaseValidator", fake_validator_cls)

        tracker = tracker_module.ProjectStateTracker(db_path="unused.db")

        assert tracker.validator is fake_validator_instance

    @pytest.mark.asyncio
    async def test_capture_state_snapshot_degrades_gracefully_without_validator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing validator must not blow up capture_state_snapshot either."""
        _patch_heavy_collaborators(monkeypatch)
        sentinel = MissingDep("PhaseValidator", ImportError("No module named 'scripts.phase_validation_system'"))
        monkeypatch.setattr(tracker_module, "PhaseValidator", sentinel)

        tracker = tracker_module.ProjectStateTracker(db_path="unused.db")
        assert tracker.validator is None

        # progression_manager is a MagicMock — give it real dict-shaped returns
        # so the snapshot-building helpers (which index into the result) work.
        tracker.progression_manager.get_current_system_capabilities.return_value = {
            "active_capabilities": [],
            "system_maturity": 0,
        }
        tracker.progression_manager.config = {}

        async def _noop(*_a, **_k):
            return None

        monkeypatch.setattr(tracker, "_save_snapshot", _noop)
        monkeypatch.setattr(tracker, "_check_milestones", _noop)

        snapshot = await tracker.capture_state_snapshot()

        assert snapshot.phase_states == {}
