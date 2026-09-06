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

from api import playwright_session_scope
from api.playwright_session_scope import PlaywrightSessionScopeMiddleware, _message
from autobot_shared.logging_manager import LogFloodSuppressionFilter


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
    # Matched on the issue reference, not on one phrasing: the middleware emits a
    # weaker sentence when it declines to read the body, and a helper keyed to the
    # confident wording would silently stop counting those.
    return [r.getMessage() for r in caplog.records if "(#15802)" in r.getMessage()]


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


class TestABodyItRefusesToRead:
    """The body is inspected only when Content-Length says it is small.

    `ValidationMiddleware` buffers an unbounded body before checking its own
    limit (#15857), so an unbounded read here would add a second copy of a
    payload nothing has bounded. Declining must produce a weaker claim, not
    silence and not a claim that was never established.
    """

    def test_a_body_over_the_bound_is_not_read(self, client, caplog, monkeypatch):
        monkeypatch.setattr(playwright_session_scope, "_INSPECT_MAX_BYTES", 4)

        with caplog.at_level(logging.WARNING):
            client.post("/api/playwright/navigate", json={"url": "http://x"})

        assert len(_warnings(caplog)) == 1
        message = _warnings(caplog)[0]
        assert "could not be confirmed as scoped" in message
        assert "over the 4 byte inspection bound" in message
        assert "is NOT isolated" not in message

    def test_a_declared_id_is_not_read_either_and_still_warns(self, client, caplog, monkeypatch):
        """An oversized body carrying a valid id is reported unconfirmed, not scoped.

        This is the honest cost of the bound and is asserted rather than hidden:
        the middleware did not look, so it may not claim the caller is scoped.
        """
        monkeypatch.setattr(playwright_session_scope, "_INSPECT_MAX_BYTES", 4)

        with caplog.at_level(logging.WARNING):
            client.post("/api/playwright/navigate", json={"url": "http://x", "session_id": "s1"})

        assert len(_warnings(caplog)) == 1
        assert "could not be confirmed as scoped" in _warnings(caplog)[0]

    def test_a_query_param_id_survives_the_refusal(self, client, caplog, monkeypatch):
        monkeypatch.setattr(playwright_session_scope, "_INSPECT_MAX_BYTES", 4)

        with caplog.at_level(logging.WARNING):
            client.post("/api/playwright/navigate?session_id=s1", json={"url": "http://x"})

        assert _warnings(caplog) == []

    def test_a_chunked_body_has_no_content_length_and_is_not_read(self, client, caplog):
        with caplog.at_level(logging.WARNING):
            client.post(
                "/api/playwright/navigate",
                content=iter([b'{"url": "http://x", "session_id": "s1"}']),
                headers={"content-type": "application/json"},
            )

        assert len(_warnings(caplog)) == 1
        assert "no content-length header" in _warnings(caplog)[0]

    def test_the_route_still_receives_an_uninspected_body(self, client, monkeypatch):
        """Declining to read must not disturb the stream the route reads."""
        monkeypatch.setattr(playwright_session_scope, "_INSPECT_MAX_BYTES", 4)

        response = client.post("/api/playwright/navigate", json={"url": "http://x", "session_id": "s1"})

        assert response.json() == {"url": "http://x", "session_id": "s1"}


class TestTheLogCanStillAnswerWho:
    """A second unscoped caller must not be silenced by the first one's traffic.

    `LogFloodSuppressionFilter` keys on the uninterpolated template plus call
    site (#15774). Passing the caller as a `%s` argument would give every caller
    one shared budget, so the sixth unscoped call in a window is dropped whoever
    made it — and "who is still unscoped" stops being answerable from the log,
    which is the entire point of #15802.
    """

    @staticmethod
    def _record(message: str) -> logging.LogRecord:
        return logging.LogRecord("api.playwright", logging.WARNING, __file__, 42, message, (), None)

    def test_distinct_callers_each_get_their_own_budget(self):
        flood = LogFloodSuppressionFilter(threshold=1, window_seconds=60.0)

        first = flood.filter(self._record(_message("/api/playwright/navigate", "10.0.0.1", None)))
        second = flood.filter(self._record(_message("/api/playwright/navigate", "10.0.0.2", None)))

        assert (first, second) == (True, True)

    def test_the_same_caller_is_still_suppressed(self):
        """The control: without this, the test above passes on a filter that never suppresses."""
        flood = LogFloodSuppressionFilter(threshold=1, window_seconds=60.0)
        message = _message("/api/playwright/navigate", "10.0.0.1", None)

        emitted = [flood.filter(self._record(message)) for _ in range(3)]

        assert emitted == [True, False, False]
