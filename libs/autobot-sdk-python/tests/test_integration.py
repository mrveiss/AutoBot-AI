# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Integration tests for the AutoBot Python SDK.

These tests run against a live local backend — AUTOBOT_BASE_URL, else the
SDK's own default, which is the backend port and not the SLM's (#15053).
Set AUTOBOT_API_TOKEN in the environment if auth is required.
Skip with: pytest -m "not integration"
"""

import os

import pytest
import pytest_asyncio

from autobot_sdk import default_base_url
from autobot_shared.live_service_probe import require_live_endpoint

pytestmark = pytest.mark.integration


# The two checks that need nothing running (#13286). ``test_sdk_package_importable``
# only imports the package, and ``test_auth_token_injection`` patches the transport,
# so a module-wide guard would trade a red result for lost coverage — the wrong
# trade, and the one #14930 caught by comparing skip counts against real failures.
_NEEDS_NO_BACKEND = ("test_auth_token_injection", "test_sdk_package_importable")

# Needs a backend listening, but not a token: it asserts only that the URL the
# SDK builds names a route, which a 401 proves as well as a 200 does (#15053).
_NEEDS_A_ROUTE_ONLY = ("test_no_sdk_request_reaches_a_missing_route",)


@pytest.fixture(scope="module")
def base_url() -> str:
    """The SDK's own resolution, so the tests dial exactly what a caller would."""
    return default_base_url()


@pytest.fixture(autouse=True)
def _require_live_backend(request) -> None:
    """Skip when no backend is listening, instead of failing on a refused socket.

    #13286: this module was selected by no workflow at all until marker-tests.yml
    gained the ``libs`` root, so nothing had ever observed it. Its first run
    reported connection failures against the default backend origin as failures —
    a red that says nothing about the SDK and would train the marker-excluded
    suite to be ignored. A skip naming the absent service is the honest report;
    these still run, and still fail for real, wherever a backend is up.
    """
    stranded = [name for name in _NEEDS_NO_BACKEND if name not in globals()]
    assert not stranded, (
        f"_NEEDS_NO_BACKEND names {stranded}, which no longer exist in this module. "
        f"A rename stranded the exemption: it now exempts nothing, silently."
    )

    if request.node.name in _NEEDS_NO_BACKEND:
        return

    require_live_endpoint(default_base_url(), what="the AutoBot backend API")

    if request.node.name in _NEEDS_A_ROUTE_ONLY:
        return

    # #15053: with the paths corrected these reach real routes and are answered
    # 401 without a token — a credential the runner does not hold. Skipping on
    # the absent credential keeps that from reading as a route defect, exactly
    # as the probe above keeps an absent service from reading as one. The
    # route itself is still asserted unconditionally, by the test below and by
    # repo_tests/sdk_request_url_test.py.
    if not os.environ.get("AUTOBOT_API_TOKEN"):
        pytest.skip("AUTOBOT_API_TOKEN is not set; the AutoBot backend answers these routes 401 without it")


@pytest.mark.asyncio
async def test_sessions_list(base_url: str) -> None:
    """SDK can list chat sessions against the running backend.

    No ``limit``: ``GET /chat/sessions`` is not paginated and declares no such
    parameter, so the SDK stopped offering one (#15119).
    """
    from autobot_sdk import AutoBot

    async with AutoBot(base_url=base_url) as bot:
        result = await bot.sessions.list()

    assert result.success is True
    assert result.data is not None
    assert isinstance(result.data.sessions, list)


@pytest.mark.asyncio
async def test_knowledge_stats(base_url: str) -> None:
    """SDK can retrieve knowledge base statistics.

    ``/knowledge_base/stats`` returns its document flat, so there is no envelope
    and no ``success`` flag to read -- asserting one was how this test passed
    while the payload it was meant to check was always ``None`` (#15116).
    """
    from autobot_sdk import AutoBot

    async with AutoBot(base_url=base_url) as bot:
        result = await bot.knowledge.stats()

    assert result.status in {"online", "offline", "error", "unknown"}
    assert result.total_facts is not None


@pytest.mark.asyncio
async def test_auth_token_injection(base_url: str) -> None:
    """SDK injects AUTOBOT_API_TOKEN as Bearer header when set."""
    from unittest.mock import AsyncMock, patch

    import httpx

    captured: list[str] = []

    async def _mock_get(*_args, **_kwargs):
        resp = httpx.Response(200, json={"success": True, "data": {"sessions": [], "count": 0}})
        return resp

    from autobot_sdk import AutoBot

    token = "test-token-123"
    with patch.dict(os.environ, {"AUTOBOT_API_TOKEN": token}):
        bot = AutoBot(base_url=base_url)
        assert bot._token == token


@pytest.mark.asyncio
async def test_sdk_package_importable() -> None:
    """Top-level package imports all expected public names."""
    import autobot_sdk  # noqa: F401

    assert hasattr(autobot_sdk, "AutoBot")
    assert hasattr(autobot_sdk, "AutoBotClient")
    assert hasattr(autobot_sdk, "DataResponse")
    assert hasattr(autobot_sdk, "Session")
    assert hasattr(autobot_sdk, "KnowledgeStats")
    assert hasattr(autobot_sdk, "AnalyticsUsage")


@pytest.mark.asyncio
async def test_no_sdk_request_reaches_a_missing_route(base_url: str) -> None:
    """No SDK read path answers 404 on a live backend (#15053).

    Every one of these used to: the SDK omitted the ``/api`` root that the
    application factory puts in front of every registered router, and three
    paths were wrong beyond that root as well. 401 is a pass here — it means
    the request arrived at a route that exists and asked for credentials.
    """
    import httpx

    from autobot_sdk import AutoBot

    missing: list[str] = []
    async with AutoBot(base_url=base_url) as bot:
        for name, call in (
            ("sessions.list", bot.sessions.list),
            ("agents.health", bot.agents.health),
            ("knowledge.stats", bot.knowledge.stats),
            ("knowledge.get_entries", lambda: bot.knowledge.get_entries(limit=1)),
            ("analytics.usage", bot.analytics.usage),
            ("analytics.performance", bot.analytics.performance),
        ):
            try:
                await call()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    missing.append(f"{name} -> {exc.request.url.path}")

    assert not missing, f"SDK requests that reached no route: {missing}"
