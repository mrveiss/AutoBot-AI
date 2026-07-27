# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /web-research/status must never hang (#12751).

The endpoint awaited integration.health_check() and get_cache_stats() with no
bound. Its `except Exception` catches failures but cannot catch a HANG, so a
stalled dependency took the endpoint with it — callers (UI health panels,
monitoring) blocked instead of receiving a clear degraded signal, which is
strictly worse than an error response.

Probes are now bounded by the same HEALTH_PROBE_TIMEOUT_S the health aggregator
uses, so the two cannot disagree about what "too slow" means.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _request_with(integration):
    req = MagicMock()
    req.app.state.web_researcher = integration
    return req


def _integration(health=None, cache=None, hang: bool = False):
    async def _hang(*_a, **_k):
        await asyncio.sleep(3600)

    return SimpleNamespace(
        health_check=_hang if hang else AsyncMock(return_value=health or {"enabled": True}),
        get_circuit_breaker_status=MagicMock(return_value={}),
        get_cache_stats=_hang if hang else AsyncMock(return_value=cache or {}),
    )


class TestStatusIsBounded:
    @pytest.mark.asyncio
    async def test_hanging_dependency_returns_degraded_not_a_hang(self, monkeypatch):
        """The whole point: a stalled probe must degrade, not block the caller."""
        import api.web_research_settings as mod

        monkeypatch.setattr(mod, "HEALTH_PROBE_TIMEOUT_S", 0.05)
        monkeypatch.setattr(mod, "_require_web_researcher", lambda request: _integration(hang=True))

        resp = await asyncio.wait_for(mod.get_research_status(_request_with(None)), timeout=5.0)

        body = json.loads(resp.body)
        assert body["status"] == "degraded"
        assert body["enabled"] is False
        assert "timed out" in body["error"]

    @pytest.mark.asyncio
    async def test_healthy_dependency_still_returns_success(self, monkeypatch):
        """Bounding must not change the happy path."""
        import api.web_research_settings as mod

        monkeypatch.setattr(
            mod,
            "_require_web_researcher",
            lambda request: _integration(health={"enabled": True}, cache={"hits": 1}),
        )

        resp = await mod.get_research_status(_request_with(None))
        body = json.loads(resp.body)
        assert body["status"] == "success"
        assert body["enabled"] is True

    def test_shares_the_aggregator_timeout_budget(self):
        """One source of truth — a divergent local constant would let the
        aggregator and this endpoint disagree about 'too slow'."""
        from api.system_health import _PROBE_TIMEOUT_S, HEALTH_PROBE_TIMEOUT_S
        from api.web_research_settings import HEALTH_PROBE_TIMEOUT_S as endpoint_budget

        assert HEALTH_PROBE_TIMEOUT_S == _PROBE_TIMEOUT_S
        assert endpoint_budget == _PROBE_TIMEOUT_S
