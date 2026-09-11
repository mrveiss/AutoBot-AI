# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every fail-open branch of task_claim leaves an audit record (#16217).

Failing open returns True, the same value success returns, so the audit event is
the only thing that tells an assumed renewal or release from a real one.
"""

import pytest

import services.task_claim as task_claim


class _BrokenRedis:
    """Reachable, then fails on the first command -- the ``redis_error`` branch."""

    def register_script(self, _script):
        raise ConnectionError("connection reset")


def _audited(monkeypatch, client) -> list:
    async def _get_client(*_args, **_kwargs):
        return client

    monkeypatch.setattr(task_claim, "get_async_redis_client", _get_client)
    events: list = []
    monkeypatch.setattr(task_claim, "emit", events.append)
    return events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "action"),
    [(task_claim.renew_claim, "task.renew"), (task_claim.release_claim, "task.release")],
)
@pytest.mark.parametrize(("client", "outcome"), [(None, "redis_unavailable"), (_BrokenRedis(), "redis_error")])
async def test_a_fail_open_branch_is_audited_with_its_own_outcome(monkeypatch, operation, action, client, outcome):
    events = _audited(monkeypatch, client)

    assert await operation("task-1", "agent-a") is True
    assert [(e.action, e.outcome, e.resource_id, e.actor_id) for e in events] == [
        (action, outcome, "task-1", "agent-a")
    ]
