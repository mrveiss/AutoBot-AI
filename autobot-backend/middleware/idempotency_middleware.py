# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Make a retried creation return the first response instead of creating twice (#15778).

Opt-in by header. A request without ``Idempotency-Key`` behaves exactly as it
did before this middleware existed -- no route changes, no behaviour change, and
nothing to migrate. That is deliberate: a replay layer that applied itself to
every POST would change the meaning of endpoints nobody had reviewed for it.

Scope is ``POST`` only. ``PUT``/``DELETE`` are idempotent by definition of the
verb; ``PATCH`` is not, but a retried partial update does not *create* a second
resource, which is the failure this addresses.

FAILING OPEN IS THE WHOLE POLICY
--------------------------------
Every interaction with the store can fail, not just acquiring the client, and
the answer is the same at each one: this layer is an optimisation over the
caller's own retry, so a store outage must cost replay protection and nothing
else. A ``claim`` that raises serves the request unprotected. A ``complete``
that raises still returns the response the handler already produced -- the work
committed, and reporting a 500 for it would provoke exactly the duplicate retry
this middleware exists to prevent. A ``release`` that raises leaves the original
response, or the original exception, untouched; the claim then lapses on its own
TTL. Nothing about a Redis failure may change what the caller is told about
their creation.
"""

from __future__ import annotations

import hashlib

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from autobot_shared.idempotency import Claim, ReplayedResponse, claim, complete, release, storage_key
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

HEADER = "Idempotency-Key"

#: Longest client key accepted. A key is an opaque token, not a payload; the
#: digest would absorb any length, but accepting unbounded input from an
#: unauthenticated header is not something to do without a reason.
MAX_KEY_LENGTH = 255


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Replay a completed creation; refuse a concurrent one."""

    async def dispatch(self, request: Request, call_next):
        client_key = request.headers.get(HEADER)
        if request.method.upper() != "POST" or not client_key:
            return await call_next(request)
        if len(client_key) > MAX_KEY_LENGTH:
            return JSONResponse(
                status_code=400, content={"detail": f"{HEADER} must be at most {MAX_KEY_LENGTH} characters"}
            )

        redis = await self._redis()
        if redis is None:
            # Redis unavailable: serve the request rather than refuse it. The
            # duplicate this middleware prevents is worse than nothing, but an
            # outage that turns every creation into a 503 is worse than both.
            logger.warning("idempotency store unavailable; serving %s without replay protection", request.url.path)
            return await call_next(request)

        key = storage_key(self._actor(request), request.method, request.url.path, client_key)
        return await self._replay_or_run(request, call_next, redis, key)

    async def _replay_or_run(self, request: Request, call_next, redis, key: str) -> Response:
        outcome = await self._claim(redis, key, request.url.path)
        if outcome is None:
            return await call_next(request)
        if outcome.in_flight:
            return JSONResponse(
                status_code=409,
                content={"detail": "A request with this Idempotency-Key is still in flight"},
            )
        if outcome.replay is not None:
            return Response(
                content=outcome.replay.body,
                status_code=outcome.replay.status_code,
                media_type="application/json",
                headers={"Idempotent-Replay": "true"},
            )
        return await self._run_and_record(request, call_next, redis, key, str(outcome.token))

    async def _run_and_record(self, request: Request, call_next, redis, key: str, token: str) -> Response:
        try:
            response = await call_next(request)
        except Exception:
            # The claim must not outlive a request that failed, or the retry the
            # caller has to make is impossible until the TTL expires.
            await self._release(redis, key, token)
            raise

        body = b"".join([section async for section in response.body_iterator])
        await self._record(redis, key, token, response.status_code, body)
        return Response(
            content=body,
            status_code=response.status_code,
            media_type=response.media_type,
            headers=dict(response.headers),
        )

    @staticmethod
    async def _claim(redis, key: str, path: str) -> Claim | None:
        """The claim, or ``None`` meaning "store failed, serve unprotected"."""
        try:
            return await claim(redis, key)
        except Exception as exc:  # noqa: BLE001 - a store failure must not refuse the request
            logger.warning("idempotency claim failed for %s; serving without replay protection: %s", path, exc)
            return None

    @staticmethod
    async def _record(redis, key: str, token: str, status_code: int, body: bytes) -> None:
        """Store a success, drop the claim otherwise -- never raising either way.

        The handler has already run. A store failure here changes nothing the
        caller should be told: reporting an error for work that committed is the
        duplicate-provoking answer this middleware exists to avoid.
        """
        try:
            if 200 <= status_code < 300:
                await complete(redis, key, token, ReplayedResponse(status_code=status_code, body=body.decode("utf-8")))
            else:
                # Only a success is worth replaying: a 4xx is the caller's to fix,
                # and replaying it would deny them the corrected retry.
                await release(redis, key, token)
        except Exception as exc:  # noqa: BLE001 - the response stands regardless
            logger.warning("idempotency record failed after the handler succeeded: %s", exc)

    @staticmethod
    async def _release(redis, key: str, token: str) -> None:
        """Drop the claim, preserving whatever the caller was already getting."""
        try:
            await release(redis, key, token)
        except Exception as exc:  # noqa: BLE001 - the original outcome is what matters
            logger.warning("idempotency release failed; the claim will lapse on its TTL: %s", exc)

    @staticmethod
    def _actor(request: Request) -> str:
        """A namespace for this caller's keys -- NOT an authorization decision.

        The first version read ``request.state.user``, which is wrong here and
        dangerously so: that attribute is populated by **route-level
        dependencies**, inside the handler, so at middleware time it is unset for
        every ordinary user request. Every caller therefore shared the
        ``"anonymous"`` namespace, and a second user sending the same
        ``Idempotency-Key`` to the same path would have been handed the first
        user's stored response body -- a cross-user disclosure produced by a
        replay layer, before any authentication had run.

        So the namespace comes from the credential **presented on the request**,
        which does exist at middleware time. It is hashed, so no token material
        reaches Redis, and it is only a bucket: two different credentials can
        never share a replay, and this makes no claim about whether either is
        valid. Authentication still happens exactly where it did before.

        ``request.state.user`` is still preferred when something upstream (the
        service-auth middleware, which does run before this) has already set it:
        a service identity is stable across token rotation in a way a token
        digest is not.
        """
        user = getattr(request.state, "user", None)
        if isinstance(user, dict):
            identity = user.get("user_id") or user.get("username")
            if identity:
                return f"user:{identity}"
        elif user is not None and getattr(user, "user_id", None):
            return f"user:{user.user_id}"

        for header in ("authorization", "x-internal-api-key", "x-service-key"):
            presented = request.headers.get(header)
            if presented:
                return "cred:" + hashlib.sha256(presented.encode("utf-8")).hexdigest()[:32]
        session = request.cookies.get("session") or request.cookies.get("access_token")
        if session:
            return "sess:" + hashlib.sha256(session.encode("utf-8")).hexdigest()[:32]
        # No credential at all: fall back to the peer address. Two anonymous
        # callers behind one proxy share a namespace, which is the weakest case
        # and is why an unauthenticated endpoint should not rely on this.
        return "peer:" + (request.client.host if request.client else "unknown")

    @staticmethod
    async def _redis():
        try:
            from autobot_shared.redis_client import get_async_redis_client

            return await get_async_redis_client(database="main")
        except Exception as exc:  # noqa: BLE001 - any failure here means "no store"
            logger.warning("idempotency store unreachable: %s", exc)
            return None
