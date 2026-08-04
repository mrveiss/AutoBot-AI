# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /kb-stats must read the grounding hash with str keys (#13278).

``get_stats`` calls ``get_async_redis_client()`` and the shared async pool is
``decode_responses=True`` (``redis_management/connection_manager.py:500`` →
``redis_management/config.py:61,153``, no per-database override), so
``hgetall("grounding:stats")`` returns a ``str``-keyed dict.

The endpoint probed it with bytes literals::

    int(decode_val(stats_data.get(b"total_responses_grounded", b"0")))

which could never match. The defect was dormant rather than visible only because
nothing in the tree writes ``grounding:stats`` yet **and** the empty-hash
fallback immediately above was itself bytes-keyed — the bytes probes hit that
hand-built default, so the endpoint returned honest zeros by accident. The first
writer to land would have turned every field into a permanent silent 0.

``_populate`` below therefore writes through the canonical HINCRBY/HINCRBYFLOAT
value shape a real writer would use (decimal strings under ``str`` field names),
so that writer/reader key drift breaks this suite instead of the endpoint.
"""

import pytest

from api import knowledge_grounding

# A populated grounding hash exactly as a HINCRBY/HINCRBYFLOAT writer leaves it:
# str field names, decimal-string values, delivered decoded by the shared client.
LIVE_STATS = {
    "total_responses_grounded": "1543",
    "total_claims_extracted": "8204",
    "claims_verified": "0.87",
    "average_confidence": "0.89",
    "conflicts_created": "142",
    "conflicts_resolved": "128",
}


class _FakeAsyncRedis:
    """Minimal stand-in for the shared async client used by get_stats."""

    def __init__(self, fields, decoded=True):
        self._fields = dict(fields)
        self._decoded = decoded
        self.hgetall_called_with = None

    def _populate(self, field, amount):
        """Mirror HINCRBY/HINCRBYFLOAT: accumulate, persist as a decimal string."""
        current = self._fields.get(field, "0")
        total = float(current) + amount
        self._fields[field] = str(int(total)) if float(total).is_integer() else repr(total)

    async def hgetall(self, key):
        self.hgetall_called_with = key
        if self._decoded:
            return dict(self._fields)
        # Field names stay str; only the values arrive as bytes.
        return {k: v.encode() for k, v in self._fields.items()}


def _install(monkeypatch, fields, decoded=True):
    """get_stats imports the client factory inside the function body."""
    import autobot_shared.redis_client as rc

    fake = _FakeAsyncRedis(fields, decoded=decoded)

    async def _factory(*args, **kwargs):
        return fake

    monkeypatch.setattr(rc, "get_async_redis_client", _factory)
    return fake


async def _call(period="24h"):
    return await knowledge_grounding.get_stats(period=period, current_user="tester", req=None)


@pytest.mark.asyncio
async def test_populated_hash_reports_its_real_figures(monkeypatch):
    """The live configuration. Pre-fix every field read back 0."""
    fake = _install(monkeypatch, LIVE_STATS)

    result = await _call()

    assert fake.hgetall_called_with == "grounding:stats", "the stats hash was never read"
    assert result["status"] == "success"
    assert result["total_responses_grounded"] == 1543, "str field names were probed with bytes literals"
    assert result["total_claims_extracted"] == 8204
    assert result["claims_verified"] == pytest.approx(0.87)
    assert result["average_confidence"] == pytest.approx(0.89)
    assert result["conflicts_created"] == 142
    assert result["conflicts_resolved"] == 128


@pytest.mark.asyncio
async def test_incrementing_writer_shape_round_trips(monkeypatch):
    """Accumulate through the HINCRBY value shape, then read with the real reader."""
    fake = _install(monkeypatch, {})
    fake._populate("total_responses_grounded", 1)
    fake._populate("total_responses_grounded", 1)
    fake._populate("total_claims_extracted", 7)
    fake._populate("average_confidence", 0.5)

    result = await _call()

    assert result["total_responses_grounded"] == 2
    assert result["total_claims_extracted"] == 7
    assert result["average_confidence"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_bytes_values_still_work(monkeypatch):
    """decode_redis_value keeps a client without decode_responses working."""
    _install(monkeypatch, LIVE_STATS, decoded=False)

    result = await _call()

    assert result["total_responses_grounded"] == 1543
    assert result["claims_verified"] == pytest.approx(0.87)
    assert result["conflicts_resolved"] == 128


@pytest.mark.asyncio
async def test_empty_hash_reports_zeros(monkeypatch):
    """The empty-stats fallback is now str-keyed; it must still report zeros."""
    _install(monkeypatch, {})

    result = await _call()

    assert result["status"] == "success"
    assert result["total_responses_grounded"] == 0
    assert result["total_claims_extracted"] == 0
    assert result["claims_verified"] == 0.0
    assert result["average_confidence"] == 0.0
    assert result["conflicts_created"] == 0
    assert result["conflicts_resolved"] == 0


@pytest.mark.asyncio
async def test_static_claim_source_breakdown_is_unchanged(monkeypatch):
    """The hard-coded claim_sources block is out of scope for this fix."""
    _install(monkeypatch, LIVE_STATS)

    result = await _call()

    assert result["claim_sources"] == {
        "kb_lookup": 0.65,
        "external_research": 0.22,
        "causal_inference": 0.13,
    }
    assert result["period"] == "24h"
