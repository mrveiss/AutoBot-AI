# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Async HTTP client base for the AutoBot SDK."""

from __future__ import annotations

import os
from typing import Any

import httpx

# Every core and optional router is mounted by the backend's application factory
# at ``/api{registry_prefix}`` — a single loop, no exceptions (#15053). The only
# mounts that are NOT under ``/api`` are the OpenAI/Anthropic compatibility
# routers at ``/v1`` and the JWKS document at ``/.well-known``, and this SDK
# exposes neither. So the prefix is a property of the whole surface and belongs
# here, applied once, rather than repeated on fifteen resource paths where a
# single omission is invisible until it 404s.
API_PREFIX = "/api"

# The SDK ships as a standalone wheel (httpx + pydantic only) and cannot import
# the platform's ``autobot_shared.ssot_config``. It reads the SAME environment
# aliases that configuration declares, with the same defaults, so an installed
# SDK agrees with the deployment it points at. ``repo_tests`` binds these to
# ``config.port.backend`` so drift in either direction fails in CI.
_HOST_ENV = "AUTOBOT_BACKEND_HOST"
_PORT_ENV = "AUTOBOT_BACKEND_PORT"
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = "8001"
_BASE_URL_ENV = "AUTOBOT_BASE_URL"
_TOKEN_ENV = "AUTOBOT_API_TOKEN"


def default_base_url() -> str:
    """Origin of the AutoBot backend, from the environment.

    ``AUTOBOT_BASE_URL`` wins outright; otherwise the origin is composed from
    the backend host and port aliases. The port default is the backend's, not
    the Service Lifecycle Manager's — pointing the SDK at the SLM answers every
    AutoBot route with a 404 (#15053).
    """
    explicit = os.environ.get(_BASE_URL_ENV, "")
    if explicit:
        return explicit
    host = os.environ.get(_HOST_ENV) or _DEFAULT_HOST
    port = os.environ.get(_PORT_ENV) or _DEFAULT_PORT
    return f"http://{host}:{port}"


def api_path(path: str) -> str:
    """Place a resource path under the backend's API root.

    ``/chat/sessions`` -> ``/api/chat/sessions``. Idempotent, so a caller that
    already spelled the prefix is not double-prefixed.
    """
    normalised = "/" + path.lstrip("/")
    if normalised == API_PREFIX or normalised.startswith(f"{API_PREFIX}/"):
        return normalised
    return f"{API_PREFIX}{normalised}"


class AutoBotClient:
    """Async client for the AutoBot REST API.

    Usage::

        async with AutoBotClient() as client:
            result = await client.get("/chat/sessions")

    Resource paths are written without the ``/api`` root; :func:`api_path`
    adds it on every request.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = (base_url or default_base_url()).rstrip("/")
        self._token = token or os.environ.get(_TOKEN_ENV, "")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def base_url(self) -> str:
        """Backend origin this client dials, without the ``/api`` root."""
        return self._base_url

    @property
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def __aenter__(self) -> "AutoBotClient":
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _ensure_open(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Use AutoBotClient as an async context manager")
        return self._client

    async def get(self, path: str, **params: Any) -> dict[str, Any]:
        query = {k: v for k, v in params.items() if v is not None}
        r = await self._ensure_open().get(api_path(path), params=query)
        r.raise_for_status()
        return r.json()

    async def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        r = await self._ensure_open().post(api_path(path), json=body or {})
        r.raise_for_status()
        return r.json()

    async def put(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        r = await self._ensure_open().put(api_path(path), json=body or {})
        r.raise_for_status()
        return r.json()

    async def delete(self, path: str) -> dict[str, Any]:
        r = await self._ensure_open().delete(api_path(path))
        r.raise_for_status()
        return r.json()
