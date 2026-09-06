# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The replay middleware end to end (#15778).

The property under test is that the handler runs **once**, so every case counts
handler invocations rather than inspecting status codes alone: a second create
returning 201 with a different id would satisfy a status-only assertion while
being exactly the defect.
"""

from __future__ import annotations

import anyio
import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autobot_shared.idempotency import IN_FLIGHT, storage_key
from middleware.idempotency_middleware import HEADER, MAX_KEY_LENGTH, IdempotencyMiddleware


@pytest.fixture
def app_and_calls(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis()

    async def _redis():
        return redis

    monkeypatch.setattr(IdempotencyMiddleware, "_redis", staticmethod(_redis))

    calls = {"create": 0}
    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware)

    @app.post("/create", status_code=201)
    async def _create():
        calls["create"] += 1
        return {"id": f"resource-{calls['create']}"}

    @app.post("/rejects")
    async def _rejects():
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="no")

    return app, calls, redis


class TestTheHandlerRunsOnce:
    def test_a_replayed_key_does_not_reach_the_handler(self, app_and_calls):
        app, calls, _redis_client = app_and_calls
        client = TestClient(app)

        first = client.post("/create", headers={HEADER: "k1"})
        second = client.post("/create", headers={HEADER: "k1"})

        assert calls["create"] == 1, "the handler ran twice — a second resource was created"
        assert first.status_code == second.status_code == 201
        assert first.json() == second.json()
        assert second.headers.get("Idempotent-Replay") == "true"

    def test_a_different_key_creates_a_second_resource(self, app_and_calls):
        """The contrast: replay must not suppress a genuinely new request."""
        app, calls, _redis_client = app_and_calls
        client = TestClient(app)

        client.post("/create", headers={HEADER: "k1"})
        second = client.post("/create", headers={HEADER: "k2"})

        assert calls["create"] == 2
        assert second.json()["id"] == "resource-2"

    def test_no_header_means_no_change_in_behaviour(self, app_and_calls):
        """Opt-in: an unmigrated caller behaves exactly as before."""
        app, calls, _redis_client = app_and_calls
        client = TestClient(app)

        client.post("/create")
        client.post("/create")

        assert calls["create"] == 2
        assert client.post("/create").headers.get("Idempotent-Replay") is None


class TestFailuresAreRetryable:
    def test_a_4xx_does_not_become_a_permanent_replay(self, app_and_calls):
        """Replaying a rejection would deny the caller the corrected retry."""
        app, _calls, _redis_client = app_and_calls
        client = TestClient(app)

        first = client.post("/rejects", headers={HEADER: "k1"})
        second = client.post("/rejects", headers={HEADER: "k1"})

        assert first.status_code == second.status_code == 422
        assert second.headers.get("Idempotent-Replay") is None


class TestGuardrails:
    def test_an_oversized_key_is_rejected(self, app_and_calls):
        app, calls, _redis_client = app_and_calls
        client = TestClient(app)

        response = client.post("/create", headers={HEADER: "x" * (MAX_KEY_LENGTH + 1)})

        assert response.status_code == 400
        assert calls["create"] == 0

    def test_a_key_at_the_limit_is_accepted(self, app_and_calls):
        """The contrast, so the limit is a boundary rather than a wall."""
        app, calls, _redis_client = app_and_calls
        client = TestClient(app)

        response = client.post("/create", headers={HEADER: "x" * MAX_KEY_LENGTH})

        assert response.status_code == 201
        assert calls["create"] == 1

    def test_a_store_outage_serves_the_request_rather_than_refusing_it(self, monkeypatch):
        """The duplicate this prevents is worse than nothing; an outage that
        turns every creation into a 503 is worse than both."""

        async def _no_store():
            return None

        monkeypatch.setattr(IdempotencyMiddleware, "_redis", staticmethod(_no_store))
        calls = {"n": 0}
        app = FastAPI()
        app.add_middleware(IdempotencyMiddleware)

        @app.post("/create", status_code=201)
        async def _create():
            calls["n"] += 1
            return {"id": "x"}

        response = TestClient(app).post("/create", headers={HEADER: "k1"})

        assert response.status_code == 201
        assert calls["n"] == 1


class TestConcurrentReplay:
    def test_an_in_flight_key_is_refused_rather_than_raced(self, app_and_calls):
        """Two retries arriving together must not both create.

        The claim is held directly here, which is what a request still executing
        looks like to the second caller — the state a two-state store would
        collapse into "unseen" and let through.
        """
        app, calls, redis = app_and_calls
        key = storage_key("anonymous", "POST", "/create", "k1")

        async def _hold_the_claim():
            await redis.set(key, IN_FLIGHT)

        anyio.run(_hold_the_claim)

        response = TestClient(app).post("/create", headers={HEADER: "k1"})

        assert response.status_code == 409
        assert "in flight" in response.json()["detail"].lower()
        assert calls["create"] == 0, "the handler ran while another request held the claim"


class TestRegistrationOrder:
    def test_audit_wraps_idempotency(self):
        """A replayed response must still be audited.

        `add_middleware` prepends, so the last registered runs first. If
        idempotency were registered after audit it would become the outermost
        layer and short-circuit replays before the audit entry was written — a
        retried creation would then be absent from the trail entirely. This
        asserts the order rather than the comment claiming it.
        """
        from fastapi import FastAPI as _FastAPI

        from initialization.middleware import configure_idempotency
        from middleware.audit_middleware import AuditMiddleware

        app = _FastAPI()
        configure_idempotency(app)
        app.add_middleware(AuditMiddleware)

        order = [m.cls.__name__ for m in app.user_middleware]

        assert order.index("AuditMiddleware") < order.index("IdempotencyMiddleware")
