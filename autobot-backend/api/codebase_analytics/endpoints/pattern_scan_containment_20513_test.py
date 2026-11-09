# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A ``/patterns/*`` scan stays inside its source, at queue time and again when it runs (#20513).

These use the real ``scan_path_in_source`` helper -- a test that mocks it cannot see a
containment regression -- and only stand in for the source registry lookup.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.codebase_analytics.endpoints import pattern_analysis as pa
from api.codebase_analytics.endpoints import shared


@pytest.fixture
def source_tree(tmp_path):
    root = tmp_path / "checkout"
    (root / "pkg").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with patch.object(shared, "resolve_source_root", AsyncMock(return_value=root)):
        yield root, outside


async def _enqueue(path):
    delay = MagicMock()
    delay.return_value.id = "task-1"
    request = pa.PatternAnalysisRequest(source_id="s1", path=path)
    with (
        patch.object(pa.run_pattern_analysis, "delay", delay),
        patch.object(pa, "store_latest_task_id", AsyncMock()),
        patch.object(shared, "authorize_source_access", AsyncMock()),
        patch.object(pa, "get_current_user", AsyncMock(return_value={"id": "u"})),
    ):
        await pa.start_pattern_analysis(request, object())
    return delay


async def test_a_subdirectory_of_the_source_is_queued_by_its_real_path(source_tree):
    root, _ = source_tree
    delay = await _enqueue("pkg")
    assert delay.call_args.args[0]["path"] == str(root / "pkg")


@pytest.mark.parametrize("bad", ["/etc", "../outside", "pkg/../../outside", "link"])
async def test_a_path_outside_the_source_is_refused_and_nothing_is_queued(source_tree, bad):
    delay = MagicMock()
    with pytest.raises(HTTPException) as exc:
        delay = await _enqueue(bad)
    assert exc.value.status_code == 400
    delay.assert_not_called()


async def test_the_worker_rejects_a_directory_swapped_for_a_link_after_queueing(source_tree):
    root, outside = source_tree
    queued = str(root / "pkg")
    assert await shared.confirm_scan_dir_in_source("s1", queued) == str(root / "pkg")
    (root / "pkg").rmdir()
    (root / "pkg").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        await shared.confirm_scan_dir_in_source("s1", queued)


async def test_a_clone_path_without_a_directory_is_no_checkout(tmp_path):
    with patch.object(shared, "resolve_source_root", AsyncMock(return_value=tmp_path / "missing")):
        with pytest.raises(shared.UnresolvedSourceError):
            await shared.resolve_scan_root("s1")
