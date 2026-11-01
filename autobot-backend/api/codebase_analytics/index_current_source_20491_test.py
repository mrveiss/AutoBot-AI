# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""/index/current says which source its job belongs to, so a page can refuse another's (#20491)."""

import asyncio
import json
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
    body = json.loads((await indexing.get_current_indexing_job()).body)
    assert body["source_id"] == "atlas"
    assert body["has_active_job"] is not finished


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
