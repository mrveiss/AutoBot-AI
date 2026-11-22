# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bug prediction reads only the selected source's clone (#18030, #20513).

The routes took ``path="."`` and scanned the server's working directory whatever source the page
had selected. Each test names one way that could come back.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import analytics_bug_prediction as mod
from api.analytics_bug_prediction_cache import cache_key_for
from api.analytics_bug_prediction_scope import scan_root, scoped_key
from api.codebase_analytics.endpoints import shared
from api.source_scope import source_scoped_prefix

#: Routes that are not about one source: a task id, the static factor list, the stuck-task reset.
_NOT_SOURCE_SCOPED = {
    "/bug-prediction/status/{task_id}",
    "/bug-prediction/factors",
    "/bug-prediction/tasks/clear-stuck",
}


def _routes():
    return [r for r in mod.router.routes if getattr(r, "dependant", None) and r.path not in _NOT_SOURCE_SCOPED]


def test_every_source_scoped_route_requires_source_id_and_takes_no_path():
    routes = _routes()
    assert len(routes) >= 9  # a walk that finds fewer has stopped seeing the routes
    for route in routes:
        query = {q.name: q for q in route.dependant.query_params}
        assert "source_id" in query and query["source_id"].field_info.is_required(), route.path
        assert "path" not in query, route.path


@pytest.fixture
def clone(tmp_path):
    root = tmp_path / "clone"
    root.mkdir()
    (root / "a.py").write_text("def f():\n    if True:\n        return 1\n", encoding="utf-8")
    (tmp_path / "outside.py").write_text("x = 1\n", encoding="utf-8")
    return root


@pytest.fixture
def registered(clone):
    with patch.object(shared, "resolve_source_root", AsyncMock(return_value=clone)):
        yield clone


@pytest.mark.asyncio
async def test_a_scan_reports_only_files_under_the_clone(registered):
    with patch.object(mod, "_safe_store_prediction_history", AsyncMock()):
        result = await mod._run_bug_analysis("src-1", "*.py", 100)
    assert [f["file_path"] for f in result["files"]] == ["a.py"]


@pytest.mark.asyncio
async def test_git_history_is_read_in_the_clone_not_the_working_directory(registered):
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(b"", b""))
    proc.returncode = 0
    with patch.object(mod, "start_git", AsyncMock(return_value=proc)) as start:
        await mod.get_git_bug_history(registered)
        await mod.get_file_change_frequency(registered)
    assert [call.kwargs["cwd"] for call in start.await_args_list] == [
        registered,
        registered,
    ]


@pytest.mark.asyncio
async def test_an_unresolvable_source_is_a_404_not_a_scan_of_the_install():
    with patch.object(shared, "resolve_source_root", AsyncMock(return_value=None)):
        with pytest.raises(shared.UnresolvedSourceError):
            await scan_root("missing")


@pytest.mark.asyncio
async def test_a_missing_clone_directory_is_an_error(tmp_path):
    with patch.object(shared, "resolve_source_root", AsyncMock(return_value=tmp_path / "gone")):
        with pytest.raises(shared.UnresolvedSourceError):
            await scan_root("src-1")


@pytest.mark.asyncio
async def test_the_file_route_refuses_a_path_outside_the_clone(registered):
    for escape in ("../outside.py", "/etc/hostname"):
        with pytest.raises(HTTPException) as err:
            await mod.get_file_risk(escape, source_id="src-1", admin_check=True)
        assert 400 <= err.value.status_code < 500


@pytest.mark.asyncio
async def test_the_file_route_scores_a_file_inside_the_clone(registered):
    with patch.object(mod, "_safe_store_prediction_history", AsyncMock()):
        body = await mod.get_file_risk("a.py", source_id="src-1", admin_check=True)
    assert body["status"] == "success" and body["file_path"] == "a.py"


def test_cache_and_history_keys_differ_per_source():
    assert cache_key_for("a", "*.py", 10) != cache_key_for("b", "*.py", 10)
    assert scoped_key(mod._PREDICTION_HISTORY_KEY, "a") != scoped_key(mod._PREDICTION_HISTORY_KEY, "b")
    with pytest.raises(ValueError):
        scoped_key(mod._PREDICTION_HISTORY_KEY, "")


