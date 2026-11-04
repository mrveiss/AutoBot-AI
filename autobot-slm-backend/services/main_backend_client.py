# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ONE client the SLM's proxies use to call the main backend with the internal key (#20760).

The voice and personality proxies carried the same ``_proxy_to_main_backend``, and the memory proxy
its own fetch, each resolving the backend URL and the key, building the headers and mapping transport
errors. ``autobot_shared.node_proxy`` already owns those primitives (#14886); this owns the call, so
every route that reaches the backend this way checks, sends and fails the same way, and a fault seen
on any of them (a missing key, a refused key: #20750) is handled in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import Response

from autobot_shared import node_proxy
from autobot_shared.logging_manager import get_logger
from config import settings
from services.backend_key_finding import report_backend_refused_internal_key

logger = get_logger(__name__)

# URL, key, TLS policy and timeout all come from the shared node client (#14886). An earlier revision
# of the memory proxy read its own AUTOBOT_NODE_PROXY_VERIFY_TLS with a "false" default, shipping
# verification OFF unless an operator opted in -- on the channel that carries the internal API key
# (#14653). A per-module switch is how that happens; there is one switch for every node proxy, and no
# proxy -- nor this client -- holds an opinion about it.


@dataclass
class MainBackendUnavailable(Exception):  # not frozen: `raise ... from` sets __cause__
    """The call couldn't be made or completed: an HTTP status, a client-facing detail, a stable reason."""

    status_code: int
    detail: str
    reason: str


def backend_url() -> str:
    """The main backend's base URL: AUTOBOT_BACKEND_URL, else the identity-authority base (#10197, #10263)."""
    return node_proxy.resolve_node_url(settings.authority_base_url)


async def call_main_backend(
    method: str,
    api_path: str,
    *,
    content: Optional[bytes] = None,
    content_type: Optional[str] = None,
    params: Optional[Mapping[str, Any]] = None,
    service: str = "Main backend",
) -> httpx.Response:
    """One request to ``<backend>/api/<api_path>`` with the internal key; raises MainBackendUnavailable.

    A missing key or URL is a configuration fault (503), a transport failure is the shared client's
    classification (#14886). Any HTTP answer, including an error status, is returned to the caller.
    """
    if not node_proxy.internal_api_key():
        logger.error("AUTOBOT_INTERNAL_API_KEY not configured — %s proxy unavailable", service.lower())
        raise MainBackendUnavailable(
            503, f"{service} service not configured (missing internal API key)", node_proxy.REASON_KEY_NOT_CONFIGURED
        )
    base = backend_url()
    if not base:
        raise MainBackendUnavailable(503, f"{service} service not configured", node_proxy.REASON_URL_NOT_CONFIGURED)
    url = f"{base.rstrip('/')}/api/{api_path.lstrip('/')}"
    try:
        async with node_proxy.node_client() as client:
            response = await client.request(
                method, url, content=content, params=params, headers=node_proxy.internal_headers(content_type)
            )
    except httpx.HTTPError as exc:
        failure = node_proxy.classify_transport_error(exc)
        logger.error("Cannot reach main backend at %s (%s)", base, failure.reason)
        raise MainBackendUnavailable(failure.status_code, failure.detail, failure.reason) from exc
    if response.status_code == 401:
        # #20750: the backend refused the SLM's internal key -- one finding the admin sees, the same
        # whichever proxy met it. The answer still goes back to the caller unchanged.
        await report_backend_refused_internal_key(f"/api/{api_path.lstrip('/')}")
    return response


async def forward_to_main_backend(request: Request, api_path: str, service: str) -> Response:
    """Pass *request* through to ``/api/<api_path>`` unchanged and return the backend's answer as-is."""
    try:
        response = await call_main_backend(
            request.method,
            api_path,
            content=await request.body(),
            content_type=request.headers.get("Content-Type", "application/json"),
            service=service,
        )
    except MainBackendUnavailable as unavailable:
        raise HTTPException(status_code=unavailable.status_code, detail=unavailable.detail) from unavailable
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
    )
