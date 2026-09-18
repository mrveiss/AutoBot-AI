# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The orphan-storage admin route: admin-only, aggregates every detector, no host paths (#17038, #17039)."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.admin_orphan_storage as route
from services import orphan_storage

_ADMIN = {"username": "admin", "role": "admin", "user_id": "admin-1"}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(route.router, prefix="/api")
    return TestClient(app)


def test_a_non_admin_is_refused(monkeypatch):
    monkeypatch.setattr(orphan_storage, "_REGISTRY", {})
    auth = MagicMock()
    auth.get_user_from_request.return_value = {"username": "u2", "role": "user", "user_id": "u2"}

    with patch("auth_rbac.get_auth_middleware", return_value=auth):
        response = _client().get("/api/admin/orphan-storage")

    assert response.status_code in (401, 403)


def test_lists_candidates_from_every_registered_detector_with_totals(monkeypatch):
    monkeypatch.setattr(orphan_storage, "_REGISTRY", {})

    async def _list_a():
        return [
            orphan_storage.OrphanCandidate(
                provider="a",
                id="1",
                location="a/1",
                size_bytes=100,
                modified_at="2026-01-01T00:00:00+00:00",
                reason="test-a",
            )
        ]

    async def _list_b():
        return [
            orphan_storage.OrphanCandidate(
                provider="b",
                id="1",
                location="b/1",
                size_bytes=50,
                modified_at="2026-01-01T00:00:00+00:00",
                reason="test-b",
            )
        ]

    orphan_storage.register_detector(orphan_storage.OrphanDetector(provider="a", list_candidates=_list_a, delete=None))
    orphan_storage.register_detector(orphan_storage.OrphanDetector(provider="b", list_candidates=_list_b, delete=None))

    auth = MagicMock()
    auth.get_user_from_request.return_value = _ADMIN

    with patch("auth_rbac.get_auth_middleware", return_value=auth):
        response = _client().get("/api/admin/orphan-storage")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    assert body["total_size_bytes"] == 150
    assert {c["provider"] for c in body["candidates"]} == {"a", "b"}
    assert {s["provider"]: s["available"] for s in body["provider_statuses"]} == {"a": True, "b": True}


def test_an_unavailable_detector_names_itself_rather_than_reading_as_success(monkeypatch):
    """66's review: an outage response must not look like an empty success."""
    monkeypatch.setattr(orphan_storage, "_REGISTRY", {})

    async def _broken():
        raise RuntimeError("connection refused: redis.internal:6379")

    orphan_storage.register_detector(
        orphan_storage.OrphanDetector(provider="broken", list_candidates=_broken, delete=None)
    )

    auth = MagicMock()
    auth.get_user_from_request.return_value = _ADMIN

    with patch("auth_rbac.get_auth_middleware", return_value=auth):
        response = _client().get("/api/admin/orphan-storage")

    assert response.status_code == 200
    body = response.json()
    assert body["candidates"] == []
    assert body["provider_statuses"] == [{"provider": "broken", "available": False, "error": "RuntimeError"}]
    assert "redis.internal" not in response.text, "#17065: never the raw exception text"
