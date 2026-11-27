# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Technical-debt data belongs to ONE source and is never served for another (#22198)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from api import analytics_debt as mod
from api import analytics_debt_store as store
from api.codebase_analytics.endpoints.shared import UnresolvedSourceError


class _Pipe:
    def __init__(self, redis):
        self._redis, self._keys = redis, []

    def get(self, key):
        self._keys.append(key)

    def execute(self):
        return [self._redis.data.get(k) for k in self._keys]


class _FakeRedis:
    """The few Redis calls the debt store makes, over a dict."""

    def __init__(self):
        self.data: dict[str, str] = {}

    def set(self, key, value, ex=None):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)

    def scan_iter(self, match):
        prefix = match.rstrip("*")
        return [k for k in list(self.data) if k.startswith(prefix)]

    def pipeline(self):
        return _Pipe(self)


def _result(total_items: int) -> dict:
    return {
        "timestamp": f"2026-11-28T10:00:0{total_items}+00:00",
        "summary": {"total_items": total_items, "total_hours": 1.0, "total_cost_usd": 75.0},
        "top_files": [],
        "roi_ranking": [],
        "items": [],
    }


@pytest.fixture
def fake_redis():
    redis = _FakeRedis()
    with (
        patch.object(store, "get_debt_redis", return_value=redis),
        patch.object(mod, "resolve_scan_root", new=AsyncMock(return_value="/checkout")),
    ):
        yield redis


def _body(response) -> dict:
    return json.loads(response.body)


@pytest.mark.asyncio
async def test_summary_of_one_source_is_never_returned_for_another(fake_redis):
    store.store_debt_result(_result(7), "src-a")
    a = _body(await mod.get_debt_summary(source_id="src-a", admin_check=True))
    b = _body(await mod.get_debt_summary(source_id="src-b", admin_check=True))
    assert a["summary"]["total_items"] == 7
    assert b["status"] == "no_data" and b["summary"] == {}


@pytest.mark.asyncio
async def test_trends_of_one_source_never_include_another(fake_redis):
    store.store_debt_result(_result(7), "src-a")
    a = _body(await mod.get_debt_trends(source_id="src-a", days=30, admin_check=True))
    b = _body(await mod.get_debt_trends(source_id="src-b", days=30, admin_check=True))
    assert a["data_points"] == 1
    assert b["data_points"] == 0 and b["trends"] == []


@pytest.mark.asyncio
async def test_report_of_one_source_is_never_returned_for_another(fake_redis):
    store.store_debt_result(_result(7), "src-a")
    a = _body(await mod.get_debt_report(source_id="src-a", format="json", admin_check=True))
    b = _body(await mod.get_debt_report(source_id="src-b", format="json", admin_check=True))
    assert a["data"]["summary"]["total_items"] == 7
    assert b["status"] == "no_data"


@pytest.mark.asyncio
async def test_no_global_debt_key_is_read_or_written(fake_redis):
    fake_redis.data["debt:latest"] = "debt:calculation:20260101_000000"
    fake_redis.data["debt:calculation:20260101_000000"] = json.dumps(_result(9))
    store.store_debt_result(_result(7), "src-a")
    assert store.get_latest_debt_data("src-b") is None
    assert store.get_debt_trend_data("src-b") == []
    assert len(store.get_debt_trend_data("src-a")) == 1  # the orphaned global calculation is not counted
    written = set(fake_redis.data) - {"debt:latest", "debt:calculation:20260101_000000"}
    assert written and all(k.startswith("debt:source_id:src-a:") for k in written)


@pytest.mark.parametrize("bad", ["", "*", "a:b", "a/b"])
def test_the_store_refuses_an_unscoped_or_malformed_source(bad):
    with pytest.raises(ValueError):
        store.debt_prefix(bad)


@pytest.mark.asyncio
async def test_an_unresolvable_source_is_a_404_and_never_the_install_tree(fake_redis):
    with patch.object(mod, "resolve_scan_root", new=AsyncMock(side_effect=UnresolvedSourceError("src-x"))):
        with pytest.raises(UnresolvedSourceError):
            await mod.get_debt_summary(source_id="src-x", admin_check=True)


@pytest.mark.asyncio
async def test_calculate_stores_under_the_requesting_source_only(fake_redis):
    import api.codebase_analytics as ca

    request = mod.DebtCalculationRequest()
    with (
        patch.object(ca, "get_code_collection", return_value=None),
        patch.object(ca, "get_redis_connection", new=AsyncMock(return_value=None)),
    ):
        response = await mod.calculate_technical_debt(request, source_id="src-a", admin_check=True)
    assert _body(response)["status"] == "success"
    assert fake_redis.data and all(k.startswith("debt:source_id:src-a:") for k in fake_redis.data)
