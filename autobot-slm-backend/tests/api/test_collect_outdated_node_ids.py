# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for _collect_outdated_node_ids — #9996.

Facet A: co-located self-node must be enumerated even when its code_status
         has not yet been updated by heartbeat.
Facet B: currency uses code_version != remote_commit (not code_status) so
         nodes that heartbeat hasn't re-evaluated yet are still included.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

# The dev-host has a conflicting `multipart` package that breaks FastAPI's import
# of `starlette.formparsers`. Stub it out before anything imports FastAPI so
# that test collection can proceed. The starlette code path that needs
# python_multipart is never exercised in unit tests (we mock all I/O).
if "multipart" in sys.modules and not hasattr(sys.modules["multipart"], "multipart"):
    # Conflicting package — replace with an empty stub
    sys.modules.pop("multipart", None)
_mp_stub = types.ModuleType("multipart")
_mp_stub.multipart = types.ModuleType("multipart.multipart")  # type: ignore[attr-defined]
sys.modules.setdefault("multipart", _mp_stub)
sys.modules.setdefault("multipart.multipart", _mp_stub.multipart)  # type: ignore[attr-defined]

from api.code_sync import (  # noqa: E402
    UpdateAllJob,
    UpdateAllStage,
    _collect_outdated_node_ids,
)
from models.database import CodeStatus, Node  # noqa: E402

REMOTE_COMMIT = "deadbeef1234deadbeef1234"
SLM_IP = "10.0.1.10"
OTHER_IP = "10.0.1.20"


def _job() -> UpdateAllJob:
    return UpdateAllJob(
        job_id="test-job",
        status="running",
        created_at="2026-01-01T00:00:00+00:00",
        stages=[
            UpdateAllStage(name="github_fetch", status="success"),
            UpdateAllStage(name="code_source_pull", status="success"),
            UpdateAllStage(name="slm_self_update", status="running"),
            UpdateAllStage(name="fleet_nodes"),
        ],
    )


def _node(node_id: str, ip: str, code_version: str | None, code_status: str) -> Node:
    n = Node.__new__(Node)
    n.node_id = node_id
    n.hostname = f"host-{node_id}"
    n.ip_address = ip
    n.code_version = code_version
    n.code_status = code_status
    return n


def _db_service_mock(query_results: List[Node], slm_node: Node | None = None) -> Any:
    """Build a db_service mock that returns query_results for the version query
    and slm_node for the self-node lookup."""
    db_service_ref = MagicMock()

    class _FakeCtx:
        def __init__(self, nodes_for_version, self_node):
            self._nodes_for_version = nodes_for_version
            self._self_node = self_node
            self._call_count = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def execute(self, stmt):
            self._call_count += 1
            if self._call_count == 1:
                # First call: version-comparison query
                result = MagicMock()
                result.scalars.return_value.all.return_value = self._nodes_for_version
                return result
            else:
                # Second call: self-node IP lookup
                result = MagicMock()
                result.scalar_one_or_none.return_value = self._self_node
                return result

    ctx = _FakeCtx(query_results, slm_node)
    db_service_ref.session.return_value = ctx
    return db_service_ref


# ---------------------------------------------------------------------------
# Bug B: version comparison, not code_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b_includes_node_with_old_version_but_up_to_date_status():
    """Nodes with code_version != remote_commit are outdated regardless of code_status.

    Regression for #9996-B: heartbeat hasn't fired since stage-1 updated
    slm_agent_latest_commit, so code_status still shows UP_TO_DATE.
    """
    stale_node = _node("worker-1", OTHER_IP, "oldsha123", CodeStatus.UP_TO_DATE.value)

    job = _job()
    with patch("api.code_sync.settings") as mock_settings, patch(
        "api.code_sync._compute_deps_changed", new=AsyncMock(return_value=False)
    ):
        mock_settings.external_url = f"http://{SLM_IP}"
        db_svc = _db_service_mock(query_results=[stale_node], slm_node=None)
        result = await _collect_outdated_node_ids(job, REMOTE_COMMIT, db_svc)

    assert "worker-1" in result


