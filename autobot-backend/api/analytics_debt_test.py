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
from testkit.fake_redis_pipeline import FakePipeline


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
        return FakePipeline(self)


def _result(total_items: int) -> dict:
    return {
        "timestamp": f"2026-11-28T10:00:0{total_items}+00:00",
        "summary": {
            "total_items": total_items,
            "total_hours": 1.0,
            "total_cost_usd": 75.0,
        },
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
    with patch.object(
        mod,
        "resolve_scan_root",
        new=AsyncMock(side_effect=UnresolvedSourceError("src-x")),
    ):
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


# --- review (#22198): per-source access on top of the admin gate (#12358), as the evolution router does ---


def _private_source():
    from api.codebase_analytics.source_models import CodeSource, SourceAccess

    return CodeSource(
        name="proj",
        clone_path="/tmp/proj",
        owner_id="alice",
        access=SourceAccess.PRIVATE,
    )


def _debt_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from auth_middleware import check_admin_permission

    app = FastAPI()
    app.include_router(mod.router)  # require_source_access is NOT overridden
    app.dependency_overrides[check_admin_permission] = lambda: True
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("route", ["summary", "by-category/code_smell", "roi-priorities", "trends", "report"])
def test_a_foreign_private_source_is_a_404_on_every_debt_read(route):
    with (
        patch(
            "auth_middleware.get_current_user",
            AsyncMock(return_value={"id": "mallory"}),
        ),
        patch(
            "api.codebase_analytics.source_storage.get_source",
            AsyncMock(return_value=_private_source()),
        ),
    ):
        assert _debt_client().get(f"/{route}", params={"source_id": "b"}).status_code == 404


def test_a_foreign_private_source_cannot_be_calculated_either():
    with (
        patch(
            "auth_middleware.get_current_user",
            AsyncMock(return_value={"id": "mallory"}),
        ),
        patch(
            "api.codebase_analytics.source_storage.get_source",
            AsyncMock(return_value=_private_source()),
        ),
    ):
        assert _debt_client().post("/calculate", params={"source_id": "b"}, json={}).status_code == 404


def test_the_debt_router_carries_the_source_access_dependency():
    from api.codebase_analytics.endpoints.shared import require_source_access

    assert any(d.dependency is require_source_access for d in mod.router.dependencies)
