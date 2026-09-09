# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Agents hold the scopes they declared, for as long as the run lasts (#15950).

The assertions that matter here are the ones about what enforcement must NOT do:
it must not keep a partial acquisition, must not renew after the run ends, must
not let a release failure replace the run's real outcome, and must not make the
claim registry a single point of failure for work it only advises on. A
happy-path test would pass on a version that got all four wrong.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from agents.base_agent_types import AgentRequest
from agents.scope_enforcement import hold_scopes, refused_response
from autobot_shared.coordination.work_claims import ClaimMode, list_claims, try_acquire

try:
    import fakeredis.aioredis as fakeredis_async
except ImportError:  # pragma: no cover
    fakeredis_async = None


@pytest_asyncio.fixture
async def redis(monkeypatch):
    if fakeredis_async is None:
        pytest.skip("fakeredis[lua] not installed")
    from autobot_shared.coordination import work_claims as wc

    client = fakeredis_async.FakeRedis(server=fakeredis_async.FakeServer(), decode_responses=True)

    async def _client(database: str = "main"):
        return client

    monkeypatch.setattr(wc, "get_async_redis_client", _client)
    yield client
    await client.flushall()


def _request(action: str = "write") -> AgentRequest:
    return AgentRequest(
        request_id="r1", agent_type="writer", action=action, payload={}, context={}, priority="normal", timeout=30.0
    )


@pytest.mark.asyncio
async def test_scopes_are_held_during_the_run_and_freed_after(redis):
    async with hold_scopes(["path:a/b.py"], agent_id="agent-1", task_id="t1", intent="write") as held:
        assert held.granted
        assert [c.scope for c in await list_claims()] == ["path:a/b.py"]
    assert await list_claims() == [], "the scope must not outlive the run"


@pytest.mark.asyncio
async def test_a_raising_run_still_frees_its_scopes(redis):
    """Release lives in `finally`, so the failure path is the one worth asserting."""
    with pytest.raises(RuntimeError):
        async with hold_scopes(["path:a/b.py"], agent_id="agent-1", task_id="t1", intent="write"):
            raise RuntimeError("mid-task explosion")
    assert await list_claims() == [], "a crashed run must not hold its scope"


@pytest.mark.asyncio
async def test_a_partial_acquisition_keeps_nothing(redis):
    """Winning two of three and keeping them blocks others for a run that never started.

    Worse, two such runs can hold each other's missing scope indefinitely. The
    assertion is that the *first* scope, which was genuinely acquired, is gone.
    """
    await try_acquire("path:b", agent_id="other", task_id="t9", mode=ClaimMode.EXCLUSIVE, intent="incumbent")

    async with hold_scopes(["path:a", "path:b"], agent_id="agent-1", task_id="t1", intent="write") as held:
        assert not held.granted
        assert held.conflict.holder.agent_id == "other"

    remaining = {c.scope for c in await list_claims()}
    assert remaining == {"path:b"}, "path:a was taken then must have been given back"


@pytest.mark.asyncio
async def test_declaring_nothing_costs_nothing(redis):
    """The default must not make every existing agent pay for the registry."""
    async with hold_scopes([], agent_id="agent-1", task_id="t1", intent="x") as held:
        assert held.granted
        assert await list_claims() == []


@pytest.mark.asyncio
async def test_the_renewal_stops_when_the_run_does(redis, monkeypatch):
    """A renew loop nobody cancels would hold a hung executor's scope forever."""
    renewals: list[str] = []

    async def _counting_renew(scope, **kwargs):
        renewals.append(scope)
        return True

    monkeypatch.setattr("autobot_shared.coordination.work_claims.renew", _counting_renew)
    monkeypatch.setattr("agents.scope_enforcement.CLAIM_TTL_S", 3)

    async with hold_scopes(["path:a/b.py"], agent_id="agent-1", task_id="t1", intent="write"):
        await asyncio.sleep(1.2)
    after_exit = len(renewals)

    await asyncio.sleep(1.2)
    assert len(renewals) == after_exit, "the renewer kept running after the run ended"


@pytest.mark.asyncio
async def test_a_release_failure_does_not_replace_the_runs_outcome(redis, monkeypatch):
    """A registry error in `finally` would surface as a task failure it did not cause."""

    async def _failing_release(scope, **kwargs):
        raise RuntimeError("redis went away")

    monkeypatch.setattr("autobot_shared.coordination.work_claims.release", _failing_release)

    async with hold_scopes(["path:a/b.py"], agent_id="agent-1", task_id="t1", intent="write") as held:
        assert held.granted
    # Reaching here at all is the assertion: the context manager exited cleanly.


@pytest.mark.asyncio
async def test_an_unavailable_registry_lets_the_run_proceed_unclaimed(redis, monkeypatch):
    """Refusing every run would make a dashboard-adjacent service a hard dependency.

    The claim is advisory; Redis being down must degrade coordination, not stop
    the work. The run proceeds and the module logs it at ERROR.
    """
    from autobot_shared.coordination.work_claims import ClaimUnavailable

    async def _unavailable(*args, **kwargs):
        raise ClaimUnavailable("redis down")

    monkeypatch.setattr("autobot_shared.coordination.work_claims.try_acquire", _unavailable)

    async with hold_scopes(["path:a/b.py"], agent_id="agent-1", task_id="t1", intent="write") as held:
        assert held.granted, "the run must proceed when the registry cannot answer"
        assert held.claims == (), "and it must not claim to hold anything"


def test_a_refusal_names_the_holder_and_their_intent():
    """ "Blocked" without "by whom, doing what" turns a collision into a mystery."""
    from autobot_shared.coordination.work_claims import Claim, ClaimConflict

    holder = Claim(
        scope="path:a/b.py",
        agent_id="agent-9",
        task_id="t9",
        mode="exclusive",
        intent="fix the header parse",
        acquired_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T00:05:00Z",
    )
    response = refused_response(_request(), ClaimConflict(requested="path:a/b.py", holder=holder), agent_type="writer")

    assert response.status == "refused"
    assert response.metadata["held_by_agent"] == "agent-9"
    assert response.metadata["holder_intent"] == "fix the header parse"
    assert "fix the header parse" in response.error, "the operator reads `error`, not just metadata"
