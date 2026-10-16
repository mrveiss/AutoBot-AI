# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The agent ledger's read model over the real coordination stores (#18391).

Real `work_claims` / `claim_waitlist` / `dev_loop_actions` code against fakeredis
(real EVAL), so the Lua changes -- the renewal counter and the pruned-member
return -- are exercised, not mocked. The control for every "empty" assertion is
a populated twin in the same test, and "unreadable" is asserted separately.
"""

from __future__ import annotations

import time

import pytest
import pytest_asyncio

from autobot_shared.coordination import claim_waitlist as wl_mod
from autobot_shared.coordination import dev_loop_actions as dla
from autobot_shared.coordination import ledger_events, ledger_read
from autobot_shared.coordination import work_claims as wc_mod
from autobot_shared.coordination.claim_waitlist import all_waiters, join
from autobot_shared.coordination.work_claims import ClaimMode, release_scope, renew, try_acquire

try:
    import fakeredis
    import fakeredis.aioredis as fakeredis_async
except ImportError:  # pragma: no cover
    fakeredis_async = None
    fakeredis = None  # type: ignore[assignment]


@pytest_asyncio.fixture
async def redis(monkeypatch):
    if fakeredis_async is None:
        pytest.skip("fakeredis[lua] not installed")
    client = fakeredis_async.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)

    async def _client(database: str = "main"):
        return client

    for module in (wc_mod, wl_mod, dla, ledger_read):
        monkeypatch.setattr(module, "get_async_redis_client", _client)
    yield client
    await client.flushall()


async def _hold(scope, agent, task="t1", intent="work", ttl_s=None, company=None):
    return await try_acquire(
        scope, agent_id=agent, task_id=task, mode=ClaimMode.EXCLUSIVE, intent=intent, ttl_s=ttl_s, company_id=company
    )


# --- claims, renewals ---------------------------------------------------------


@pytest.mark.asyncio
async def test_claims_carry_the_renewal_count(redis):
    await _hold("path:a/b", "alpha")
    assert (await ledger_read.claims()).claims[0].renewals == 0
    for _ in range(3):
        assert await renew("path:a/b", agent_id="alpha", task_id="t1")
    row = (await ledger_read.claims()).claims[0]
    assert (row.scope, row.agent_id, row.mode, row.intent, row.renewals) == (
        "path:a/b",
        "alpha",
        "exclusive",
        "work",
        3,
    )


@pytest.mark.asyncio
async def test_a_company_sees_only_claims_stamped_with_its_id(redis):
    await _hold("path:a/x", "co-a-agent", company="A")
    await _hold("path:b/x", "co-b-agent", company="B")
    await _hold("provider:anthropic", "dev-session")  # install-wide: no stamp
    assert [c.agent_id for c in (await ledger_read.claims("A")).claims] == ["co-a-agent"]
    assert (await ledger_read.claims("C")).count == 0  # a company with no stamped claims sees nothing
    assert (await ledger_read.claims()).count == 3  # control: the install-wide read sees all three


@pytest.mark.asyncio
async def test_a_squatted_agent_slug_reveals_nothing(redis):
    """Company B using company A's (or an install-wide) agent NAME gains no visibility: scoping is by stamp."""
    await _hold("path:a/x", "shared-name", company="A")
    await _hold("provider:anthropic", "shared-name")  # install-wide holder with the same slug
    await join("path:a/x", agent_id="shared-name", task_id="w", intent="wait", company_id="A")
    await release_scope(
        "path:a/x",
        agent_id="shared-name",
        task_id="other",
    )  # refused release, unstamped actor
    for read in (ledger_read.claims, ledger_read.waitlists, ledger_read.conflicts, ledger_read.activity):
        assert [r for r in vars(await read("B")).values() if isinstance(r, list)][0] == [], read.__name__
    assert (await ledger_read.claims("A")).count == 1  # control: A sees its own


@pytest.mark.asyncio
async def test_the_authenticated_context_stamps_writes(redis):
    from autobot_shared.coordination.claim_company import set_company

    set_company("ctx-co")
    try:
        await _hold("path:c/x", "someone")
    finally:
        set_company(None)
    assert [c.company_id for c in (await ledger_read.claims("ctx-co")).claims] == ["ctx-co"]


