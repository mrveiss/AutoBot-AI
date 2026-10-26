# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The stalled-run sweep must sweep, and must not sweep what is still alive (#16817).

The defect this closes was not a wrong result — it was no result at all: nothing read
``llc_heartbeat_runs`` back to decide a run had stopped. So the tests that matter are
the ones that fail if the sweep ever stops selecting: a sweep that quietly matches
nothing is indistinguishable from the state before it existed.
"""

import asyncio
import importlib
import uuid
from datetime import datetime, timedelta, timezone

import fakeredis
import pytest
from sqlalchemy.dialects import postgresql

from llc.models.enums import LLCRunStatus
from testkit.fake_async_session import FakeAsyncSession
from testkit.fake_result import FakeResult


@pytest.fixture
def sweep(monkeypatch):
    """Import with a short timeout so the tests do not depend on the six-hour default."""
    monkeypatch.setenv("LLC_RUN_STALL_TIMEOUT_SECONDS", "60")
    module = importlib.import_module("llc.scheduler.stalled_run_sweep")
    return importlib.reload(module)


def test_the_timeout_is_env_var_backed_not_a_literal(sweep):
    assert sweep.STALL_TIMEOUT_SECONDS == 60


def test_the_default_is_used_when_the_env_var_is_absent(monkeypatch):
    monkeypatch.delenv("LLC_RUN_STALL_TIMEOUT_SECONDS", raising=False)
    module = importlib.reload(importlib.import_module("llc.scheduler.stalled_run_sweep"))
    assert module.STALL_TIMEOUT_SECONDS == 6 * 60 * 60


def test_a_run_older_than_the_cutoff_is_past_it(sweep):
    old = datetime.now(timezone.utc) - timedelta(seconds=120)
    assert old <= sweep._cutoff()


def test_a_fresh_run_is_not_past_the_cutoff(sweep):
    fresh = datetime.now(timezone.utc) - timedelta(seconds=5)
    assert fresh > sweep._cutoff()


def test_only_non_terminal_statuses_are_candidates(sweep):
    """A completed or failed run is finished; sweeping it would rewrite history."""
    assert set(sweep.NON_TERMINAL_STATUSES) == {"queued", "running"}
    for terminal in ("completed", "failed", "interrupted", "timeout"):
        assert terminal not in sweep.NON_TERMINAL_STATUSES


def test_the_error_says_the_sweep_decided_it(sweep):
    """The human-readable half of the distinction.

    #16817 rewrote this test's premise. It used to read "both end as status
    ``timeout`` ... the error text is the only place that distinguishes them", which
    was true and was the defect: telling a stall from an adapter timeout meant
    matching a formatted message. ``STALLED`` now carries the fact and this carries
    the detail, so a re-wording here can no longer make the two indistinguishable.
    """
    message = sweep.STALL_ERROR.format(seconds=60)
    assert "sweep" in message
    assert "60" in message
    assert "16817" in message


def test_a_swept_run_is_stalled_rather_than_timeout(sweep):
    """AC4: the reason is recorded in the status, not inferred from the error.

    Four sites set ``TIMEOUT`` -- http_adapter, subprocess_base, heartbeat_scheduler
    and this sweep -- so before #16817 a consumer asking "which runs stalled?" had to
    match the error text. A status the sweep alone writes is what makes that a lookup.
    """
    assert LLCRunStatus.STALLED.value == "stalled"
    assert LLCRunStatus.STALLED is not LLCRunStatus.TIMEOUT


@pytest.mark.parametrize("other", ["TIMEOUT", "FAILED", "CANCELLED", "INTERRUPTED"])
def test_stalled_is_distinct_from_every_status_it_could_be_confused_with(other):
    """AC4 names failed and cancelled; timeout is the one it actually shared."""
    assert LLCRunStatus.STALLED.value != getattr(LLCRunStatus, other).value


def test_stalled_is_terminal(sweep):
    """A swept run is over. ``is_terminal`` is a deny-list over {queued, running},
    so this holds by construction -- asserted because that is the property relied on
    when STALLED was added without editing the terminal set."""
    assert LLCRunStatus.STALLED.is_terminal() is True
    assert LLCRunStatus.STALLED.value not in sweep.NON_TERMINAL_STATUSES


def _compiled(sweep):
    """Compiled against PostgreSQL, because that is what runs it.

    The default dialect renders ``FOR UPDATE`` and silently drops ``SKIP LOCKED`` --
    it is a PostgreSQL extension. Asserting against the generic rendering would have
    reported a lock clause that production does not get, which is the shape of error
    this sweep's own tests exist to avoid.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
    return str(sweep._stalled_candidates(cutoff).compile(dialect=postgresql.dialect()))


