# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21418: the ``/duplicates`` index fallback says when its findings come from an interrupted run.

When a live duplicate scan fails, ``_handle_detection_failure`` serves the duplicates the last
indexing run stored. Those are the same index findings the #21003 routes label, so the fallback
carries the same ``partial``/``run`` pair, read by the one ``run_response_fields`` before the
findings are read. The run record is the real one (``run_status``) over an in-memory store; only
the code collection the fallback reads is replaced.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.codebase_analytics import run_status
from api.codebase_analytics.endpoints import duplicate_results as results_mod
from api.codebase_analytics.endpoints import duplicates as dup_mod
from api.codebase_analytics.run_state_read_paths_21003_test import _killed_after_a_completed_run, _RunStore

_STORED_DUPLICATE = {"file1": "a.py", "file2": "b.py", "similarity": 91.0, "lines": 6, "code_snippet": "x = 1"}


@pytest.fixture
def run_store():
    store = _RunStore()
    with patch.object(run_status, "get_code_collection_async", AsyncMock(return_value=store)):
        yield store


@pytest.fixture
def stored_duplicates():
    """The index holds one duplicate for the source; the live scan is the part that failed."""
    with (
        patch.object(results_mod, "get_code_collection", return_value=MagicMock()),
        patch.object(results_mod, "get_all_paginated", return_value={"metadatas": [_STORED_DUPLICATE]}) as read,
    ):
        yield read


async def _fallback_body(source="src") -> dict:
    response = await dup_mod._handle_detection_failure(RuntimeError("live scan failed"), source_id=source)
    return json.loads(response.body)


@pytest.mark.asyncio
async def test_the_fallback_of_a_killed_run_is_labelled_partial_with_the_run(run_store, stored_duplicates):
    await _killed_after_a_completed_run()
    body = await _fallback_body()
    assert (body["storage_type"], body["total_count"]) == ("chromadb_fallback", 1)
    assert body["partial"] is True
    assert (body["run"]["status"], body["run"]["reason"]) == (
        "killed",
        "killed by the hard timeout: run exceeded 1800s",
    )


@pytest.mark.asyncio
async def test_the_fallback_of_a_source_without_a_run_record_is_not_partial(run_store, stored_duplicates):
    body = await _fallback_body()
    assert body["total_count"] == 1
    assert (body["partial"], body["run"]) == (False, None)


@pytest.mark.asyncio
async def test_the_run_state_is_read_before_the_stored_findings(run_store, stored_duplicates):
    await _killed_after_a_completed_run()
    reads_before = run_store.reads
    reads_when_findings_were_read = []
    stored_duplicates.side_effect = lambda *a, **k: (
        reads_when_findings_were_read.append(run_store.reads) or {"metadatas": [_STORED_DUPLICATE]}
    )
    await _fallback_body()
    assert reads_when_findings_were_read == [reads_before + 1]


@pytest.mark.asyncio
async def test_no_stored_findings_answers_the_unlabelled_error_body(run_store):
    with patch.object(results_mod, "get_code_collection", return_value=None):
        body = await _fallback_body()
    assert (body["status"], body["total_count"]) == ("error", 0)
    assert "partial" not in body
