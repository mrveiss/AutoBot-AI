# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""POST /api/batch-jobs/load dispatch (#18765).

Every sub-request is sent THROUGH the ASGI application (``request.app``), so the full middleware
stack and the target route's own dependencies -- ``get_current_user``, ``check_admin_permission``,
session ownership -- run exactly as for a direct call. The route's endpoint function is never
called directly.

* Credentials: only the caller's ``Authorization``, ``Cookie`` and ``X-Session-ID`` are forwarded.
  ``X-Internal-API-Key`` is never forwarded and no service key is ever added, so a batch cannot
  carry more authority than its caller.
* Allow-list: only the GET path templates in ``BATCHABLE_GET_PATHS`` dispatch; everything else is
  refused in its own result slot without dispatch.
* Bounds: batch size, per-sub-request timeout and concurrency (env-backed, registered).

This is in-process ASGI dispatch, not network egress: ``ASGITransport`` opens no socket.
"""

import asyncio
import re
import time
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

import httpx
from fastapi import HTTPException, Request

from autobot_shared.env_registry import env
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def _clamped(value, low, high):
    return max(low, min(high, value))


BATCH_MAX_REQUESTS: int = _clamped(int(env("AUTOBOT_BATCH_LOAD_MAX_REQUESTS")), 1, 100)
BATCH_SUBREQUEST_TIMEOUT_SECONDS: float = _clamped(float(env("AUTOBOT_BATCH_LOAD_TIMEOUT_SECONDS")), 1.0, 120.0)
BATCH_CONCURRENCY: int = _clamped(int(env("AUTOBOT_BATCH_LOAD_CONCURRENCY")), 1, 20)

#: Read-only GET path templates the frontend batches today (BatchApiService.ts: the chat-init
#: pair, and loadEssentialChatData's three). ``{name}`` matches exactly one path segment.
BATCHABLE_GET_PATHS: FrozenSet[str] = frozenset(
    {
        "/api/chat/sessions",
        "/api/system/health",
        "/api/chats",
        "/api/chat/health",
        "/api/health",
    }
)

#: The only incoming headers a sub-request inherits. Anything else -- X-Internal-API-Key above all -- is dropped.
FORWARDED_HEADERS: Tuple[str, ...] = ("authorization", "cookie", "x-session-id")

_RECURSION_PREFIX = "/api/batch-jobs"
_FORBIDDEN_CHARS = re.compile(r"[?#\\%\x00-\x20\x7f]")


def _template_regex(template: str) -> "re.Pattern[str]":
    parts = [r"[^/]+" if p.startswith("{") and p.endswith("}") else re.escape(p) for p in template.split("/")]
    return re.compile("^" + "/".join(parts) + "$")


def refusal_for(endpoint: Any, method: str, allow: Iterable[str]) -> Optional[Tuple[int, str]]:
    """Return ``(status, reason)`` if this sub-request must not dispatch, else ``None``."""
    if not isinstance(endpoint, str) or not endpoint.startswith("/api/") or endpoint.startswith("//"):
        return 400, "endpoint must be a path starting with /api/ (no scheme or host)"
    if _FORBIDDEN_CHARS.search(endpoint) or ".." in endpoint.split("/"):
        return 400, "endpoint contains a forbidden character or '..'"
    if endpoint == _RECURSION_PREFIX or endpoint.startswith(_RECURSION_PREFIX + "/"):
        return 403, "batch-jobs endpoints are not batchable"
    if method != "GET":
        return 403, f"method {method} is not batchable"
    if not any(_template_regex(t).match(endpoint) for t in allow):
        return 403, "endpoint is not batchable"
    return None


def forwarded_headers(request: Request) -> Dict[str, str]:
    """The caller's credentials, and nothing else, for the in-process sub-request."""
    return {k: v for k, v in request.headers.items() if k.lower() in FORWARDED_HEADERS}


def _decode_body(response: "httpx.Response") -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _result(
    req: Dict, status: int, body: Any, error: Optional[str], started: float, refused: bool = False
) -> Dict[str, Any]:
    """One slot. ``refused`` marks a sub-request this loader would not dispatch, so a caller can
    run it directly; a dispatched route's own 403 keeps ``refused`` False."""
    return {
        "endpoint": req.get("endpoint"),
        "method": str(req.get("method", "GET")).upper(),
        "status": status,
        "body": body,
        "error": error,
        "timing": round(time.monotonic() - started, 4),
        "refused": refused,
    }


def _error_text(body: Any, status: int) -> Optional[str]:
    if status < 400:
        return None
    detail = body.get("detail") if isinstance(body, dict) else None
    return str(detail) if detail else f"HTTP {status}"


async def _dispatch_one(asgi_client: "httpx.AsyncClient", req: Dict, headers: Dict[str, str]) -> Dict[str, Any]:
    started = time.monotonic()
    params = req.get("params")
    try:
        response = await asyncio.wait_for(
            asgi_client.get(req["endpoint"], params=params if isinstance(params, dict) else None, headers=headers),
            timeout=BATCH_SUBREQUEST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return _result(req, 504, None, "sub-request timed out", started)
    except Exception as exc:  # one failing item must not fail the batch
        logger.error("Batch sub-request %s failed: %s", req.get("endpoint"), exc)
        return _result(req, 502, None, f"sub-request failed: {type(exc).__name__}", started)
    body = _decode_body(response)
    return _result(req, response.status_code, body, _error_text(body, response.status_code), started)


def check_batch_size(requests: List[Dict]) -> None:
    """Refuse an oversized or empty batch before anything is dispatched."""
    if not requests:
        raise HTTPException(status_code=400, detail="batch is empty")
    if len(requests) > BATCH_MAX_REQUESTS:
        raise HTTPException(
            status_code=400, detail=f"batch of {len(requests)} exceeds the maximum of {BATCH_MAX_REQUESTS}"
        )


async def dispatch_batch(request: Request, requests: List[Dict], allow: Optional[Iterable[str]] = None) -> List[Dict]:
    """Run *requests* through ``request.app``; one result per request, in order."""
    check_batch_size(requests)
    allow = tuple(BATCHABLE_GET_PATHS if allow is None else allow)
    headers = forwarded_headers(request)
    gate = asyncio.Semaphore(BATCH_CONCURRENCY)

    async def run(asgi_client: "httpx.AsyncClient", req: Any) -> Dict[str, Any]:
        started = time.monotonic()
        item = req if isinstance(req, dict) else {}
        refusal = refusal_for(item.get("endpoint"), str(item.get("method", "GET")).upper(), allow)
        if refusal:
            return _result(item, refusal[0], None, refusal[1], started, refused=True)
        async with gate:
            return await _dispatch_one(asgi_client, item, headers)

    base_url = str(request.base_url)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=request.app, raise_app_exceptions=False), base_url=base_url
    ) as asgi_client:
        return list(await asyncio.gather(*(run(asgi_client, r) for r in requests)))
