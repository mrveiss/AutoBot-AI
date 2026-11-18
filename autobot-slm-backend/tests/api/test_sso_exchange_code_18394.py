# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SSO callbacks must never put a session token in the URL (#18394).

Guard: every RedirectResponse built in api/sso_auth.py is checked for a
`token=` query. One-time code store: single use, expiry, unknown code.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_SVC_PY = Path(__file__).resolve().parents[2] / "services" / "sso_exchange_code.py"
_spec = importlib.util.spec_from_file_location("sso_exchange_code_under_test", _SVC_PY)
svc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(svc)

_SSO_AUTH = Path(__file__).resolve().parents[2] / "api" / "sso_auth.py"
_TOKEN_QUERY = re.compile(r"[?&]token=")


def _redirect_url_literals(source: str) -> list[str]:
    """Static text of every `url=` passed to a RedirectResponse call."""
    urls = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "RedirectResponse":
            for kw in node.keywords:
                if kw.arg == "url":
                    urls.append(ast.unparse(kw.value))
    return urls


def test_no_sso_redirect_url_carries_a_token_query():
    urls = _redirect_url_literals(_SSO_AUTH.read_text(encoding="utf-8"))
    assert urls, "detector found no RedirectResponse - the guard would be vacuous"
    assert not [u for u in urls if _TOKEN_QUERY.search(u)]


def test_guard_detects_the_pre_18394_redirect():
    old = 'return RedirectResponse(url=f"/?token={token_response.access_token}", status_code=302)'
    urls = _redirect_url_literals(old)
    assert urls and _TOKEN_QUERY.search(urls[0])


class _FakeRedis:
    """In-memory async Redis with TTL support and atomic GETDEL."""

    def __init__(self):
        self.data: dict[str, tuple[str, int]] = {}
        self.now = 0

    async def set(self, key, value, ex=None):
        self.data[key] = (value, self.now + (ex or 10**9))

    async def getdel(self, key):
        item = self.data.pop(key, None)
        if item is None or item[1] <= self.now:
            return None
        return item[0]


@pytest.fixture
def redis():
    fake = _FakeRedis()
    with patch.object(svc, "get_redis_client", return_value=fake):
        yield fake


def _token() -> dict:
    return {"access_token": "jwt-abc", "token": "jwt-abc", "token_type": "bearer", "expires_in": 3600}


def test_code_is_opaque_and_single_use(redis):
    async def run():
        code = await svc.issue_exchange_code(_token())
        assert "jwt-abc" not in code
        first = await svc.consume_exchange_code(code)
        second = await svc.consume_exchange_code(code)
        return first, second

    first, second = asyncio.run(run())
    assert first["access_token"] == "jwt-abc"
    assert second is None


def test_code_expires(redis):
    async def run():
        code = await svc.issue_exchange_code(_token())
        redis.now += svc.SSO_CODE_TTL_SECONDS + 1
        return await svc.consume_exchange_code(code)

    assert asyncio.run(run()) is None


def test_ttl_is_set_on_store(redis):
    asyncio.run(svc.issue_exchange_code(_token()))
    ((value, expiry),) = redis.data.values()
    assert expiry == svc.SSO_CODE_TTL_SECONDS
    assert json.loads(value)["access_token"] == "jwt-abc"


def test_unknown_code_returns_none(redis):
    assert asyncio.run(svc.consume_exchange_code("nope")) is None


def test_redis_down_fails_closed():
    with patch.object(svc, "get_redis_client", return_value=None):
        with pytest.raises(svc.ExchangeCodeUnavailableError):
            asyncio.run(svc.issue_exchange_code(_token()))


def test_exchange_endpoint_unknown_or_used_code_is_4xx():
    helper_spec = importlib.util.spec_from_file_location(
        "sso_auth_test_helpers_18394", Path(__file__).with_name("test_sso_auth.py")
    )
    helpers = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helpers)
    sso_auth, http_exc = helpers._load_sso_auth_with_real_endpoints()
    response = type("R", (), {"headers": {}})()
    with patch.object(sso_auth, "consume_exchange_code", new=AsyncMock(return_value=None)):
        with pytest.raises(http_exc) as exc:
            asyncio.run(sso_auth.exchange_sso_code(response, code="unknown"))
    assert exc.value.status_code == 400
    assert response.headers["Cache-Control"] == "no-store"
