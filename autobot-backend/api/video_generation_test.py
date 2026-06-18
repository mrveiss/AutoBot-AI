# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the video generation API — GH#9016. All I/O is mocked."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import video_generation as vg

USER = {"username": "testuser", "role": "user", "org_id": "org123"}


def _make_app() -> FastAPI:
    app = FastAPI()

    async def _override_user():
        return USER

    from auth_middleware import get_current_user

    app.dependency_overrides[get_current_user] = _override_user
    app.include_router(vg.router)
    return app


@pytest.fixture
def store():
    """In-memory Redis stand-in keyed by job key."""
    data = {}

    async def _set(key, value, expire=None, database="main"):
        data[key] = value
        return True

    async def _get(key, database="main"):
        return data.get(key)

    with (
        patch.object(vg, "redis_set", new=AsyncMock(side_effect=_set)),
        patch.object(vg, "redis_get", new=AsyncMock(side_effect=_get)),
    ):
        yield data


@pytest.fixture
def client(store):
    return TestClient(_make_app())


def _fake_provider(available=True, name="runway"):
    p = MagicMock()
    p.name = name
    p.available = available
    p.submit = AsyncMock(return_value="provider-job-1")
    return p


def test_list_providers(client):
    with patch.dict("os.environ", {"RUNWAY_API_KEY": "x", "SORA_API_KEY": "", "KLING_API_KEY": ""}, clear=False):
        resp = client.get("/providers")
    assert resp.status_code == 200
    names = {p["name"]: p["available"] for p in resp.json()["providers"]}
    assert names["runway"] is True
    assert names["sora"] is False


def test_generate_submits_and_returns_job_id(client, store):
    provider = _fake_provider()
    with patch.object(vg, "get_provider", return_value=provider), patch.object(vg, "_PROVIDERS_AVAILABLE", True):
        resp = client.post("/generate", json={"prompt": "a cat", "duration": 5, "provider": "runway"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    job_id = body["job_id"]
    assert job_id
    # Record persisted with provider job id.
    stored = json.loads(next(iter(store.values())))
    assert stored["provider_job_id"] == "provider-job-1"
    assert stored["prompt"] == "a cat"


def test_generate_provider_disabled(client):
    provider = _fake_provider(available=False)
    with patch.object(vg, "get_provider", return_value=provider), patch.object(vg, "_PROVIDERS_AVAILABLE", True):
        resp = client.post("/generate", json={"prompt": "a cat", "provider": "runway"})
    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert "RUNWAY_API_KEY" in resp.json()["error"]


def test_status_unknown_job_404(client):
    resp = client.get("/status/does-not-exist")
    assert resp.status_code == 404


def test_status_running_then_succeeded(client, store):
    provider = _fake_provider()
    # Submit first to create a job record.
    with patch.object(vg, "get_provider", return_value=provider), patch.object(vg, "_PROVIDERS_AVAILABLE", True):
        job_id = client.post("/generate", json={"prompt": "a cat", "provider": "runway"}).json()["job_id"]

    running = vg.VideoStatusResponse  # noqa: F841 - sanity reference
    poll_provider = MagicMock()
    poll_provider.poll = AsyncMock(
        return_value=MagicMock(
            status="succeeded", progress=1.0, video_url="https://v/c.mp4", provider="runway", error=None
        )
    )
    with patch.object(vg, "get_provider", return_value=poll_provider):
        resp = client.get(f"/status/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["video_url"] == "https://v/c.mp4"
    assert body["progress"] == 1.0


def test_full_lifecycle_submit_then_poll_progress(client, store):
    provider = _fake_provider()
    with patch.object(vg, "get_provider", return_value=provider), patch.object(vg, "_PROVIDERS_AVAILABLE", True):
        job_id = client.post("/generate", json={"prompt": "clip", "provider": "runway"}).json()["job_id"]

    poll_provider = MagicMock()
    poll_provider.poll = AsyncMock(
        return_value=MagicMock(status="running", progress=0.5, video_url=None, provider="runway", error=None)
    )
    with patch.object(vg, "get_provider", return_value=poll_provider):
        resp = client.get(f"/status/{job_id}")
    body = resp.json()
    assert body["status"] == "running"
    assert body["progress"] == 0.5
    assert body["video_url"] is None