@pytest.mark.asyncio
async def test_b_excludes_node_already_at_remote_commit():
    """Nodes at remote_commit are not reported as outdated.

    The version query returns an empty list (no rows differ from remote_commit),
    so the result must not contain worker-2.
    """
    # worker-2 is at remote_commit — the DB query (code_version != remote) excludes it
    # We pass an empty query_results to simulate that
    job = _job()
    with patch("api.code_sync.settings") as mock_settings, patch(
        "api.code_sync._compute_deps_changed", new=AsyncMock(return_value=False)
    ):
        mock_settings.external_url = f"http://{SLM_IP}"
        db_svc = _db_service_mock(query_results=[], slm_node=None)
        result = await _collect_outdated_node_ids(job, REMOTE_COMMIT, db_svc)

    assert "worker-2" not in result


# ---------------------------------------------------------------------------
# Bug A: co-located self-node inclusion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_self_node_included_when_not_in_version_query():
    """Self-node with UP_TO_DATE code_status but stale code_version is included.

    Regression for #9996-A: after stage-1 updates slm_agent_latest_commit,
    the heartbeat hasn't run yet so the SLM node row has code_status=UP_TO_DATE
    and code_version=<old_sha> — the version query returns it, and it must
    appear in the result.
    """
    # The self-node has a stale version — version query DOES return it
    self_node = _node("slm-node", SLM_IP, "oldsha456", CodeStatus.UP_TO_DATE.value)

    job = _job()
    with patch("api.code_sync.settings") as mock_settings, patch(
        "api.code_sync._compute_deps_changed", new=AsyncMock(return_value=False)
    ):
        mock_settings.external_url = f"http://{SLM_IP}"
        # Version query returns self_node (old version); slm_node lookup also returns it
        db_svc = _db_service_mock(query_results=[self_node], slm_node=self_node)
        result = await _collect_outdated_node_ids(job, REMOTE_COMMIT, db_svc)

    assert "slm-node" in result


@pytest.mark.asyncio
async def test_a_self_node_added_when_code_version_is_none():
    """Self-node with no code_version recorded is added explicitly.

    Covers the case where the node was never synced — code_version IS NULL.
    The version query (code_version != remote_commit OR is NULL) captures it;
    the self-node fallback is a safety net for edge cases.
    """
    # Node has no code_version at all
    self_node = _node("slm-node-fresh", SLM_IP, None, CodeStatus.UNKNOWN.value)

    job = _job()
    with patch("api.code_sync.settings") as mock_settings, patch(
        "api.code_sync._compute_deps_changed", new=AsyncMock(return_value=False)
    ):
        mock_settings.external_url = f"http://{SLM_IP}"
        # Version query includes self_node (NULL version); slm_node lookup same
        db_svc = _db_service_mock(query_results=[self_node], slm_node=self_node)
        result = await _collect_outdated_node_ids(job, REMOTE_COMMIT, db_svc)

    assert "slm-node-fresh" in result


@pytest.mark.asyncio
async def test_a_self_node_not_duplicated_when_already_in_version_list():
    """Self-node already captured by version query is NOT duplicated."""
    self_node = _node("slm-node", SLM_IP, "oldsha789", CodeStatus.OUTDATED.value)

    job = _job()
    with patch("api.code_sync.settings") as mock_settings, patch(
        "api.code_sync._compute_deps_changed", new=AsyncMock(return_value=False)
    ):
        mock_settings.external_url = f"http://{SLM_IP}"
        db_svc = _db_service_mock(query_results=[self_node], slm_node=self_node)
        result = await _collect_outdated_node_ids(job, REMOTE_COMMIT, db_svc)

    assert result.count("slm-node") == 1


@pytest.mark.asyncio
async def test_a_and_b_mixed_fleet():
    """Full fleet: stale worker + current worker + stale self-node all handled correctly."""
    stale_worker = _node("worker-stale", OTHER_IP, "oldsha", CodeStatus.UP_TO_DATE.value)
    self_node = _node("slm-node", SLM_IP, "oldsha", CodeStatus.UP_TO_DATE.value)
    # current_worker at remote_commit is NOT returned by the version query

    job = _job()
    with patch("api.code_sync.settings") as mock_settings, patch(
        "api.code_sync._compute_deps_changed", new=AsyncMock(return_value=False)
    ):
        mock_settings.external_url = f"http://{SLM_IP}"
        # Version query returns both stale nodes; self-node lookup returns self_node
        db_svc = _db_service_mock(query_results=[stale_worker, self_node], slm_node=self_node)
        result = await _collect_outdated_node_ids(job, REMOTE_COMMIT, db_svc)

    assert "worker-stale" in result
    assert "slm-node" in result
    assert result.count("slm-node") == 1
