# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for scheduler operator toggles — Issue #12820

The property under test throughout: the registry default is what applies when nobody
has expressed a preference, including when Redis cannot be reached.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import scheduler_toggles
from services.scheduler_registry import REGISTRY


def _flags(override=None, set_ok=True, clear_ok=True):
    """A FeatureFlags stand-in whose stored override is ``override`` (None = unset)."""
    flags = MagicMock()
    flags.get_feature = AsyncMock(side_effect=lambda _name, default=False: default if override is None else override)
    flags.get_feature_override = AsyncMock(return_value=override)
    flags.set_feature = AsyncMock(return_value=set_ok)
    flags.clear_feature = AsyncMock(return_value=clear_ok)
    return flags


def _patch_flags(flags):
    return patch("services.feature_flags.get_feature_flags", AsyncMock(return_value=flags))


class TestDefaults:
    """With no override, the registry default decides."""

    @pytest.mark.asyncio
    async def test_unset_resolves_to_registry_default_true(self):
        with _patch_flags(_flags(override=None)):
            # BackupScheduler starts unconditionally today -> default True
            assert await scheduler_toggles.is_scheduler_enabled("BackupScheduler") is True

    @pytest.mark.asyncio
    async def test_unset_resolves_to_registry_default_false(self):
        with _patch_flags(_flags(override=None)):
            # Distillation costs LLM tokens hourly -> ships off
            assert await scheduler_toggles.is_scheduler_enabled("SkillDistillationScheduler") is False

    @pytest.mark.asyncio
    async def test_inert_job_defaults_off(self):
        with _patch_flags(_flags(override=None)):
            assert await scheduler_toggles.is_scheduler_enabled("MeshBrainScheduler") is False

    @pytest.mark.asyncio
    async def test_every_registry_default_is_reachable(self):
        """Each job resolves to exactly its declared default when unset."""
        with _patch_flags(_flags(override=None)):
            for job in REGISTRY:
                assert await scheduler_toggles.is_scheduler_enabled(job.name) is job.default_enabled, job.name


class TestOverrides:
    """An operator override wins over the default, and clearing reverts."""

    @pytest.mark.asyncio
    async def test_override_enables_a_default_off_job(self):
        with _patch_flags(_flags(override=True)):
            assert await scheduler_toggles.is_scheduler_enabled("SkillDistillationScheduler") is True

    @pytest.mark.asyncio
    async def test_override_disables_a_default_on_job(self):
        with _patch_flags(_flags(override=False)):
            assert await scheduler_toggles.is_scheduler_enabled("BackupScheduler") is False

    @pytest.mark.asyncio
    async def test_set_writes_the_namespaced_flag(self):
        flags = _flags()
        with _patch_flags(flags):
            assert await scheduler_toggles.set_scheduler_enabled("BackupScheduler", False) is True
        flags.set_feature.assert_awaited_once_with("scheduler:BackupScheduler", False)

    @pytest.mark.asyncio
    async def test_clearing_reverts_to_default(self):
        flags = _flags(override=True)
        with _patch_flags(flags):
            assert await scheduler_toggles.clear_scheduler_override("SkillDistillationScheduler") is True
        flags.clear_feature.assert_awaited_once_with("scheduler:SkillDistillationScheduler")


class TestFailureModes:
    """A toggle lookup must never be the reason a scheduler misbehaves."""

    @pytest.mark.asyncio
    async def test_redis_failure_falls_back_to_default_not_off(self):
        """A cache blip must not silently stop every background job."""
        flags = MagicMock()
        flags.get_feature = AsyncMock(side_effect=RuntimeError("redis down"))
        with _patch_flags(flags):
            assert await scheduler_toggles.is_scheduler_enabled("BackupScheduler") is True

    @pytest.mark.asyncio
    async def test_redis_failure_does_not_silently_enable_an_off_job(self):
        flags = MagicMock()
        flags.get_feature = AsyncMock(side_effect=RuntimeError("redis down"))
        with _patch_flags(flags):
            assert await scheduler_toggles.is_scheduler_enabled("SkillDistillationScheduler") is False

    @pytest.mark.asyncio
    async def test_unregistered_scheduler_is_disabled(self):
        with _patch_flags(_flags(override=True)):
            assert await scheduler_toggles.is_scheduler_enabled("NoSuchScheduler") is False

    @pytest.mark.asyncio
    async def test_unregistered_scheduler_cannot_be_toggled(self):
        flags = _flags()
        with _patch_flags(flags):
            assert await scheduler_toggles.set_scheduler_enabled("NoSuchScheduler", True) is False
            assert await scheduler_toggles.clear_scheduler_override("NoSuchScheduler") is False
        flags.set_feature.assert_not_awaited()
        flags.clear_feature.assert_not_awaited()


class TestListing:
    """The listing reports effective state and where it came from."""

    @pytest.mark.asyncio
    async def test_listing_covers_every_registered_job(self):
        with _patch_flags(_flags(override=None)):
            states = await scheduler_toggles.list_scheduler_states()
        assert len(states) == len(REGISTRY)
        assert {s["name"] for s in states} == {j.name for j in REGISTRY}

    @pytest.mark.asyncio
    async def test_listing_marks_no_override_and_shows_default(self):
        with _patch_flags(_flags(override=None)):
            states = await scheduler_toggles.list_scheduler_states()
        distil = next(s for s in states if s["name"] == "SkillDistillationScheduler")
        assert distil["override_active"] is False
        assert distil["enabled"] is False
        assert distil["default_enabled"] is False

    @pytest.mark.asyncio
    async def test_listing_marks_an_active_override(self):
        with _patch_flags(_flags(override=True)):
            states = await scheduler_toggles.list_scheduler_states()
        distil = next(s for s in states if s["name"] == "SkillDistillationScheduler")
        assert distil["override_active"] is True
        assert distil["enabled"] is True
        # The default is still reported, so the UI can offer "revert to default".
        assert distil["default_enabled"] is False
