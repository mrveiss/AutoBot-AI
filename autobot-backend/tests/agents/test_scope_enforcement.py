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

import agents.scope_enforcement as enforcement
from agents.base_agent_types import AgentRequest
from agents.scope_enforcement import ClaimNotHeld, hold_scopes, refused_response, require_held
from autobot_shared.coordination.run_progress import current_run, record_progress
from autobot_shared.coordination.work_claims import ClaimMode, ClaimUnavailable, ScopeError, list_claims, try_acquire

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


@pytest.mark.asyncio
async def test_a_malformed_later_scope_frees_the_ones_already_taken(redis):
    """#16213 review: `path:a` is genuinely acquired, then the next declaration fails
    to parse. The raise must not strand `path:a` until its TTL -- the same
    every-scope-or-none rule as a conflict, on the raising path."""
    with pytest.raises(ScopeError):
        async with hold_scopes(["path:a", "not a scope"], agent_id="agent-1", task_id="t1", intent="write"):
            pass
    assert await list_claims() == [], "a scope taken before the malformed one must be released"


# ---------------------------------------------------------------------------
# Renewal follows progress (#15950 AC4, owner ruling)
#
# A one-second renewal interval (TTL 3s) and a stall window set per test, so a
# stall is observable in seconds. The window's real floor -- twice the LLM
# request timeout -- is replaced here, not bypassed in production.
# ---------------------------------------------------------------------------


def _fast(monkeypatch, *, window: float) -> list[str]:
    """Shrink the interval and stall window; return the list every renew is recorded in."""
    renewals: list[str] = []

    async def _counting_renew(scope, **_kwargs):
        renewals.append(scope)
        return True

    monkeypatch.setattr("autobot_shared.coordination.work_claims.renew", _counting_renew)
    monkeypatch.setattr("agents.scope_enforcement.CLAIM_TTL_S", 3)
    monkeypatch.setattr("agents.scope_enforcement._stall_window_s", lambda _interval: window)
    return renewals


class _Recorder:
    """Stands in for the module logger, so a warning is asserted without relying on propagation."""

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, msg, *args) -> None:
        self.warnings.append(msg % args)

    def info(self, *_a, **_k) -> None:
        pass

    def error(self, *_a, **_k) -> None:
        pass


@pytest.mark.asyncio
async def test_a_run_that_keeps_reporting_progress_keeps_its_claim(redis, monkeypatch):
    """Slow but working must never lapse: the ruling's first guarantee."""
    renewals = _fast(monkeypatch, window=1.5)
    async with hold_scopes(["path:a/b.py"], agent_id="agent-1", task_id="t1", intent="write"):
        for _ in range(8):
            await asyncio.sleep(0.4)
            record_progress()
        assert current_run().standing == "held"
    assert len(renewals) >= 2, "a progressing run's claim was not kept renewed"


@pytest.mark.asyncio
async def test_a_run_that_goes_silent_lapses_and_stops_renewing(redis, monkeypatch):
    """A run hung on an await reports nothing, so its renewal stops and its claim is marked lapsed."""
    renewals = _fast(monkeypatch, window=1.5)
    async with hold_scopes(["path:a/b.py"], agent_id="agent-1", task_id="t1", intent="write"):
        await asyncio.sleep(3.5)
        run = current_run()
        assert run.standing == "lapsed" and "no progress" in run.lapse_reason
        settled = len(renewals)
        await asyncio.sleep(1.2)
        assert len(renewals) == settled, "a stalled run's claim was still being renewed"


@pytest.mark.asyncio
async def test_progress_from_a_spawned_task_reaches_the_run(redis):
    """Work fanned out from a run reports to it: a task copies the context it was created in."""

    async def _child() -> None:
        record_progress()

    async with hold_scopes(["path:a/b.py"], agent_id="agent-1", task_id="t1", intent="write"):
        run = current_run()
        before = run.last_progress
        await asyncio.sleep(0.05)
        await asyncio.create_task(_child())
        assert run.last_progress > before


@pytest.mark.asyncio
async def test_progress_in_a_nested_run_is_progress_of_the_outer_one(redis):
    async with hold_scopes(["path:a/one.py"], agent_id="agent-1", task_id="t1", intent="write"):
        outer = current_run()
        async with hold_scopes(["path:a/two.py"], agent_id="agent-1", task_id="t1", intent="write"):
            before = outer.last_progress
            await asyncio.sleep(0.05)
            record_progress()
            assert outer.last_progress > before


