# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Async HTTP client base for the AutoBot SDK."""

from __future__ import annotations

import os
from typing import Any

import httpx

from .models import DataResponse

_DEFAULT_BASE_URL = "http://localhost:8000"
_TOKEN_ENV = "AUTOBOT_API_TOKEN"


class AutoBotClient:
    """Async client for the AutoBot REST API.

    Usage::

        async with AutoBotClient() as client:
            result = await client.get("/chat/sessions")
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = (base_url or os.environ.get("AUTOBOT_BASE_URL", _DEFAULT_BASE_URL)).rstrip("/")
        self._token = token or os.environ.get(_TOKEN_ENV, "")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

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
        r = await self._ensure_open().get(path, params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()

    async def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        r = await self._ensure_open().post(path, json=body or {})
        r.raise_for_status()
        return r.json()

    async def put(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        r = await self._ensure_open().put(path, json=body or {})
        r.raise_for_status()
        return r.json()

    async def delete(self, path: str) -> dict[str, Any]:
        r = await self._ensure_open().delete(path)
        r.raise_for_status()
        return r.json()
