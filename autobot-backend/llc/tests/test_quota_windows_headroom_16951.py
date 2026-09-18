# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /costs/quota-windows reports real observed headroom, not a placeholder (#16951).

Before this, the route's own docstring said actual headroom values were
"populated by the quota monitor (phase 3)" and it returned only the static
window-structure map — even though ``QuotaHeadroomStore`` (#15026) already
records real provider-reported readings off every LLM call. Nothing read them.

Two behaviours matter, and each gets its own test: a provider with a real
recorded reading reports it, and a provider with none reports an empty
``headroom`` list and an honest note — never a fabricated zero, which is
exactly the distinction ``QuotaHeadroomStore.get``'s own docstring draws
between "no signal received yet" and "confirmed zero remaining".
"""

import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api import costs
from llm_shared.quota_headroom import QuotaHeadroomEntry
from user_management.services import TenantContext

_ORG_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(costs.router, prefix="/api/llc/costs")
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER_ID), "user_id": str(_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=_ORG_ID, user_id=_USER_ID, is_platform_admin=False
    )
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_a_recorded_reading_is_returned_for_its_window():
    tier_svc = MagicMock()
    tier_svc.get_tier_map.return_value = {"anthropic": {"fast": "claude-haiku"}}

    reading = QuotaHeadroomEntry(
        provider="anthropic",
        window="5h_output_tokens",
        account_id="default",
        limit=1_000_000.0,
        remaining=250_000.0,
        resets_at=time.time() + 3600,
        observed_at=time.time(),
        source="anthropic-ratelimit-output-tokens-remaining",
    )
    store = MagicMock()
    store.all_entries = AsyncMock(return_value=[reading])

    with (
        patch.object(costs, "get_model_tier_service", return_value=tier_svc),
        patch.object(costs, "get_quota_headroom_store", return_value=store),
    ):
        async with _client(_app()) as client:
            resp = await client.get("/api/llc/costs/quota-windows")

    assert resp.status_code == 200
    body = resp.json()
    entry = next(w for w in body if w["provider"] == "anthropic")
    assert entry["headroom"] == [
        {
            "window": "5h_output_tokens",
            "limit": 1_000_000.0,
            "remaining": 250_000.0,
            "utilization": pytest.approx(0.75),
            "resets_at": reading.resets_at,
            "observed_at": reading.observed_at,
            "source": "anthropic-ratelimit-output-tokens-remaining",
        }
    ]
    assert "Live headroom" in entry["note"]
    store.all_entries.assert_awaited_with(provider="anthropic")


@pytest.mark.asyncio
async def test_no_reading_reports_empty_headroom_not_a_fabricated_zero():
    tier_svc = MagicMock()
    tier_svc.get_tier_map.return_value = {"openai": {"fast": "gpt-5-mini"}}

    store = MagicMock()
    store.all_entries = AsyncMock(return_value=[])

    with (
        patch.object(costs, "get_model_tier_service", return_value=tier_svc),
        patch.object(costs, "get_quota_headroom_store", return_value=store),
    ):
        async with _client(_app()) as client:
            resp = await client.get("/api/llc/costs/quota-windows")

    assert resp.status_code == 200
    body = resp.json()
    entry = next(w for w in body if w["provider"] == "openai")
    assert entry["headroom"] == []
    assert "No headroom observed yet" in entry["note"]