def test_reporting_progress_outside_a_run_does_nothing():
    assert current_run() is None
    record_progress()


# ---------------------------------------------------------------------------
# The write site checks the claim (#15950 AC6, owner ruling)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_write_inside_a_granted_claim_is_allowed(redis):
    async with hold_scopes(["kb:entry"], agent_id="agent-1", task_id="t1", intent="write"):
        require_held(["kb:entry"], site="test")


@pytest.mark.asyncio
async def test_a_write_under_a_lapsed_claim_is_refused(redis, monkeypatch):
    """A run that stalled and woke up must not write over a scope someone else may now hold."""
    _fast(monkeypatch, window=0.5)
    async with hold_scopes(["kb:entry"], agent_id="agent-1", task_id="t1", intent="write"):
        await asyncio.sleep(2.2)
        with pytest.raises(ClaimNotHeld, match="lapsed"):
            require_held(["kb:entry"], site="test")


@pytest.mark.asyncio
async def test_a_write_outside_the_declared_scopes_is_refused(redis):
    async with hold_scopes(["kb:entry"], agent_id="agent-1", task_id="t1", intent="write"):
        with pytest.raises(ClaimNotHeld, match="not held"):
            require_held(["kb:another"], site="test")


@pytest.mark.asyncio
async def test_a_held_parent_path_covers_a_write_below_it_and_nothing_beside_it(redis):
    async with hold_scopes(["path:a"], agent_id="agent-1", task_id="t1", intent="write"):
        require_held(["path:a/b.py"], site="test")
        with pytest.raises(ClaimNotHeld):
            require_held(["path:ab.py"], site="test")


def test_a_write_with_no_claimed_run_is_warned_not_refused(monkeypatch):
    """A dispatcher that skipped hold_scopes (#16269): named, not blocked, until routing is fixed."""
    recorder = _Recorder()
    monkeypatch.setattr(enforcement, "logger", recorder)

    require_held(["kb:entry"], site="test-bypass")

    assert any("UNCLAIMED WRITE at test-bypass" in w for w in recorder.warnings)


@pytest.mark.asyncio
async def test_a_degraded_registry_lets_the_write_through_and_says_so(redis, monkeypatch):
    """Redis down: the run proceeds unclaimed by design, and so does its write."""

    async def _unavailable(*_a, **_k):
        raise ClaimUnavailable("registry down")

    recorder = _Recorder()
    monkeypatch.setattr(enforcement, "logger", recorder)
    monkeypatch.setattr(enforcement, "_acquire_all", _unavailable)
    async with hold_scopes(["kb:entry"], agent_id="agent-1", task_id="t1", intent="write"):
        require_held(["kb:entry"], site="test")
    assert any("registry was unavailable" in w for w in recorder.warnings)


@pytest.mark.asyncio
async def test_the_kb_librarian_will_not_write_under_a_lapsed_claim(redis, monkeypatch):
    """The guard AC6 names: a declared write site that runs without a held claim fails.

    The contrast is the same write under a live claim, which must go through.
    """
    from agents.kb_librarian_agent import KBLibrarianAgent

    agent = KBLibrarianAgent.__new__(KBLibrarianAgent)
    writes: list[str] = []

    async def _add(content, title, source=None):
        writes.append(title)

    monkeypatch.setattr(agent, "add_new_knowledge", _add, raising=False)
    request = AgentRequest(
        request_id="r1",
        agent_type="kb_librarian",
        action="add_knowledge",
        payload={"content": "c", "title": "Entry"},
        context={},
        priority="normal",
        timeout=30.0,
    )
    scopes = agent.declared_scopes(request)
    _fast(monkeypatch, window=0.5)

    async with hold_scopes(scopes, agent_id="kb", task_id="t1", intent="add_knowledge"):
        await asyncio.sleep(2.2)
        with pytest.raises(ClaimNotHeld):
            await agent._handle_add_knowledge(request)
    assert writes == [], "the write went through under a lapsed claim"

    async with hold_scopes(scopes, agent_id="kb", task_id="t2", intent="add_knowledge"):
        await agent._handle_add_knowledge(request)
    assert writes == ["Entry"], "a write under a live claim was refused"
