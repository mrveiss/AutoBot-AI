# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15475 — self-update must refresh every co-located role, not just the SLM
node.

``POST /api/code-sync/self-update`` ran ``update-all-nodes.yml`` with
``--limit localhost,<slm-node>``. A co-located main frontend can be modeled
as its OWN ``Node`` row sharing the SLM's IP (see
``setup_wizard._apply_colocation_vars``); Play 2 (``hosts: infrastructure``)
only executes for a host ``--limit`` includes, so that row was silently
skipped. The fix scopes ``--limit`` to every ``Node`` row registered at this
physical machine's own IP addresses — not the SLM's node_id alone, and not
the whole fleet.
"""

from __future__ import annotations

import contextlib
import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _code_sync_import import import_code_sync  # noqa: E402

import_code_sync()

import asyncio  # noqa: E402

from api.code_sync import _ansible_self_update, _colocated_node_ids  # noqa: E402

importlib.import_module("services.database")


@contextlib.contextmanager
def _patched_db_service(db_service_mock):
    """setattr/restore on the sys.modules entry, not ``patch("services.database.db_service")``.

    That dotted-path form resolves via getattr on the PARENT ``services``
    module, which a whole-backend sweep can leave as a hollow package with no
    ``database`` attribute yet, while ``_colocated_node_ids`` resolves
    ``from services.database import db_service`` through ``sys.modules``
    directly — the same #11798/#9780 divergence ``test_component_resolve_job.py``
    documents. Patch the sys.modules entry itself so both paths agree.
    """
    mod = sys.modules["services.database"]
    prev = getattr(mod, "db_service", None)
    mod.db_service = db_service_mock
    try:
        yield
    finally:
        mod.db_service = prev


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeSessionCtx:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def execute(self, _stmt):
        result = MagicMock()
        result.all.return_value = self._rows
        return result


def _db_service_with_rows(rows):
    db_service_ref = MagicMock()
    db_service_ref.session.return_value = _FakeSessionCtx(rows)
    return db_service_ref


def test_colocated_node_sharing_this_machines_ip_is_included() -> None:
    """A separate Node row for the co-located frontend, same IP as the SLM
    node, must be pulled into the limit set."""
    rows = [("slm-node-1", "10.0.0.5"), ("frontend-node-2", "10.0.0.5"), ("remote-npu-node-3", "10.0.0.9")]

    with (
        patch("autobot_shared.network_utils.get_local_ips", return_value={"10.0.0.5"}),
        _patched_db_service(_db_service_with_rows(rows)),
    ):
        result = _run(_colocated_node_ids("slm-node-1"))

    assert result == sorted({"slm-node-1", "frontend-node-2"})
    assert "remote-npu-node-3" not in result


def test_remote_fleet_node_never_enters_the_limit() -> None:
    """The blast radius stays this machine: a node on a different IP must
    never be added, however many rows the fleet has."""
    rows = [("slm-node-1", "10.0.0.5")] + [(f"fleet-node-{i}", "10.0.0.{}".format(i)) for i in range(10, 20)]

    with (
        patch("autobot_shared.network_utils.get_local_ips", return_value={"10.0.0.5"}),
        _patched_db_service(_db_service_with_rows(rows)),
    ):
        result = _run(_colocated_node_ids("slm-node-1"))

    assert result == ["slm-node-1"]


def test_ansible_self_update_passes_colocated_ids_as_limit() -> None:
    executor = MagicMock()
    executor.execute_playbook = AsyncMock(return_value={"success": True, "output": ""})

    with (
        patch("api.code_sync.get_playbook_executor", return_value=executor),
        patch(
            "api.code_sync._colocated_node_ids",
            AsyncMock(return_value=["frontend-node-2", "slm-node-1"]),
        ),
        patch("api.code_sync._update_fleet_node_version", AsyncMock()),
    ):
        _run(_ansible_self_update("slm-node-1"))

    call_kwargs = executor.execute_playbook.await_args.kwargs
    assert call_kwargs["limit"] == ["localhost", "frontend-node-2", "slm-node-1"]
