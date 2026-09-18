# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the orphan-storage detector framework itself (#17039)."""

import pytest

from services import orphan_storage

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    """Never leak a fake provider into other tests sharing the module registry."""
    monkeypatch.setattr(orphan_storage, "_REGISTRY", {})


def _candidate(provider="fake", cid="1"):
    return orphan_storage.OrphanCandidate(
        provider=provider,
        id=cid,
        location=f"fake/{cid}",
        size_bytes=10,
        modified_at="2026-01-01T00:00:00+00:00",
        reason="test",
    )


class TestListAllCandidates:
    async def test_aggregates_across_every_registered_detector(self):
        async def _list_a():
            return [_candidate("a", "1")]

        async def _list_b():
            return [_candidate("b", "1"), _candidate("b", "2")]

        orphan_storage.register_detector(
            orphan_storage.OrphanDetector(provider="a", list_candidates=_list_a, delete=None)
        )
        orphan_storage.register_detector(
            orphan_storage.OrphanDetector(provider="b", list_candidates=_list_b, delete=None)
        )

        listing = await orphan_storage.list_all_candidates()

        assert {(c.provider, c.id) for c in listing.candidates} == {("a", "1"), ("b", "1"), ("b", "2")}
        assert {s.provider: s.available for s in listing.statuses} == {"a": True, "b": True}

    async def test_one_detectors_failure_does_not_hide_the_others_candidates(self):
        async def _boom():
            raise RuntimeError("detector unavailable")

        async def _list_ok():
            return [_candidate("ok", "1")]

        orphan_storage.register_detector(
            orphan_storage.OrphanDetector(provider="broken", list_candidates=_boom, delete=None)
        )
        orphan_storage.register_detector(
            orphan_storage.OrphanDetector(provider="ok", list_candidates=_list_ok, delete=None)
        )

        listing = await orphan_storage.list_all_candidates()

        assert [c.provider for c in listing.candidates] == ["ok"]

    async def test_a_failed_detector_is_reported_unavailable_not_silently_empty(self):
        """MEASUREMENT_DISCIPLINE: an outage must read as "could not check", never "found nothing"."""

        async def _boom():
            raise RuntimeError("registry unreachable")

        orphan_storage.register_detector(
            orphan_storage.OrphanDetector(provider="broken", list_candidates=_boom, delete=None)
        )

        listing = await orphan_storage.list_all_candidates()

        assert listing.candidates == []
        assert listing.statuses == [
            orphan_storage.ProviderStatus(provider="broken", available=False, error="registry unreachable")
        ]


class TestDeleteCandidate:
    async def test_refuses_an_unregistered_provider(self):
        result = await orphan_storage.delete_candidate("no-such-provider", "1")

        assert result.deleted is False
        assert "no-such-provider" in result.reason

    async def test_delegates_to_the_registered_detectors_own_delete(self):
        calls = []

        async def _delete(candidate_id):
            calls.append(candidate_id)
            return orphan_storage.DeleteResult(deleted=True)

        orphan_storage.register_detector(
            orphan_storage.OrphanDetector(provider="p", list_candidates=None, delete=_delete)
        )

        result = await orphan_storage.delete_candidate("p", "candidate-9")

        assert result.deleted is True
        assert calls == ["candidate-9"]

    async def test_an_unexpected_exception_from_the_detector_is_never_deleted_true(self):
        async def _boom(_candidate_id):
            raise RuntimeError("unexpected failure")

        orphan_storage.register_detector(
            orphan_storage.OrphanDetector(provider="p", list_candidates=None, delete=_boom)
        )

        result = await orphan_storage.delete_candidate("p", "candidate-1")

        assert result.deleted is False
        assert "unexpected failure" in result.reason


def test_grace_period_is_clamped_to_at_least_one_hour(monkeypatch):
    monkeypatch.setenv(orphan_storage.GRACE_PERIOD_ENV, "0")

    assert orphan_storage.orphan_grace_period_hours() == 1
