# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared fake HTTPClientManager for tests that assert on outbound JSON
payloads without a real Browser VM (#11539).

Reused by test_browser_mcp_session_isolation.py and
test_playwright_session_isolation.py so both suites share one mock shape
instead of duplicating it (Rule 2: reuse, don't duplicate).
"""

from __future__ import annotations

import json
from types import SimpleNamespace


class FakeResponse:
    """Minimal async-context-manager stand-in for aiohttp.ClientResponse."""

    def __init__(self, status: int = 200, payload: dict | None = None):
        self.status = status
        self._payload = payload if payload is not None else {"success": True}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return json.dumps(self._payload)


def fake_http_client(recorder: list, payload: dict | None = None) -> SimpleNamespace:
    """Build a fake HTTPClientManager whose .get()/.post() record every call."""

    async def _post(url, json: dict | None = None, **kwargs):  # noqa: A002 - match call signature
        recorder.append({"method": "POST", "url": url, "payload": json, "kwargs": kwargs})
        return FakeResponse(payload=payload)

    async def _get(url, **kwargs):
        recorder.append({"method": "GET", "url": url, "payload": kwargs.get("params"), "kwargs": kwargs})
        return FakeResponse(payload=payload)

    return SimpleNamespace(post=_post, get=_get)
