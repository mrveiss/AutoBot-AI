# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A schedule's fleet job, shared by run-now and the schedule executor (#19352).

The executor used to honour ``restart_strategy == "manual"`` (no restart) on its own rsync path. Now
that both callers build the job in ``_create_fleet_sync_job``, the rule lives there once.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _code_sync_import import import_code_sync  # noqa: E402

import_code_sync()

import api.code_sync as code_sync  # noqa: E402


def _node(node_id):
    return SimpleNamespace(
        node_id=node_id, hostname=f"h-{node_id}", ip_address="node.example.test", ssh_user=None, ssh_port=None
    )


@pytest.mark.parametrize(
    ("restart_after_sync", "strategy", "restart"),
    [(True, "graceful", True), (True, "immediate", True), (True, "manual", False), (False, "graceful", False)],
)
def test_schedule_job_restart_follows_the_schedule(restart_after_sync, strategy, restart):
    schedule = SimpleNamespace(restart_after_sync=restart_after_sync, restart_strategy=strategy)
    job = code_sync._create_fleet_sync_job([_node("n1"), _node("n2")], schedule)
    assert job.restart is restart
    assert (job.strategy, job.batch_size) == ("rolling", 1)
    assert sorted(job.nodes) == ["n1", "n2"] and job.nodes["n1"].ssh_user == "autobot"


@pytest.mark.asyncio
async def test_queue_schedule_job_guards_then_persists(monkeypatch):
    calls = []

    async def _guard(db):
        calls.append("guard")

    async def _persist(job):
        calls.append(("persist", sorted(job.nodes)))

    monkeypatch.setattr(code_sync, "assert_no_running_sync", _guard)
    monkeypatch.setattr(code_sync, "_persist_fleet_sync_job", _persist)
    schedule = SimpleNamespace(restart_after_sync=True, restart_strategy="graceful")
    job = await code_sync.queue_schedule_job(object(), schedule, [_node("n1")])
    assert calls == ["guard", ("persist", ["n1"])] and job.restart is True