def test_the_rows_are_locked_and_locked_rows_are_skipped(sweep):
    """AC5, and it is about timing rather than today's behaviour.

    Two beat workers overlapping today would write the same terminal status, so the
    race is invisible. Once the sweep releases leases and checkouts on this path, the
    same race releases each holding twice -- the lock is what partitions the runs.
    """
    sql = _compiled(sweep)
    assert "FOR UPDATE" in sql
    assert "SKIP LOCKED" in sql


def test_the_age_comparison_happens_in_sql(sweep):
    """The scan fix: the WHERE carries the age rule, so the sweep does not load every
    non-terminal run and filter in Python. The original comment's NULL reasoning was
    right -- COALESCE is that reasoning expressed where the index can serve it."""
    sql = _compiled(sweep).lower()
    assert "coalesce" in sql
    assert "started_at" in sql and "created_at" in sql


def test_the_sweep_is_registered_as_a_named_celery_task(sweep):
    """An unregistered task is a sweep that never runs — the state before this."""
    assert sweep.run_stalled_run_sweep.name == "llc.scheduler.stalled_run_sweep.run_stalled_run_sweep"


class _Run:
    """A row the sweep may close out. Only the fields the sweep touches or filters on."""

    def __init__(self, age_seconds: int = 3600):
        self.id = uuid.uuid4()
        self.status = "running"
        self.finished_at = None
        self.error = None
        self.started_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
        self.created_at = self.started_at


class _Lease:
    """A workspace lease. Only what `release_for_run` filters on and `release` touches."""

    def __init__(self, run_id=None):
        self.heartbeat_run_id = run_id
        self.path = "/w/issue-1"
        self.owner = "session-gone"
        self.released_at = None
        self.release_reason = None


class _Item:
    """A work item. Only what the checkout release filters on and writes."""

    def __init__(self, checkout_run_id=None):
        self.id = uuid.uuid4()
        self.company_id = uuid.uuid4()
        self.assignee_agent_id = uuid.uuid4()
        self.checkout_run_id = str(checkout_run_id) if checkout_run_id else None
        self.checkout_locked_at = datetime.now(timezone.utc) if checkout_run_id else None
        self.version = 1


def _bound_values(statement) -> list:
    values = []
    for value in statement.compile().params.values():
        values.extend(value if isinstance(value, (list, tuple)) else [value])
    return values


class _World:
    """Runs, leases and checkouts, answering the sweep's three queries by their own
    predicates -- so a release the sweep does not ask for is a release that does not
    happen. ``locked`` stands in for row locks held until commit, which is what
    SKIP LOCKED partitions on."""

    def __init__(self, runs=(), leases=(), items=()):
        self.runs, self.leases, self.items = list(runs), list(leases), list(items)
        self.locked: set = set()

    def answer(self, statement, mine: set) -> list:
        entity = statement.column_descriptions[0]["entity"].__name__
        bound = _bound_values(statement)
        if entity == "LLCHeartbeatRun":
            cutoff = next(v for v in bound if isinstance(v, datetime))
            rows = [r for r in self.runs if r.status in bound and (r.started_at or r.created_at) <= cutoff]
            if statement._for_update_arg is None:
                return rows  # no row lock: an overlapping sweeper sees the same rows
            rows = [r for r in rows if r.id not in self.locked]
            mine.update(r.id for r in rows)
            self.locked.update(mine)
            return rows
        if entity == "LLCWorkspaceLease":
            return [x for x in self.leases if x.heartbeat_run_id in bound and x.released_at is None]
        return [i for i in self.items if i.checkout_run_id is not None and i.checkout_run_id in bound]


