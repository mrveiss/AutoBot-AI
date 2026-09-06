# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An unscoped Playwright caller must be visible, not silent (#15802).

Driven through a real app and TestClient rather than by calling the helper:
the property is that a *request* which omits `session_id` produces a warning
and is otherwise unaffected, and only an end-to-end drive can show that reading
the body in middleware does not consume it before the route parses it.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from api.playwright_session_scope import PlaywrightSessionScopeMiddleware


class _Navigate(BaseModel):
    url: str
    session_id: str | None = None


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.add_middleware(PlaywrightSessionScopeMiddleware)

    @app.post("/api/playwright/navigate")
    async def _navigate(request: _Navigate):
        return {"url": request.url, "session_id": request.session_id}

    @app.get("/api/playwright/status")
    async def _status():
        return {"ok": True}

    @app.post("/api/other/thing")
    async def _other(request: _Navigate):
        return {"ok": True}

    return TestClient(app)


def _warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "without session_id" in r.getMessage()]


class TestTheWarningFiresExactlyOnOmission:
    def test_an_omitted_session_id_warns(self, client, caplog):
        with caplog.at_level(logging.WARNING):
            client.post("/api/playwright/navigate", json={"url": "http://x"})

        assert len(_warnings(caplog)) == 1

    def test_a_present_session_id_is_silent(self, client, caplog):
        """Warning on every call trains the reader to ignore it."""
        with caplog.at_level(logging.WARNING):
            client.post("/api/playwright/navigate", json={"url": "http://x", "session_id": "s1"})

        assert _warnings(caplog) == []

    def test_an_empty_session_id_counts_as_omitted(self, client, caplog):
        """`""` routes to the shared context exactly as `None` does, so treating
        it as scoped would be the same defect with a different spelling."""
        with caplog.at_level(logging.WARNING):
            client.post("/api/playwright/navigate", json={"url": "http://x", "session_id": ""})

        assert len(_warnings(caplog)) == 1

    def test_a_query_param_id_is_honoured(self, client, caplog):
        """`GET /status` carries the id in the query string, not a body."""
        with caplog.at_level(logging.WARNING):
            client.get("/api/playwright/status?session_id=s1")

        assert _warnings(caplog) == []

    def test_a_status_call_without_an_id_warns(self, client, caplog):
        with caplog.at_level(logging.WARNING):
            client.get("/api/playwright/status")

        assert len(_warnings(caplog)) == 1


class TestNothingElseChanges:
    def test_the_route_still_receives_its_body(self, client):
        """The middleware reads the body; if that consumed the stream the route
        would 422 or see nothing. This is why the test drives a real app."""
        response = client.post("/api/playwright/navigate", json={"url": "http://x", "session_id": "s1"})

        assert response.status_code == 200
        assert response.json() == {"url": "http://x", "session_id": "s1"}

    def test_an_unscoped_call_is_served_normally(self, client):
        """Observational, not enforcing: making the field required would break
        every existing caller, which is a decision rather than a fix."""
        response = client.post("/api/playwright/navigate", json={"url": "http://x"})

        assert response.status_code == 200
        assert response.json()["session_id"] is None

    def test_a_non_playwright_route_is_untouched(self, client, caplog):
        """The contrast: a middleware that warned on every path would be noise
        and would say nothing about Playwright isolation."""
        with caplog.at_level(logging.WARNING):
            response = client.post("/api/other/thing", json={"url": "http://x"})

        assert response.status_code == 200
        assert _warnings(caplog) == []

    def test_a_malformed_body_warns_rather_than_crashing(self, client, caplog):
        """A caller that sent nothing parseable is exactly the caller this
        exists to find; skipping it would reproduce the silence."""
        with caplog.at_level(logging.WARNING):
            client.post("/api/playwright/navigate", content=b"not json", headers={"content-type": "application/json"})

        assert len(_warnings(caplog)) == 1


class TestTheWarningIdentifiesTheCaller:
    def test_the_caller_and_route_are_named(self, client, caplog):
        """A warning that cannot say who is unscoped does not make the
        population discoverable, which is the whole point."""
        with caplog.at_level(logging.WARNING):
            client.post("/api/playwright/navigate", json={"url": "http://x"}, headers={"user-agent": "legacy-mcp/0.3"})

        message = _warnings(caplog)[0]
        assert "/api/playwright/navigate" in message
        assert "legacy-mcp/0.3" in message
