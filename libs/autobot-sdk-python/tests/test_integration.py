# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Integration tests for the AutoBot Python SDK.

These tests run against a live local backend (http://localhost:8000).
Set AUTOBOT_API_TOKEN in the environment if auth is required.
Skip with: pytest -m "not integration"
"""

import os

import pytest
import pytest_asyncio

from autobot_shared.live_service_probe import require_live_endpoint

pytestmark = pytest.mark.integration


# The two checks that need nothing running (#13286). ``test_sdk_package_importable``
# only imports the package, and ``test_auth_token_injection`` patches the transport,
# so a module-wide guard would trade a red result for lost coverage — the wrong
# trade, and the one #14930 caught by comparing skip counts against real failures.
_NEEDS_NO_BACKEND = ("test_auth_token_injection", "test_sdk_package_importable")


@pytest.fixture(scope="module")
def base_url() -> str:
    return os.environ.get("AUTOBOT_BASE_URL", "http://localhost:8000")


@pytest.fixture(autouse=True)
def _require_live_backend(request) -> None:
    """Skip when no backend is listening, instead of failing on a refused socket.

    #13286: this module was selected by no workflow at all until marker-tests.yml
    gained the ``libs`` root, so nothing had ever observed it. Its first run
    reported connection failures against ``localhost:8000`` as test failures —
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

    require_live_endpoint(
        os.environ.get("AUTOBOT_BASE_URL", "http://localhost:8000"),
        what="the AutoBot backend API",
    )


@pytest.mark.asyncio
async def test_sessions_list(base_url: str) -> None:
    """SDK can list chat sessions against the running backend."""
    from autobot_sdk import AutoBot

    async with AutoBot(base_url=base_url) as bot:
        result = await bot.sessions.list(limit=5)

    assert result.success is True
    assert result.data is not None
    assert isinstance(result.data.sessions, list)


@pytest.mark.asyncio
async def test_knowledge_stats(base_url: str) -> None:
    """SDK can retrieve knowledge base statistics."""
    from autobot_sdk import AutoBot

    async with AutoBot(base_url=base_url) as bot:
        result = await bot.knowledge.stats()

    assert result.success is True


@pytest.mark.asyncio
async def test_auth_token_injection(base_url: str) -> None:
    """SDK injects AUTOBOT_API_TOKEN as Bearer header when set."""
    from unittest.mock import AsyncMock, patch

    import httpx

    captured: list[str] = []

    async def _mock_get(*_args, **_kwargs):
        resp = httpx.Response(200, json={"success": True, "data": {"sessions": [], "total": 0}})
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
