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
