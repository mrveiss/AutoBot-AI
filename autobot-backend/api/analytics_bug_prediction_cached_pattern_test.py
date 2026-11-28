# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``/cached`` replies say they are cached, and ``include_pattern`` cannot leave the clone (#18030).

AC4: a stored result carries the scan's own ``from_cache: False``; the reply must not inherit it.
AC6: ``include_pattern`` reaches ``rglob``, so it is validated before it does.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api import analytics_bug_prediction as mod
from api.analytics_bug_prediction_scope_test import _client

_STORED = {
    "completed_at": "2026-01-01T00:00:00+00:00",
    "result": {"status": "success", "from_cache": False, "files": [], "total_files": 0},
}


async def _cached(last_synced):
    source = SimpleNamespace(last_synced=last_synced)
    with (
        patch("utils.celery_task_status.get_latest_task_result", AsyncMock(return_value=_STORED)),
        patch(
            "api.codebase_analytics.source_storage.get_source_or_none_if_unreadable",
            AsyncMock(return_value=source),
        ),
    ):
        return await mod.get_cached_bug_prediction(source_id="A")


@pytest.mark.asyncio
async def test_a_cached_reply_is_marked_from_cache_whatever_the_stored_payload_says():
    reply = await _cached(None)
    assert reply["from_cache"] is True
    assert reply["completed_at"] == _STORED["completed_at"]


@pytest.mark.asyncio
async def test_a_result_older_than_the_last_sync_is_flagged_stale_not_current():
    assert (await _cached("2026-02-01T00:00:00+00:00"))["stale"] is True
    assert (await _cached("2025-12-01T00:00:00+00:00"))["stale"] is False


@pytest.mark.parametrize(
    "pattern", ["/etc/*", "\\win/*.py", "C:/x/*.py", "../*.py", "a/../b/*.py", "a\x00b", "x" * 500]
)
def test_a_bad_include_pattern_is_422_at_the_route(pattern):
    response = _client().get("/bug-prediction/high-risk", params={"source_id": "A", "include_pattern": pattern})
    assert response.status_code == 422


@pytest.mark.parametrize("pattern", ["/etc/*", "../*.py", "a\x00b"])
def test_the_walk_refuses_a_bad_pattern_instead_of_swallowing_it(pattern, tmp_path: Path):
    with pytest.raises(ValueError):
        mod._find_files_sync(tmp_path, pattern, 10)


def test_a_relative_glob_still_walks(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert [p.name for p in mod._find_files_sync(tmp_path, "**/*.py", 10)] == ["a.py"]
