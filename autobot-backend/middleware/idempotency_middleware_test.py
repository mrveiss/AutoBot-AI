# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The replay middleware end to end (#15778).

The property under test is that the handler runs **once**, so every case counts
handler invocations rather than inspecting status codes alone: a second create
returning 201 with a different id would satisfy a status-only assertion while
being exactly the defect.

The second property is that a store failure never changes what the caller is
told. Every one of `claim`, `complete` and `release` gets its own case, because
they fail at different points of the request and only one of them is before the
handler has done anything: a `complete` that raises must still hand back the
response for work that already committed, or the caller retries and creates the
duplicate this middleware exists to prevent.
"""

from __future__ import annotations

import hashlib

import anyio
import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autobot_shared.idempotency import IN_FLIGHT, ReplayedResponse, complete, storage_key
from middleware.idempotency_middleware import (
    HEADER,
    MAX_KEY_LENGTH,
    STATUS_HEADER,
    IdempotencyMiddleware,
)


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

    @app.post("/explodes")
    async def _explodes():
        raise RuntimeError("handler exploded")

    return app, calls, redis


class TestTheHandlerRunsOnce:
    def test_a_replayed_key_does_not_reach_the_handler(self, app_and_calls):
        app, calls, _redis_client = app_and_calls
        client = TestClient(app)

        first = client.post("/create", headers={HEADER: "k1", "Authorization": _TOKEN})
        second = client.post("/create", headers={HEADER: "k1", "Authorization": _TOKEN})

        assert calls["create"] == 1, "the handler ran twice — a second resource was created"
        assert first.status_code == second.status_code == 201
        assert first.json() == second.json()
        assert second.headers.get("Idempotent-Replay") == "true"

    def test_a_different_key_creates_a_second_resource(self, app_and_calls):
        """The contrast: replay must not suppress a genuinely new request."""
        app, calls, _redis_client = app_and_calls
        client = TestClient(app)

        client.post("/create", headers={HEADER: "k1", "Authorization": _TOKEN})
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

        first = client.post("/rejects", headers={HEADER: "k1", "Authorization": _TOKEN})
        second = client.post("/rejects", headers={HEADER: "k1", "Authorization": _TOKEN})

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

        response = TestClient(app).post("/create", headers={HEADER: "k1", "Authorization": _TOKEN})

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
        key = storage_key(_credential_actor(_TOKEN), "POST", "/create", "k1")

        async def _hold_the_claim():
            await redis.set(key, IN_FLIGHT)

        anyio.run(_hold_the_claim)

        response = TestClient(app).post("/create", headers={HEADER: "k1", "Authorization": _TOKEN})

        assert response.status_code == 409
        assert "in flight" in response.json()["detail"].lower()
        assert calls["create"] == 0, "the handler ran while another request held the claim"


class _RedisFailingAt:
    """A store that works except at one operation.

    That is how a real outage arrives -- mid-request, not conveniently before
    it. Wrapping a working fakeredis rather than mocking the whole client keeps
    every other operation honest, so the test exercises the actual code path up
    to the failure.
    """

    def __init__(self, inner, failing: str) -> None:
        self._inner = inner
        self._failing = failing

    def __getattr__(self, name):
        if name == self._failing:

            async def _unreachable(*_args, **_kwargs):
                raise ConnectionError("redis went away")

            return _unreachable
        return getattr(self._inner, name)


def _app_with_store(monkeypatch, failing: str):
    """The same app as the main fixture, but with one Redis call that raises."""
    store = _RedisFailingAt(fakeredis.aioredis.FakeRedis(), failing)

    async def _redis():
        return store

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

    @app.post("/explodes")
    async def _explodes():
        raise RuntimeError("handler exploded")

    return app, calls


class TestAStoreFailureNeverChangesTheAnswer:
    """Redis is an optimisation over the caller's own retry, at every step."""

    def test_a_claim_failure_serves_the_request_rather_than_refusing_it(self, monkeypatch):
        """`set` raises after the client was acquired -- the case the
        acquisition guard alone never saw."""
        app, calls = _app_with_store(monkeypatch, failing="set")

        response = TestClient(app).post("/create", headers={HEADER: "k1", "Authorization": _TOKEN})

        assert response.status_code == 201
        assert calls["create"] == 1, "a store failure refused a creation instead of serving it"

    def test_a_completion_failure_still_returns_the_handler_response(self, monkeypatch):
        """The handler already committed. Reporting an error for work that
        succeeded provokes exactly the duplicate retry this prevents."""
        app, calls = _app_with_store(monkeypatch, failing="eval")

        response = TestClient(app).post("/create", headers={HEADER: "k1", "Authorization": _TOKEN})

        assert response.status_code == 201, "a failed record turned a successful creation into an error"
        assert response.json() == {"id": "resource-1"}
        assert calls["create"] == 1

    def test_a_release_failure_preserves_the_original_status(self, monkeypatch):
        """A 4xx releases the claim; failing to release must not overwrite the
        4xx the caller needs in order to correct their request."""
        app, _calls = _app_with_store(monkeypatch, failing="eval")

        response = TestClient(app).post("/rejects", headers={HEADER: "k1", "Authorization": _TOKEN})

        assert response.status_code == 422

    def test_a_release_failure_preserves_the_original_exception(self, monkeypatch):
        """The handler's own failure is what the caller must see. An unguarded
        release would replace RuntimeError with the store's ConnectionError and
        hide the real fault."""
        app, _calls = _app_with_store(monkeypatch, failing="eval")

        with pytest.raises(RuntimeError, match="handler exploded"):
            TestClient(app).post("/explodes", headers={HEADER: "k1", "Authorization": _TOKEN})