# --- #22085 review: containment, isolation between sources, and the routes themselves ---------------------


def test_a_symlink_to_a_file_outside_the_clone_is_not_analysed(registered, tmp_path):
    (registered / "link.py").symlink_to(tmp_path / "outside.py")
    outside_dir = tmp_path / "elsewhere"
    outside_dir.mkdir()
    (outside_dir / "deep.py").write_text("y = 2\n", encoding="utf-8")
    (registered / "linked_dir").symlink_to(outside_dir, target_is_directory=True)

    found = [p.name for p in mod._find_files_sync(registered, "*.py", 100)]

    assert found == ["a.py"]


class _FakeRedis:
    """Just the commands the bug-prediction module uses, one dict per key."""

    def __init__(self):
        self.values, self.sorted, self.lists = {}, {}, {}

    def setex(self, key, _ttl, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def zadd(self, key, mapping):
        self.sorted.setdefault(key, {}).update(mapping)

    def zremrangebyrank(self, key, start, stop):
        pass

    def zrangebyscore(self, key, low, high):
        return [m for m, score in self.sorted.get(key, {}).items() if low <= score <= high]

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def ltrim(self, key, start, stop):
        pass


@pytest.fixture
def redis():
    fake = _FakeRedis()
    with (
        patch.object(mod, "get_redis_client", return_value=fake),
        patch("api.analytics_bug_prediction_cache.get_redis_client", return_value=fake),
        patch("autobot_shared.redis_client.get_redis_client", return_value=fake),
    ):
        yield fake


@pytest.mark.asyncio
async def test_source_a_cache_is_invisible_to_source_b(redis):
    await mod.set_cached_prediction("A", "*.py", 10, {"files": [1]})
    assert await mod.get_cached_prediction("A", "*.py", 10) == {"files": [1]}
    assert await mod.get_cached_prediction("B", "*.py", 10) is None


@pytest.mark.asyncio
async def test_source_a_history_is_invisible_to_source_b(redis):
    await mod._store_prediction_history("A", 1, 0, {"low": 1}, [{"risk_score": 5}])
    assert len(await mod._get_prediction_history(30, "A")) == 1
    assert await mod._get_prediction_history(30, "B") == []


@pytest.mark.asyncio
async def test_a_recorded_bug_lands_under_its_own_source_key(redis):
    await mod.record_bug(source_id="A", admin_check=True, file_path="a.py", description="d", severity="low")
    assert list(redis.lists) == [scoped_key("bug_prediction:recorded_bugs", "A")]
    assert scoped_key("bug_prediction:recorded_bugs", "B") not in redis.lists


@pytest.mark.asyncio
async def test_start_and_cached_use_the_per_source_task_pointer(registered):
    prefix = source_scoped_prefix(mod._REDIS_PREFIX, "A")
    task = MagicMock(id="t1")
    with (
        patch.object(mod, "store_latest_task_id", AsyncMock()) as store,
        patch.object(mod.run_bug_prediction_analysis, "delay", MagicMock(return_value=task)),
    ):
        await mod.start_bug_analysis(source_id="A", admin_check=True, include_pattern="*.py", limit=1)
    store.assert_awaited_once_with(prefix, "t1")
    with patch.object(mod, "get_latest_task_result", AsyncMock(return_value=None)) as read:
        await mod.get_cached_bug_prediction(source_id="A")
    read.assert_awaited_once_with(prefix)
    assert source_scoped_prefix(mod._REDIS_PREFIX, "B") != prefix


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from auth_middleware import check_admin_permission

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[check_admin_permission] = lambda: True
    app.dependency_overrides[shared.require_source_access] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("route", ["analyze", "cached", "high-risk", "heatmap", "trends", "summary", "file/a.py"])
def test_a_request_without_source_id_is_a_4xx_through_the_route(route):
    assert _client().get(f"/bug-prediction/{route}").status_code == 422


@pytest.mark.parametrize("route", ["analyze", "high-risk", "heatmap", "summary", "file/a.py"])
def test_a_source_with_no_checkout_is_a_404_through_the_route(route):
    with patch.object(shared, "resolve_source_root", AsyncMock(return_value=None)):
        response = _client().get(f"/bug-prediction/{route}", params={"source_id": "missing"})
    assert response.status_code == 404
