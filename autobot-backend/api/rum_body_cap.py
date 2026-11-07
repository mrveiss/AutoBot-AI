# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cap the body of the open RUM ingest routes while it streams, before parsing (#16375).

The first version enforced the cap in a route dependency, which FastAPI runs
only after it has read and parsed the whole JSON body -- so an oversize payload
was fully parsed before it was refused. ``BodyCappedRoute`` wraps the request's
ASGI ``receive`` instead: it refuses a declared ``Content-Length`` over the cap
at once, counts bytes as each chunk arrives (a chunked body has no declared
length), and raises 413 the moment the count passes the cap -- before FastAPI
decodes a byte of JSON.

Only routes listed in ``BODY_CAP_ENV`` are capped; every other route on the
router is passed through unchanged.
"""

from __future__ import annotations

from typing import Callable, Dict

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from starlette.types import Message, Receive

from autobot_shared.env_registry import env

#: Route path (as declared on the router) -> env var holding its byte cap.
BODY_CAP_ENV: Dict[str, str] = {
    "/event": "AUTOBOT_RUM_EVENT_MAX_BYTES",
    "/metrics": "AUTOBOT_RUM_METRICS_MAX_BYTES",
}


def _too_large(cap: int) -> HTTPException:
    return HTTPException(status_code=413, detail=f"RUM payload exceeds the {cap}-byte limit")


def capped_receive(receive: Receive, cap: int) -> Receive:
    """A ``receive`` that raises 413 once more than *cap* body bytes have arrived."""
    seen = 0

    async def _receive() -> Message:
        nonlocal seen
        message = await receive()
        if message.get("type") == "http.request":
            seen += len(message.get("body", b""))
            if seen > cap:
                raise _too_large(cap)
        return message

    return _receive


def _declared_over(request: Request, cap: int) -> bool:
    declared = request.headers.get("content-length", "")
    return declared.isdigit() and int(declared) > cap


class BodyCappedRoute(APIRoute):
    """An ``APIRoute`` that caps the streamed body of the routes in ``BODY_CAP_ENV``."""

    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()
        cap_env = BODY_CAP_ENV.get(self.path_format)
        if cap_env is None:
            return handler

        async def capped_handler(request: Request):
            cap = int(env(cap_env))
            if _declared_over(request, cap):
                raise _too_large(cap)
            return await handler(Request(request.scope, capped_receive(request.receive, cap), request._send))

        return capped_handler