class TestFencingReachesTheMiddleware:
    def test_a_request_whose_claim_lapsed_does_not_overwrite_a_successors_record(self, app_and_calls):
        """End to end: the middleware must pass its own token to `complete`, not
        blindly overwrite. A successor's stored response has to survive."""
        app, calls, redis = app_and_calls
        key = storage_key(_credential_actor(_TOKEN), "POST", "/create", "k1")
        client = TestClient(app)

        client.post("/create", headers={HEADER: "k1", "Authorization": _TOKEN})  # the successor's record

        async def _a_lapsed_predecessor_tries_to_publish():
            return await complete(redis, key, "a-token-from-a-lapsed-request", ReplayedResponse(201, '{"id": "stale"}'))

        assert anyio.run(_a_lapsed_predecessor_tries_to_publish) is False
        replay = client.post("/create", headers={HEADER: "k1", "Authorization": _TOKEN})
        assert replay.json() == {"id": "resource-1"}
        assert calls["create"] == 1


#: A credential the middleware can namespace by. Ordinary user requests are
#: authenticated by route dependencies, so `request.state.user` is unset while
#: middleware runs -- the namespace comes from what the request presents.
_TOKEN = "Bearer test-caller"


def _credential_actor(token: str) -> str:
    """The namespace the middleware computes for an Authorization header."""
    return "cred:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]


class TestTheReplayNamespaceIsPerCaller:
    """`request.state.user` is written by route-level dependencies, so at
    middleware time it is unset for every ordinary request. Reading it put all
    callers in one "anonymous" namespace: a second user sending the same key to
    the same path received the first user's response body.
    """

    def test_two_credentials_do_not_share_a_replay(self, app_and_calls):
        app, calls = app_and_calls[0], app_and_calls[1]
        client = TestClient(app)

        first = client.post("/create", headers={HEADER: "shared", "Authorization": "Bearer alice"})
        second = client.post("/create", headers={HEADER: "shared", "Authorization": "Bearer bob"})

        assert calls["create"] == 2, "the second caller was served the first caller's stored response"
        assert first.json() != second.json()
        assert second.headers.get("Idempotent-Replay") is None

    def test_the_same_credential_still_replays(self, app_and_calls):
        """The contrast: per-caller scoping must not disable the feature."""
        app, calls = app_and_calls[0], app_and_calls[1]
        client = TestClient(app)

        first = client.post("/create", headers={HEADER: "k", "Authorization": "Bearer alice"})
        second = client.post("/create", headers={HEADER: "k", "Authorization": "Bearer alice"})

        assert calls["create"] == 1
        assert first.json() == second.json()
        assert second.headers.get("Idempotent-Replay") == "true"

    def test_no_token_material_reaches_the_key(self):
        """The namespace is a digest: a bearer token must not become a Redis key."""
        actor = _credential_actor("Bearer super-secret-token")

        assert "super-secret-token" not in actor
        assert "super-secret-token" not in storage_key(actor, "POST", "/create", "k")


class TestAnUncredentialedRequestGetsNoReplay:
    """#15814: the peer-address fallback bucketed all anonymous traffic together.

    Behind a reverse proxy `request.client.host` is the proxy for every external
    caller, and keys are client-chosen — so an anonymous caller sending
    `Idempotency-Key: 1` would receive another anonymous caller's stored body
    with no guessing at all. The layer now declines rather than narrowing the
    collision, because "less likely" is the wrong shape for a disclosure.
    """

    def test_two_anonymous_callers_sharing_a_key_do_not_share_a_response(self, app_and_calls):
        app, calls = app_and_calls[0], app_and_calls[1]
        client = TestClient(app)

        first = client.post("/create", headers={HEADER: "1"})
        second = client.post("/create", headers={HEADER: "1"})

        assert calls["create"] == 2, "an anonymous caller was served another anonymous caller's response"
        assert first.json() != second.json()

    def test_the_caller_is_told_the_guarantee_was_not_given(self, app_and_calls):
        """Silently withholding what was asked for is the shape this repository
        keeps finding: a check that reports success without doing the work."""
        app = app_and_calls[0]

        response = TestClient(app).post("/create", headers={HEADER: "1"})

        assert response.headers.get(STATUS_HEADER) == "skipped-unauthenticated"
        assert response.headers.get("Idempotent-Replay") is None

    def test_a_credentialed_caller_is_unaffected(self, app_and_calls):
        """The contrast: declining must apply only where there is no principal."""
        app, calls = app_and_calls[0], app_and_calls[1]
        client = TestClient(app)

        client.post("/create", headers={HEADER: "1", "Authorization": "Bearer alice"})
        second = client.post("/create", headers={HEADER: "1", "Authorization": "Bearer alice"})

        assert calls["create"] == 1
        assert second.headers.get(STATUS_HEADER) is None
        assert second.headers.get("Idempotent-Replay") == "true"

    def test_no_actor_is_derived_without_a_credential(self):
        from starlette.datastructures import Headers

        class _Req:
            state = type("S", (), {})()
            headers = Headers({})
            cookies: dict = {}
            client = type("C", (), {"host": "10.0.0.1"})()

        assert IdempotencyMiddleware._actor(_Req()) is None
