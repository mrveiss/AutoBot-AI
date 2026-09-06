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
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from autobot_shared.idempotency import IN_FLIGHT, ReplayedResponse, claim, complete, release, storage_key
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
        existing = await claim(redis, key)
        if existing is IN_FLIGHT or existing == IN_FLIGHT:
            return JSONResponse(
                status_code=409,
                content={"detail": "A request with this Idempotency-Key is still in flight"},
            )
        if isinstance(existing, ReplayedResponse):
            return Response(
                content=existing.body,
                status_code=existing.status_code,
                media_type="application/json",
                headers={"Idempotent-Replay": "true"},
            )

        return await self._run_and_record(request, call_next, redis, key)

    async def _run_and_record(self, request: Request, call_next, redis, key: str) -> Response:
        try:
            response = await call_next(request)
        except Exception:
            # The claim must not outlive a request that failed, or the retry the
            # caller has to make is impossible until the TTL expires.
            await release(redis, key)
            raise

        body = b"".join([section async for section in response.body_iterator])
        if 200 <= response.status_code < 300:
            await complete(redis, key, ReplayedResponse(status_code=response.status_code, body=body.decode("utf-8")))
        else:
            # Only a success is worth replaying: a 4xx is the caller's to fix,
            # and replaying it would deny them the corrected retry.
            await release(redis, key)
        return Response(
            content=body,
            status_code=response.status_code,
            media_type=response.media_type,
            headers=dict(response.headers),
        )

    @staticmethod
    def _actor(request: Request) -> str:
        """Who is asking -- so two callers cannot collide on the same key."""
        user = getattr(request.state, "user", None) or {}
        if isinstance(user, dict):
            return str(user.get("user_id") or user.get("username") or "anonymous")
        return str(getattr(user, "user_id", None) or "anonymous")

    @staticmethod
    async def _redis():
        try:
            from autobot_shared.redis_client import get_async_redis_client

            return await get_async_redis_client(database="main")
        except Exception as exc:  # noqa: BLE001 - any failure here means "no store"
            logger.warning("idempotency store unreachable: %s", exc)
            return None
