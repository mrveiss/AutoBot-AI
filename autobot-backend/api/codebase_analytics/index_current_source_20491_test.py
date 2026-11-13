# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""/index/current says which source its job belongs to, so a page can refuse another's (#20491)."""

import asyncio
import json
from collections import deque
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.codebase_analytics import subprocess_runner
from api.codebase_analytics.endpoints import indexing


@pytest.mark.asyncio
@pytest.mark.parametrize("finished", [False, True])
async def test_the_current_job_names_its_source(monkeypatch, finished):
    task = MagicMock()
    task.done.return_value = finished
    monkeypatch.setattr(indexing, "_current_indexing_task_id", "t1")
    monkeypatch.setattr(indexing, "_active_tasks", {"t1": task})
    monkeypatch.setattr(indexing, "_load_task_from_redis", AsyncMock(return_value={"source_id": "atlas"}))
    body = json.loads((await indexing.get_current_indexing_job(source_id="atlas")).body)
    assert body["source_id"] == "atlas"
    assert body["has_active_job"] is not finished


@pytest.mark.asyncio
@pytest.mark.parametrize("finished", [False, True])
async def test_another_sources_job_is_not_reported_for_this_source(monkeypatch, finished):
    """#20513: one job runs at a time across sources; a page asking about source B is told idle, not A's job."""
    task = MagicMock()
    task.done.return_value = finished
    monkeypatch.setattr(indexing, "_current_indexing_task_id", "t1")
    monkeypatch.setattr(indexing, "_active_tasks", {"t1": task})
    monkeypatch.setattr(
        indexing,
        "_load_task_from_redis",
        AsyncMock(return_value={"source_id": "atlas", "status": "running", "progress": {"current": 3}}),
    )
    body = json.loads((await indexing.get_current_indexing_job(source_id="borealis")).body)
    assert body["has_active_job"] is False
    assert body["task_id"] is None and body["status"] == "idle"
    assert "atlas" not in json.dumps(body)  # the other source's id is not disclosed
    own = json.loads((await indexing.get_current_indexing_job(source_id="atlas")).body)  # control
    assert own["task_id"] == "t1"


@pytest.mark.asyncio
async def test_no_job_at_all_is_idle_for_any_source(monkeypatch):
    monkeypatch.setattr(indexing, "_current_indexing_task_id", None)
    body = json.loads((await indexing.get_current_indexing_job(source_id="atlas")).body)
    assert (body["has_active_job"], body["status"]) == (False, "idle")


@pytest.mark.asyncio
async def test_a_job_whose_record_names_no_source_is_not_attributed_to_the_caller(monkeypatch):
    task = MagicMock()
    task.done.return_value = False
    monkeypatch.setattr(indexing, "_current_indexing_task_id", "t1")
    monkeypatch.setattr(indexing, "_active_tasks", {"t1": task})
    monkeypatch.setattr(indexing, "_load_task_from_redis", AsyncMock(return_value={"status": "running"}))
    monkeypatch.setitem(indexing.indexing_tasks, "t1", {"status": "running"})
    body = json.loads((await indexing.get_current_indexing_job(source_id="atlas")).body)
    assert body["has_active_job"] is False


def _arm_running_job(monkeypatch, running_source, queue):
    """Source B's job is running; ``queue`` holds the requests waiting behind it."""
    task = MagicMock()
    task.done.return_value = False
    monkeypatch.setattr(indexing, "_current_indexing_task_id", "t1")
    monkeypatch.setattr(indexing, "_active_tasks", {"t1": task})
    monkeypatch.setattr(indexing, "_index_queue", deque(queue))
    running = {"source_id": running_source, "status": "running", "progress": {"current": 3}}
    monkeypatch.setattr(indexing, "_load_task_from_redis", AsyncMock(return_value=running))


async def _poll(source_id):
    return json.loads((await indexing.get_current_indexing_job(source_id=source_id)).body)


@pytest.mark.asyncio
async def test_a_job_queued_behind_another_sources_job_is_seen_by_its_own_poll(monkeypatch):
    """#20513: A's request waits behind B's running job; A's page must keep waiting, not read ``idle``."""
    _arm_running_job(monkeypatch, "borealis", [{"source_id": "atlas", "root_path": "/a"}])
    queued = await _poll("atlas")
    assert (queued["has_active_job"], queued["status"], queued["source_id"]) == (True, "queued", "atlas")
    assert queued["task_id"] is None and queued["position"] == 1
    running = await _poll("borealis")  # B sees its own running job
    assert (running["has_active_job"], running["status"], running["task_id"]) == (True, "running", "t1")
    idle = await _poll("cirrus")  # C has nothing queued and nothing running
    assert (idle["has_active_job"], idle["status"]) == (False, "idle")


@pytest.mark.asyncio
async def test_position_counts_the_whole_queue_and_a_finished_current_job_still_shows_the_queue(monkeypatch):
    _arm_running_job(
        monkeypatch, "borealis", [{"source_id": "cirrus", "root_path": "/c"}, {"source_id": "atlas", "root_path": "/a"}]
    )
    assert (await _poll("atlas"))["position"] == 2
    indexing._active_tasks["t1"].done.return_value = True  # the running job just finished
    assert (await _poll("atlas"))["status"] == "queued"


@pytest.mark.asyncio
async def test_a_queued_request_is_seen_when_nothing_is_running(monkeypatch):
    monkeypatch.setattr(indexing, "_current_indexing_task_id", None)
    monkeypatch.setattr(indexing, "_index_queue", deque([{"source_id": "atlas", "root_path": "/a"}]))
    assert (await _poll("atlas"))["status"] == "queued"
    assert (await _poll("borealis"))["status"] == "idle"


@pytest.mark.asyncio
async def test_a_new_job_names_its_source_from_the_first_save(monkeypatch):
    tasks: dict = {}
    saved: list = []

    async def _save(task_id):
        saved.append(dict(tasks[task_id]))

    monkeypatch.setattr(
        subprocess_runner.asyncio, "create_subprocess_exec", AsyncMock(side_effect=RuntimeError("stop here"))
    )
    with pytest.raises(RuntimeError, match="stop here"):
        await subprocess_runner._run_indexing_subprocess(
            "t1", "/repo", tasks, asyncio.Lock(), lambda: {"status": "running"}, _save, MagicMock(), source_id="atlas"
        )
    assert saved[0]["source_id"] == "atlas"