# --- waitlists, contention ----------------------------------------------------


@pytest.mark.asyncio
async def test_waitlists_list_every_queue_with_positions_and_scope_by_agent(redis):
    await join("path:a/x", agent_id="co-a-agent", task_id="t", intent="wait", company_id="A")
    await join("path:a/x", agent_id="co-b-agent", task_id="t", intent="wait", company_id="B")
    await join("provider:anthropic", agent_id="co-a-agent", task_id="t2", intent="wait")
    assert sorted(await all_waiters()) == ["path:a/x", "provider:anthropic"]
    rows = (await ledger_read.waitlists()).waiters
    assert [(r.scope, r.position, r.agent_id) for r in rows if r.scope == "path:a/x"] == [
        ("path:a/x", 1, "co-a-agent"),
        ("path:a/x", 2, "co-b-agent"),
    ]
    mine = await ledger_read.waitlists("B")
    assert [(r.agent_id, r.position) for r in mine.waiters] == [("co-b-agent", 2)]


@pytest.mark.asyncio
async def test_contention_covers_only_shared_resource_scopes(redis):
    await _hold("provider:anthropic", "holder")
    await join("provider:anthropic", agent_id="waiter", task_id="t", intent="wait")
    await _hold("cpu:gpu0", "solo")
    await _hold("path:a/x", "pathy")
    rows = {r.scope: r for r in (await ledger_read.contention()).resources}
    assert set(rows) == {"provider:anthropic", "cpu:gpu0"}
    assert rows["provider:anthropic"].contended and [w.agent_id for w in rows["provider:anthropic"].waiters] == [
        "waiter"
    ]
    assert not rows["cpu:gpu0"].contended


# --- conflicts ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_release_aimed_at_another_holders_claim_is_recorded_and_deletes_nothing(redis):
    await _hold("path:a/x", "owner", "t-owner")
    assert await release_scope("path:a/x", agent_id="intruder", task_id="t-i") is False
    assert (await ledger_read.claims()).count == 1  # the claim stands
    rows = (await ledger_read.conflicts()).conflicts
    assert [(r.kind, r.agent_id, r.other_agent_id, r.scope) for r in rows] == [
        ("release_refused", "intruder", "owner", "path:a/x")
    ]


@pytest.mark.asyncio
async def test_releasing_a_scope_nobody_holds_is_not_a_conflict(redis):
    assert await release_scope("path:a/x", agent_id="a", task_id="t") is False
    assert (await ledger_read.conflicts()).conflicts == []


@pytest.mark.asyncio
async def test_a_claim_that_expired_unreleased_is_recorded_when_a_read_prunes_it(redis):
    await _hold("path:a/x", "crashed", "t-dead", ttl_s=1)
    await redis.delete("work_claims:c:path:a/x|crashed|t-dead")  # what TTL expiry does to the key, index left behind
    assert (await ledger_read.claims()).count == 0
    rows = (await ledger_read.conflicts()).conflicts
    assert [(r.kind, r.scope, r.agent_id) for r in rows] == [("claim_expired", "path:a/x", "crashed")]


@pytest.mark.asyncio
async def test_a_claim_pruned_by_a_later_acquire_is_still_recorded(redis):
    await _hold("path:a/x", "crashed", "t-dead")
    await redis.delete("work_claims:c:path:a/x|crashed|t-dead")
    assert not isinstance(await _hold("path:a/x", "next", "t-next"), wc_mod.ClaimConflict)
    rows = (await ledger_read.conflicts()).conflicts
    assert [(r.kind, r.agent_id) for r in rows] == [("claim_expired", "crashed")]


@pytest.mark.asyncio
async def test_a_yield_with_no_answer_past_the_timeout_is_a_conflict_and_an_answered_one_is_not(redis):
    old = "2020-01-01T00:00:00+00:00"
    for token in ("t-silent", "t-answered"):
        await redis.lpush(
            ledger_events.EVENTS_KEY,
            '{"type": "yield_requested", "at": "%s", "token": "%s", "scope": "path:a/x", '
            '"requester_agent_id": "req", "requester_task_id": "rt"}' % (old, token),
        )
    await redis.lpush(ledger_events.EVENTS_KEY, '{"type": "yield_answered", "at": "%s", "token": "t-answered"}' % old)
    rows = (await ledger_read.conflicts()).conflicts
    assert [(r.kind, r.agent_id) for r in rows] == [("yield_unanswered", "req")]


