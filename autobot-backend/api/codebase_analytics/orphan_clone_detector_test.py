# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the code-source clone orphan detector (#17036, #17039)."""

import time

import pytest

from api.codebase_analytics import orphan_clone_detector as detector
from api.codebase_analytics.source_storage import RegistryUnavailable

pytestmark = pytest.mark.asyncio


def _age_dir(path, hours_old: float) -> None:
    stamp = time.time() - hours_old * 3600
    import os

    os.utime(path, (stamp, stamp))


def _known_ids(*ids):
    async def _registered(_ids=frozenset(ids)):
        return set(_ids)

    return _registered


@pytest.fixture(autouse=True)
def _registry_reachable_by_default(monkeypatch):
    """Every test but TestFailsClosedOnARegistryOutage assumes a reachable,
    empty-by-default registry -- override with `_known_ids(...)` per test."""
    monkeypatch.setattr(detector, "registered_source_ids", _known_ids())


class TestListCandidates:
    async def test_a_directory_with_no_source_record_past_the_grace_period_is_listed(self, monkeypatch, tmp_path):
        monkeypatch.setattr(detector, "CODE_SOURCES_BASE", tmp_path)
        orphan_dir = tmp_path / "orphan-id"
        orphan_dir.mkdir()
        (orphan_dir / "file.txt").write_bytes(b"x" * 100)
        _age_dir(orphan_dir, hours_old=48)
        monkeypatch.setenv("AUTOBOT_ORPHAN_GRACE_HOURS", "24")

        candidates = await detector._list_candidates()

        assert len(candidates) == 1
        assert candidates[0].id == "orphan-id"
        assert candidates[0].location == "code-sources/orphan-id"
        assert candidates[0].size_bytes == 100
        assert str(tmp_path) not in candidates[0].location, "no host filesystem path may reach the API output"

    async def test_a_directory_with_a_matching_record_is_never_listed(self, monkeypatch, tmp_path):
        monkeypatch.setattr(detector, "CODE_SOURCES_BASE", tmp_path)
        known_dir = tmp_path / "known-id"
        known_dir.mkdir()
        _age_dir(known_dir, hours_old=48)
        monkeypatch.setattr(detector, "registered_source_ids", _known_ids("known-id"))

        candidates = await detector._list_candidates()

        assert candidates == []

    async def test_a_directory_younger_than_the_grace_period_is_excluded(self, monkeypatch, tmp_path):
        monkeypatch.setattr(detector, "CODE_SOURCES_BASE", tmp_path)
        fresh_dir = tmp_path / "fresh-id"
        fresh_dir.mkdir()
        _age_dir(fresh_dir, hours_old=1)
        monkeypatch.setenv("AUTOBOT_ORPHAN_GRACE_HOURS", "24")

        candidates = await detector._list_candidates()

        assert candidates == [], "a clone still being written must never be offered for cleanup"


class TestFailsClosedOnARegistryOutage:
    """#17039 review: an unreachable registry must never make every clone look orphaned."""

    async def test_list_candidates_returns_nothing_when_the_registry_is_unreachable(self, monkeypatch, tmp_path):
        monkeypatch.setattr(detector, "CODE_SOURCES_BASE", tmp_path)
        orphan_dir = tmp_path / "looks-orphaned-but-registry-is-down"
        orphan_dir.mkdir()
        _age_dir(orphan_dir, hours_old=48)

        async def _unavailable():
            raise RegistryUnavailable("Redis is down")

        monkeypatch.setattr(detector, "registered_source_ids", _unavailable)

        with pytest.raises(RegistryUnavailable):
            await detector._list_candidates()

    async def test_delete_refuses_when_the_registry_is_unreachable(self, monkeypatch, tmp_path):
        monkeypatch.setattr(detector, "CODE_SOURCES_BASE", tmp_path)
        clone_dir = tmp_path / "maybe-still-referenced"
        clone_dir.mkdir()
        _age_dir(clone_dir, hours_old=48)

        async def _unavailable():
            raise RegistryUnavailable("Redis is down")

        monkeypatch.setattr(detector, "registered_source_ids", _unavailable)

        result = await detector._delete("maybe-still-referenced")

        assert result.deleted is False
        assert clone_dir.exists()


class TestDelete:
    async def test_deletes_a_genuine_orphan_past_the_grace_period(self, monkeypatch, tmp_path):
        monkeypatch.setattr(detector, "CODE_SOURCES_BASE", tmp_path)
        orphan_dir = tmp_path / "orphan-id"
        orphan_dir.mkdir()
        _age_dir(orphan_dir, hours_old=48)
        monkeypatch.setenv("AUTOBOT_ORPHAN_GRACE_HOURS", "24")

        result = await detector._delete("orphan-id")

        assert result.deleted is True
        assert not orphan_dir.exists()

    async def test_refuses_when_a_record_now_references_the_directory(self, monkeypatch, tmp_path):
        """#17039 AC: a directory whose record reappears is refused, re-checked at delete time."""
        monkeypatch.setattr(detector, "CODE_SOURCES_BASE", tmp_path)
        orphan_dir = tmp_path / "reclaimed-id"
        orphan_dir.mkdir()
        _age_dir(orphan_dir, hours_old=48)
        monkeypatch.setattr(detector, "registered_source_ids", _known_ids("reclaimed-id"))

        result = await detector._delete("reclaimed-id")

        assert result.deleted is False
        assert orphan_dir.exists()

    async def test_refuses_when_no_longer_past_the_grace_period(self, monkeypatch, tmp_path):
        monkeypatch.setattr(detector, "CODE_SOURCES_BASE", tmp_path)
        young_dir = tmp_path / "young-id"
        young_dir.mkdir()
        _age_dir(young_dir, hours_old=1)
        monkeypatch.setenv("AUTOBOT_ORPHAN_GRACE_HOURS", "24")

        result = await detector._delete("young-id")

        assert result.deleted is False
        assert young_dir.exists()

    async def test_a_failed_removal_is_reported_never_swallowed(self, monkeypatch, tmp_path):
        """#17036: never ignore_errors=True."""
        monkeypatch.setattr(detector, "CODE_SOURCES_BASE", tmp_path)
        orphan_dir = tmp_path / "stubborn-id"
        orphan_dir.mkdir()
        _age_dir(orphan_dir, hours_old=48)
        monkeypatch.setenv("AUTOBOT_ORPHAN_GRACE_HOURS", "24")

        def _boom(_path):
            raise OSError("permission denied")

        monkeypatch.setattr(detector.shutil, "rmtree", _boom)

        result = await detector._delete("stubborn-id")

        assert result.deleted is False
        assert "permission denied" in result.reason
        assert orphan_dir.exists()

    @pytest.mark.parametrize("bad_id", ["../escape", "a/b", "..", "."])
    async def test_refuses_a_candidate_id_that_would_escape_the_base(self, bad_id):
        result = await detector._delete(bad_id)

        assert result.deleted is False

    async def test_refuses_a_candidate_that_no_longer_exists_on_disk(self, monkeypatch, tmp_path):
        monkeypatch.setattr(detector, "CODE_SOURCES_BASE", tmp_path)

        result = await detector._delete("never-existed")

        assert result.deleted is False