class _WorldSession(FakeAsyncSession):
    def __init__(self, world: _World):
        super().__init__()
        self.world, self.mine = world, set()

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        rows = self.world.answer(statement, self.mine)
        await asyncio.sleep(0)  # let a concurrent sweeper interleave between select and commit
        return FakeResult(rows)

    async def commit(self):
        await super().commit()
        self.world.locked -= self.mine


class _Recorder:
    def __init__(self):
        self.entries: list[dict] = []

    async def record(self, session, **entry):
        self.entries.append(entry)


class _CheckoutLandsMidRelease:
    """Redis in which a newer checkout lands right after the sweep's first command.

    Models the window the fence's TTL opens: the released fence expires and another
    agent's ``SET NX`` takes the key. A client-side GET -> compare -> DEL has its gap
    exactly there; one atomic compare-and-delete has none.
    """

    def __init__(self, inner, key: str, newer: str):
        self._inner, self._key, self._newer, self._landed = inner, key, newer, False

    def __getattr__(self, name):
        command = getattr(self._inner, name)
        if name not in ("get", "eval") or self._landed:
            return command

        async def then_a_checkout_lands(*args, **kwargs):
            result = await command(*args, **kwargs)
            self._landed = True
            await self._inner.delete(self._key)  # the released fence's TTL ran out
            await self._inner.set(self._key, self._newer, nx=True)
            return result

        return then_a_checkout_lands


@pytest.fixture
def world(sweep, monkeypatch):
    """A fresh world wired into the sweep: sessions, activity log and Redis fences."""
    state = _World()
    state.sessions = []
    state.audit = _Recorder()
    state.fences = fakeredis.aioredis.FakeRedis(decode_responses=True)

    def factory():
        session = _WorldSession(state)
        state.sessions.append(session)
        return session

    monkeypatch.setattr(sweep, "get_async_session_factory", lambda: factory)
    monkeypatch.setattr(sweep, "_activity_log", state.audit)

    async def redis():
        return state.redis or state.fences

    state.redis = None

    monkeypatch.setattr(sweep, "get_async_redis_client", redis)
    return state


@pytest.mark.asyncio
async def test_the_sweep_writes_stalled_and_closes_the_run_out(sweep, world):
    """AC6's status half, driven through `_async_sweep` rather than asserted on the enum.

    Without this, every other AC4 test here passes while the sweep writes whatever it
    likes -- the enum member existing is not the sweep using it. Mutation-checked:
    changing the write back to TIMEOUT fails this and nothing else.
    """
    row = _Run()
    world.runs.append(row)

    report = await sweep._async_sweep()

    assert report["stalled"] == 1
    assert row.status == LLCRunStatus.STALLED.value
    assert row.finished_at is not None, "a swept run must be closed out, not just relabelled"
    assert "16817" in row.error
    assert world.sessions[0].committed is True


@pytest.mark.asyncio
async def test_a_sweep_with_nothing_to_do_reports_zero_rather_than_silence(sweep, world):
    """AC7: a sweep that found nothing and a sweep that did not run must differ.

    Every count is in the return value, and it is logged unconditionally -- so zero is
    a measurement here, not an absence of one.
    """
    assert await sweep._async_sweep() == {"stalled": 0, "workspace_leases": 0, "checkouts": 0}
    assert world.sessions[0].committed is True


@pytest.mark.asyncio
async def test_a_stalled_run_hands_its_workspace_back(sweep, world):
    """#16818's AC2 half: marking a run stalled while it still holds a workspace is the
    2026-09-16 state -- a status nobody acts on, and a slot nothing can reclaim."""
    run = _Run()
    lease = _Lease(run.id)
    world.runs.append(run)
    world.leases.append(lease)

    assert (await sweep._async_sweep())["workspace_leases"] == 1
    assert lease.released_at is not None, "the workspace must be handed back"
    assert "16818" in lease.release_reason
    assert lease.release_reason == sweep.STALL_RELEASE_REASON


