# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20483: a probe that only ran slow does not read as the whole system being down."""

from __future__ import annotations

import asyncio

from api import system_health
from api.system_health import ComponentHealth, _aggregate_status, _run_probe


async def _slow(_request) -> ComponentHealth:
    await asyncio.sleep(1)
    return ComponentHealth(name="slow", status="ok")


async def _raises(_request) -> ComponentHealth:
    raise RuntimeError("broken")


async def _reports_down(_request) -> ComponentHealth:
    return ComponentHealth(name="dead", status="down", detail="refused")


async def test_a_timeout_is_degraded_and_says_it_timed_out(monkeypatch) -> None:
    monkeypatch.setattr(system_health, "_PROBE_TIMEOUT_S", 0.01)
    result = await _run_probe("slow", _slow, None)
    assert result.status == "degraded" and "timed out" in result.detail
    assert _aggregate_status([result, ComponentHealth(name="ok", status="ok")]) == "degraded"


async def test_a_real_failure_still_reads_down() -> None:
    assert (await _run_probe("broken", _raises, None)).status == "down"
    result = await _run_probe("dead", _reports_down, None)
    assert result.status == "down" and _aggregate_status([result]) == "down"