@pytest.mark.asyncio
async def test_a_fresh_yield_request_is_pending_not_unanswered(redis):
    now = time.time()
    events = [{"type": "yield_requested", "at": "2999-01-01T00:00:00+00:00", "token": "x"}]
    assert ledger_events.unanswered_yields(events, now_epoch=now, timeout_s=30) == []


@pytest.mark.asyncio
async def test_a_dev_loop_action_that_outlived_its_claim_is_a_conflict(redis):
    clean = dla.build_action(7, intent="triage", outcome=dla.OUTCOME_RAN, estimated_tokens=1)
    lapsed = dla.build_action(8, intent="fix", outcome=dla.OUTCOME_RAN_CLAIM_LAPSED, estimated_tokens=1, reason="slow")
    for action in (clean, lapsed):
        assert await dla.record(action)
    rows = (await ledger_read.conflicts()).conflicts
    assert [(r.kind, r.scope) for r in rows] == [("claim_lapsed_during_action", "issue:8")]
    assert (await ledger_read.conflicts("anyone")).conflicts == []  # install-wide data, never a company's


# --- dev loop, activity -------------------------------------------------------


@pytest.mark.asyncio
async def test_dev_loop_history_per_issue_includes_refusals(redis):
    await dla.record(
        dla.build_action(5, intent="a", outcome=dla.OUTCOME_SKIPPED_CLAIMED, estimated_tokens=0, reason="held")
    )
    await dla.record(dla.build_action(5, intent="b", outcome=dla.OUTCOME_RAN, estimated_tokens=3))
    assert (await ledger_read.dev_loop_issues()).issues == [5]
    history = await ledger_read.dev_loop_history(5)
    assert [a.outcome for a in history.actions] == ["ran", "skipped_claimed"]  # newest first
    assert (await ledger_read.dev_loop_history(99)).actions == []  # untouched issue: empty, read fine


@pytest.mark.asyncio
async def test_activity_merges_claims_waiters_and_events_newest_first(redis):
    await _hold("path:a/x", "co-a-agent", company="A")
    await join("path:a/x", agent_id="co-a-agent", task_id="t9", intent="wait", company_id="A")
    await release_scope("path:a/x", agent_id="stranger", task_id="s")
    rows = (await ledger_read.activity()).activity
    assert {r.type for r in rows} == {"claim_held", "waiting", "release_refused"}
    assert [r.at for r in rows] == sorted((r.at for r in rows), reverse=True)
    assert {r.type for r in (await ledger_read.activity("nobody")).activity} == set()


# --- unreachable is not empty -------------------------------------------------


@pytest.mark.asyncio
async def test_every_read_raises_unreadable_when_redis_is_gone_and_none_returns_empty(monkeypatch):
    async def _none(database: str = "main"):
        return None

    for module in (wc_mod, wl_mod, dla, ledger_read):
        monkeypatch.setattr(module, "get_async_redis_client", _none)
    reads = {
        "claims": ledger_read.claims(),
        "waitlists": ledger_read.waitlists(),
        "contention": ledger_read.contention(),
        "conflicts": ledger_read.conflicts(),
        "activity": ledger_read.activity(),
        "dev_loop_issues": ledger_read.dev_loop_issues(),
        "dev_loop_history": ledger_read.dev_loop_history(1),
    }
    for name, call in reads.items():
        with pytest.raises(ledger_read.LedgerUnreadable):
            await call
        assert name


@pytest.mark.asyncio
async def test_a_refused_release_shows_each_party_only_its_own_side(redis):
    await _hold("path:a/x", "holder-a", "th", company="A")
    await release_scope("path:a/x", agent_id="intruder-b", task_id="ti")  # actor context: none -> unstamped
    from autobot_shared.coordination.claim_company import set_company

    set_company("B")
    try:
        await release_scope("path:a/x", agent_id="intruder-b", task_id="ti")
    finally:
        set_company(None)
    as_b = [c for c in (await ledger_read.conflicts("B")).conflicts]
    as_a = [c for c in (await ledger_read.conflicts("A")).conflicts]
    assert [(c.agent_id, c.other_agent_id) for c in as_b] == [("intruder-b", None)]  # B never learns A's agent id
    assert [(c.agent_id, c.task_id, c.other_agent_id) for c in as_a] == [(None, None, "holder-a")] * 2
    assert (await ledger_read.conflicts("C")).conflicts == []