@pytest.mark.asyncio
async def test_the_release_reason_says_the_run_stalled_not_that_the_lease_expired(sweep, world):
    """Two different failures, two different remedies. A run that died is a bug to
    investigate; a lease that expired is a holder that walked away. The audit trail
    has to tell them apart, which a shared reason string would prevent."""
    run = _Run()
    lease = _Lease(run.id)
    world.runs.append(run)
    world.leases.append(lease)

    await sweep._async_sweep()

    from llc.services.workspace_lease import RECLAIM_REASON

    assert lease.release_reason != RECLAIM_REASON
    assert "stalled" in lease.release_reason


@pytest.mark.asyncio
async def test_a_stalled_run_releases_its_checkout_and_its_lease_and_is_marked_stalled(sweep, world):
    """#16817 AC2 + AC6: the status change AND the release of everything the run held.

    The checkout is the claim the 2026-09-16 incident was about -- an item held by a
    run that no longer exists, unstartable by anyone else. Mutation-checked: dropping
    the checkout release fails this while the lease assertions stay green.
    """
    run = _Run()
    lease, item = _Lease(run.id), _Item(run.id)
    world.runs.append(run)
    world.leases.append(lease)
    world.items.append(item)
    fence = f"llc:checkout:{item.id}"
    await world.fences.set(fence, str(item.assignee_agent_id))

    report = await sweep._async_sweep()

    assert report == {"stalled": 1, "workspace_leases": 1, "checkouts": 1}
    assert run.status == LLCRunStatus.STALLED.value
    assert lease.released_at is not None
    assert item.checkout_run_id is None and item.checkout_locked_at is None
    assert item.version == 2
    assert await world.fences.get(fence) is None, "the Redis fence must not outlive the checkout"
    [entry] = world.audit.entries
    assert entry["entity_id"] == str(item.id)
    assert entry["metadata"]["reason"] == "stalled"
    assert entry["metadata"]["heartbeat_run_id"] == str(run.id)


@pytest.mark.asyncio
async def test_the_assignment_survives_the_checkout_release(sweep, world):
    """The assignment is not run-scoped -- it can predate the run -- so it stays."""
    run = _Run()
    item = _Item(run.id)
    assignee = item.assignee_agent_id
    world.runs.append(run)
    world.items.append(item)

    await sweep._async_sweep()

    assert item.checkout_run_id is None
    assert item.assignee_agent_id == assignee


@pytest.mark.asyncio
async def test_two_concurrent_sweeps_release_each_holding_once(sweep, world):
    """AC5: two overlapping beat workers partition the runs instead of both releasing."""
    run = _Run()
    world.runs.append(run)
    world.leases.append(_Lease(run.id))
    world.items.append(_Item(run.id))

    first, second = await asyncio.gather(sweep._async_sweep(), sweep._async_sweep())
    third = await sweep._async_sweep()

    totals = [first, second, third]
    assert sum(r["stalled"] for r in totals) == 1
    assert sum(r["checkouts"] for r in totals) == 1
    assert sum(r["workspace_leases"] for r in totals) == 1
    assert len(world.audit.entries) == 1, "one release, one audit entry"


@pytest.mark.asyncio
async def test_a_live_run_releases_nothing(sweep, world):
    """A run inside its deadline keeps its status, its checkout and its lease."""
    run = _Run(age_seconds=5)
    lease, item = _Lease(run.id), _Item(run.id)
    world.runs.append(run)
    world.leases.append(lease)
    world.items.append(item)

    assert await sweep._async_sweep() == {"stalled": 0, "workspace_leases": 0, "checkouts": 0}
    assert run.status == "running"
    assert item.checkout_run_id == str(run.id)
    assert lease.released_at is None
    assert world.audit.entries == []


