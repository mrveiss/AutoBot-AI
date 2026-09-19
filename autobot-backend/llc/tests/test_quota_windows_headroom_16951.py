# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /costs/quota-windows reports real observed headroom, not a placeholder (#16951).

Before this, the route's own docstring said actual headroom values were
"populated by the quota monitor (phase 3)" and it returned only the static
window-structure map — even though ``QuotaHeadroomStore`` (#15026) already
records real provider-reported readings off every LLM call. Nothing read them.

A first version of this fix filtered the shown readings to the provider's
static ``_PROVIDER_QUOTA_STRUCTURE`` window names (``rpm``, ``tpm``,
``5h_output_tokens``, ...) — which silently dropped exactly the data the
store's only production writer actually records: every 429 is persisted
under the generic window ``"requests"`` with ``remaining=0``
(``rate_limit_backoff.py``), a name that appears in none of those lists.
The mirror image of a fabricated zero: real data discarded because it did
not match an expected shape. ``test_a_recorded_reading_is_returned_for_its_window``
uses exactly that shape (``"requests"``, ``remaining=0``) as its fixture,
not a name that happens to already be on the static list, so a regression
back to filtering by ``windows`` fails it again.

Three behaviours matter, and each gets its own test: a provider with a real
recorded reading reports it even when its window name is outside the static
vocabulary; a ``remaining=0`` reading is real data and stays visible, never
collapsed into "no data" by a truthy check; and a provider with no reading at
all reports an empty ``headroom`` list and an honest note — never a
fabricated zero, which is exactly the distinction
``QuotaHeadroomStore.get``'s own docstring draws between "no signal received
yet" and "confirmed zero remaining".
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
    app.include_router(costs.router, prefix="/api/llc")
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER_ID), "user_id": str(_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=_ORG_ID, user_id=_USER_ID, is_platform_admin=False
    )
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_a_recorded_reading_is_returned_for_its_window():
    """Uses the REAL writer's exact shape — window="requests", remaining=0.

    Not "5h_output_tokens" (a name that happens to already be on anthropic's
    static window list): rate_limit_backoff.py's 429 handler is the only
    production writer this store has, and it always records under the
    generic window "requests", which is on no provider's static list. A
    reader that filters to that static list passes against a friendlier
    fixture and fails against what actually gets written — this fixture is
    what actually gets written.
    """
    tier_svc = MagicMock()
    tier_svc.get_tier_map.return_value = {"anthropic": {"fast": "claude-haiku"}}

    reading = QuotaHeadroomEntry(
        provider="anthropic",
        window="requests",
        account_id="default",
        limit=None,
        remaining=0.0,
        resets_at=time.time() + 3600,
        observed_at=time.time(),
        source="rate_limit_backoff:429",
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
    # "requests" is on none of anthropic's static windows (5h/7d output
    # tokens) — shown anyway, because it was actually recorded.
    assert "requests" not in entry["windows"]
    assert entry["headroom"] == [
        {
            "window": "requests",
            "limit": None,
            "remaining": 0.0,
            "utilization": None,
            "resets_at": reading.resets_at,
            "observed_at": reading.observed_at,
            "source": "rate_limit_backoff:429",
        }
    ]
    # remaining=0 is real, observed data — distinct from no reading at all
    # (test_no_reading_reports_empty_headroom_not_a_fabricated_zero below).
    # A falsy-value check (`if entry.remaining:`) would have collapsed this
    # into the empty case; asserting the list is non-empty pins that it does
    # not.
    assert len(entry["headroom"]) == 1
    assert entry["headroom"][0]["remaining"] == 0.0
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
