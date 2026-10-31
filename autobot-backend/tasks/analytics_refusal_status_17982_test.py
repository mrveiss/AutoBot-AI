# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A scan that refuses or examines nothing is not reported as `completed` (#17982, #18067).

Celery records a RETURNED value as SUCCESS whatever it says, so the three scan
tasks that return a refusal dict (`import_tree`, `duplicate`, `dependency`, all
through `_scan_root_or_refusal`) surfaced as `completed` / progress 100 /
`error: None`: "scanned nothing" and "scanned and found nothing" were the same
observable. The mapper is the one shared place, so it is fixed there and each
of the three is asserted, not only the one the report named.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from celery.result import AsyncResult
from fastapi import HTTPException

from api.codebase_analytics.endpoints.scan_responses import ScanTimedOut
from api.codebase_analytics.source_scope import cached_task_result
from utils.celery_task_status import celery_result_to_status

_REFUSAL = {"status": "error", "message": "source_id 'ghost' does not resolve to a code source; nothing scanned"}


@pytest.fixture(autouse=True)
def celery_eager():
    from celery_app import celery_app

    keys = ("task_always_eager", "task_eager_propagates", "task_store_eager_result")
    previous = {key: getattr(celery_app.conf, key, False) for key in keys}
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    celery_app.conf.task_store_eager_result = True
    yield
    for key, value in previous.items():
        setattr(celery_app.conf, key, value)
    cache = getattr(getattr(celery_app.backend, "client", None), "cache", None)
    if cache is not None:
        cache.clear()


async def _refuse(_source_id):
    return None, dict(_REFUSAL)


def _status_of(task, *args):
    return celery_result_to_status(AsyncResult(task.apply(args=args).id))


@pytest.mark.parametrize("name", ["run_import_tree_analysis", "run_duplicate_analysis", "run_dependency_analysis"])
def test_every_task_that_returns_a_refusal_reports_failed_with_the_reason(name):
    from tasks import analytics_tasks

    with patch.object(analytics_tasks, "_scan_root_or_refusal", _refuse):
        status = _status_of(getattr(analytics_tasks, name), "ghost")
    assert status["status"] == "failed", status
    assert status["error"] == _REFUSAL["message"], "the reason must reach the status endpoint"
    assert status["progress"] != 100.0


def test_a_real_result_is_still_completed():
    """Contrast: the fix must not turn every SUCCESS into a failure."""
    from tasks import analytics_tasks

    done = SimpleNamespace(files_analyzed=12)

    async def _root(_source_id):
        return "/somewhere", None

    async def _scan(*_a, **_k):
        return done

    with (
        patch.object(analytics_tasks, "_scan_root_or_refusal", _root),
        patch("api.codebase_analytics.endpoints.duplicates._run_duplicate_analysis", _scan),
        patch(
            "api.codebase_analytics.endpoints.duplicates._process_and_cache_analysis",
            lambda *_a, **_k: {"status": "success"},
        ),
    ):
        status = _status_of(analytics_tasks.run_duplicate_analysis, "src")
    assert status["status"] == "completed" and status["error"] is None


def test_a_scan_that_examined_zero_files_is_not_completed():
    from tasks import analytics_tasks

    async def _root(_source_id):
        return "/empty", None

    async def _scan(*_a, **_k):
        return SimpleNamespace(files_analyzed=0)

    with (
        patch.object(analytics_tasks, "_scan_root_or_refusal", _root),
        patch("api.codebase_analytics.endpoints.duplicates._run_duplicate_analysis", _scan),
    ):
        status = _status_of(analytics_tasks.run_duplicate_analysis, "src")
    assert status["status"] == "failed" and "nothing scanned" in status["error"]


def test_a_background_timeout_is_a_failure_not_a_completed_partial_result():
    from tasks import analytics_tasks

    async def _root(_source_id):
        return "/big", None

    async def _scan(*_a, **_k):
        raise ScanTimedOut(3600.0)

    with (
        patch.object(analytics_tasks, "_scan_root_or_refusal", _root),
        patch("api.codebase_analytics.endpoints.duplicates._run_duplicate_analysis", _scan),
    ):
        status = _status_of(analytics_tasks.run_duplicate_analysis, "src")
    assert status["status"] == "failed", status
    assert "3600" in status["error"]


@pytest.mark.asyncio
async def test_cached_does_not_answer_200_for_a_failed_scan():
    """A consumer that checks only the status code must not be able to render
    a refused scan as "no duplicates"."""

    async def _failed(_prefix):
        return {"error": "boom: internal detail", "completed_at": None}

    with patch("utils.celery_task_status.get_latest_task_result", _failed):
        with pytest.raises(HTTPException) as caught:
            await cached_task_result("dup_task:", "88831f3d")
    assert caught.value.status_code == 409
    assert caught.value.detail["status"] == "error"
    assert "internal detail" not in caught.value.detail["message"], "CWE-209: do not echo task exceptions"