@pytest.mark.asyncio
async def test_a_checkout_the_stalled_run_did_not_make_is_untouched(sweep, world):
    """Release what the run acquired, not what happens to be near it."""
    run, other = _Run(), _Run(age_seconds=5)
    mine, theirs, unclaimed = _Item(run.id), _Item(other.id), _Item()
    world.runs.extend([run, other])
    world.items.extend([mine, theirs, unclaimed])
    await world.fences.set(f"llc:checkout:{theirs.id}", str(theirs.assignee_agent_id))

    assert (await sweep._async_sweep())["checkouts"] == 1
    assert mine.checkout_run_id is None
    assert theirs.checkout_run_id == str(other.id) and theirs.version == 1
    assert unclaimed.checkout_run_id is None and unclaimed.version == 1
    assert await world.fences.get(f"llc:checkout:{theirs.id}") == str(theirs.assignee_agent_id)


@pytest.mark.asyncio
async def test_a_fence_naming_a_newer_holder_is_left_alone(sweep, world):
    """The fence is dropped only while it still names the released checkout's holder."""
    run = _Run()
    item = _Item(run.id)
    world.runs.append(run)
    world.items.append(item)
    fence = f"llc:checkout:{item.id}"
    await world.fences.set(fence, "someone-newer")

    await sweep._async_sweep()

    assert await world.fences.get(fence) == "someone-newer"


def test_the_checkout_lookup_is_keyed_by_the_run_and_row_locked(sweep):
    """The release is scoped by ``checkout_run_id`` -- the run's own key -- and waits
    for, rather than skips, an item another transaction holds."""
    sql = str(sweep._checkouts_held_by(uuid.uuid4()).compile(dialect=postgresql.dialect()))
    assert "checkout_run_id" in sql
    assert "FOR UPDATE" in sql and "SKIP LOCKED" not in sql


@pytest.mark.asyncio
async def test_a_checkout_landing_mid_release_keeps_its_fence(sweep, world):
    """The fence check and the delete are one atomic step (#19607 review).

    Fail demo: a client-side GET -> compare -> DEL reads the released holder, the newer
    checkout lands in the gap, and the DEL removes the newer holder's fence.
    """
    run = _Run()
    item = _Item(run.id)
    world.runs.append(run)
    world.items.append(item)
    fence = f"llc:checkout:{item.id}"
    await world.fences.set(fence, str(item.assignee_agent_id))
    world.redis = _CheckoutLandsMidRelease(world.fences, fence, "agent-newer")

    report = await sweep._async_sweep()

    assert report["checkouts"] == 1
    assert await world.fences.get(fence) == "agent-newer", "a newer checkout's fence must survive the release"


@pytest.mark.asyncio
async def test_a_redis_client_failure_after_commit_does_not_fail_the_sweep(sweep, world, monkeypatch, caplog):
    """The DB release has committed; a missing Redis client must not turn that into a task failure."""
    run = _Run()
    item = _Item(run.id)
    world.runs.append(run)
    world.items.append(item)

    async def broken():
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(sweep, "get_async_redis_client", broken)

    report = await sweep._async_sweep()

    assert report == {"stalled": 1, "workspace_leases": 0, "checkouts": 1}
    assert item.checkout_run_id is None
    assert "redis unreachable" in caplog.text


@pytest.mark.asyncio
async def test_one_failing_fence_does_not_stop_the_next(sweep, world, monkeypatch):
    """A Redis error on one fence is logged; the remaining fences are still dropped."""
    calls: list[str] = []

    async def flaky(redis, key, expected):
        calls.append(key)
        if len(calls) == 1:
            raise TimeoutError("first fence timed out")
        await world.fences.delete(key)
        return True

    monkeypatch.setattr(sweep, "delete_if_value", flaky)
    await world.fences.set("llc:checkout:b", "agent-b")

    await sweep._drop_checkout_fences([("a", "agent-a"), ("b", "agent-b")])

    assert calls == ["llc:checkout:a", "llc:checkout:b"]
    assert await world.fences.get("llc:checkout:b") is None