@pytest.mark.asyncio
async def test_the_unreadable_detail_is_generic_and_the_cause_is_only_logged(monkeypatch, caplog):
    async def _boom(database: str = "main"):
        raise ConnectionError("Error 111 connecting to 10.9.8.7:6379. Connection refused.")

    for module in (wc_mod, wl_mod, dla, ledger_read):
        monkeypatch.setattr(module, "get_async_redis_client", _boom)
    with pytest.raises(ledger_read.LedgerUnreadable) as caught:
        await ledger_read.claims()
    assert "10.9.8.7" not in caught.value.detail and "6379" not in caught.value.detail
    assert "10.9.8.7" in caplog.text  # kept server-side


@pytest.mark.asyncio
async def test_a_yield_reason_is_capped_on_write_and_other_fields_are_not(redis):
    long_text = "x" * (ledger_events.TEXT_CAP + 50)
    assert await ledger_events.record_ledger_event(
        redis, ledger_events.YIELD_REQUESTED, token="t", scope="path:a/x", reason=long_text, requester_task_id=long_text
    )
    row = (await ledger_read.activity()).activity[0]
    assert row.detail == "x" * ledger_events.TEXT_CAP
    stored = await redis.lindex(ledger_events.EVENTS_KEY, 0)
    assert long_text in stored  # a non-free-text field (an id) is never cut


# --- CodeRabbit threads on the read APIs (#18391) -------------------------------


@pytest.mark.asyncio
async def test_a_malformed_wait_key_is_skipped_not_fatal(redis):
    await join("path:a/b", agent_id="w", task_id="t", intent="x")
    await redis.rpush("work_claims:wait:bogus:thing", "x")
    assert list((await all_waiters()).keys()) == ["path:a/b"]


@pytest.mark.asyncio
async def test_malformed_events_are_filtered_out(redis):
    good = '{"type": "claim_expired", "at": "2026-01-01T00:00:00+00:00", "scope": "path:a"}'
    for bad in ('{"type": "claim_expired"}', '{"at": "2026-01-01T00:00:00+00:00"}', '{"type": "x", "at": "nope"}'):
        await redis.lpush(ledger_events.EVENTS_KEY, bad)
    await redis.lpush(ledger_events.EVENTS_KEY, good)
    assert [c.kind for c in (await ledger_read.conflicts("A")).conflicts] == []
    assert len((await ledger_read.conflicts()).conflicts) == 1
    assert len((await ledger_read.activity()).activity) == 1


@pytest.mark.asyncio
async def test_a_same_holder_reacquire_carries_the_renewal_count(redis):
    await _hold("path:a/b", "alpha")
    assert await renew("path:a/b", agent_id="alpha", task_id="t1")
    await _hold("path:a/b", "alpha")
    assert (await ledger_read.claims()).claims[0].renewals == 2


@pytest.mark.asyncio
async def test_work_claim_stamps_the_company_it_is_given(redis):
    async with wc_mod.work_claim("path:c/d", agent_id="a", intent="x", company_id="acme"):
        assert [c.company_id for c in (await ledger_read.claims("acme")).claims] == ["acme"]


def test_an_unknown_claim_kind_is_a_422():
    from fastapi import HTTPException

    from autobot_shared.coordination.ledger_http import valid_kind

    assert valid_kind(None) is None and valid_kind("path") == "path"
    with pytest.raises(HTTPException) as caught:
        valid_kind("foo")
    assert caught.value.status_code == 422


@pytest.mark.asyncio
async def test_an_explicit_company_overrides_and_cannot_be_shadowed_by_fields(redis):
    assert await ledger_events.record_ledger_event(redis, ledger_events.CLAIM_EXPIRED, company_id=None, scope="path:z")
    assert '"company_id": null' in await redis.lindex(ledger_events.EVENTS_KEY, 0)
