# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The replay store's three states and the two races that defeat them (#15778).

Against a real fakeredis rather than a mock: `SET NX` and the compare-and-set
scripts are the whole mechanism -- a stub that returns whatever the test wants
would assert only that the code calls the function it obviously calls.

The race tests force their interleaving rather than hoping the scheduler
produces it. `_Rendezvous` holds every caller until all of them have reached the
same point, so "both callers lost SET NX before either read the key" is a fact
of the test rather than a coincidence; the fencing tests drive two coroutines
that wait on each other's events. A concurrency test that only *usually*
interleaves passes against the bug most of the time, which is worse than not
having it.
"""

from __future__ import annotations

import asyncio

import fakeredis.aioredis
import pytest

from autobot_shared.idempotency import (
    IDEMPOTENCY_CLAIM_TTL_SECONDS,
    IDEMPOTENCY_TTL_SECONDS,
    IN_FLIGHT,
    ReplayedResponse,
    claim,
    complete,
    release,
    storage_key,
)

KEY = "k"


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis()


class _Rendezvous:
    """Hold every caller until all of them have arrived.

    The interleavings under test are the ones where two callers are at the same
    instruction at the same time. Without a barrier that is left to the event
    loop, and an ordering the loop happens to pick is not an assertion.
    """

    def __init__(self, parties: int) -> None:
        self._parties = parties
        self._arrived = 0
        self._open = asyncio.Event()

    async def wait(self) -> None:
        self._arrived += 1
        if self._arrived >= self._parties:
            self._open.set()
        await self._open.wait()


class TestTheThreeStates:
    @pytest.mark.asyncio
    async def test_an_unseen_key_is_claimed(self, redis):
        assert (await claim(redis, KEY)).token

    @pytest.mark.asyncio
    async def test_a_second_claim_reports_in_flight(self, redis):
        """The state that must not collapse into 'unseen': two retries racing
        would otherwise both proceed and both create."""
        await claim(redis, KEY)

        second = await claim(redis, KEY)

        assert second.in_flight
        assert second.token is None

    @pytest.mark.asyncio
    async def test_a_completed_key_replays_the_original_response(self, redis):
        held = await claim(redis, KEY)
        await complete(redis, KEY, held.token, ReplayedResponse(status_code=201, body=b'{"id": "abc"}'))

        replayed = (await claim(redis, KEY)).replay

        assert replayed is not None
        assert replayed.status_code == 201
        assert replayed.body == b'{"id": "abc"}'

    @pytest.mark.asyncio
    async def test_a_released_key_is_claimable_again(self, redis):
        """A failed create is not a completed one: holding the key would make
        the retry the caller must perform impossible until the TTL expires."""
        held = await claim(redis, KEY)
        assert await release(redis, KEY, held.token) is True

        assert (await claim(redis, KEY)).token


class TestKeyScoping:
    def test_two_actors_using_the_same_key_do_not_collide(self):
        assert storage_key("u1", "POST", "/api/tasks", "k") != storage_key("u2", "POST", "/api/tasks", "k")

    def test_one_actor_reusing_a_key_across_routes_does_not_collide(self):
        assert storage_key("u1", "POST", "/api/tasks", "k") != storage_key("u1", "POST", "/api/goals", "k")

    def test_the_same_request_produces_the_same_key(self):
        """The contrast: scoping must not make a legitimate retry look new."""
        assert storage_key("u1", "POST", "/api/tasks", "k") == storage_key("u1", "POST", "/api/tasks", "k")

    def test_the_client_key_never_reaches_the_keyspace_verbatim(self):
        """A caller-supplied value is hashed, so a hostile or huge key cannot
        shape the Redis keyspace."""
        key = storage_key("u1", "POST", "/api/tasks", "../../etc/passwd\n\r")

        assert "etc/passwd" not in key
        assert key.startswith("idempotency:")


class TestMalformedRecords:
    @pytest.mark.asyncio
    async def test_a_corrupt_record_is_treated_as_in_flight_not_replayed(self, redis):
        """A wrong replay is worse than a retry: garbage must not resurrect as
        a response the caller believes."""
        await redis.set(KEY, "{not json")

        assert (await claim(redis, KEY)).in_flight

    @pytest.mark.asyncio
    async def test_a_record_missing_its_status_is_not_replayed(self, redis):
        await redis.set(KEY, '{"body": "{}"}')

        assert (await claim(redis, KEY)).in_flight


class TestTheExpiringClaimRace:
    """Both callers lose `SET NX`, then the claim they lost to expires."""

    @pytest.mark.asyncio
    async def test_two_callers_finding_the_key_expired_do_not_both_proceed(self, redis, monkeypatch):
        """The interleaving that made the store useless.

        Both callers lose the atomic claim, both then read a key that has just
        expired, and reporting 'unseen' there hands *both* of them permission to
        create. Retrying the atomic claim is the only answer exactly one of them
        can win.
        """
        await redis.set(KEY, f"{IN_FLIGHT}:about-to-expire")
        gate = _Rendezvous(2)
        original_get = redis.get
        reads = {"n": 0}

        async def _read_after_the_claim_expired(name):
            await gate.wait()  # neither caller reads until both have lost SET NX
            reads["n"] += 1
            if reads["n"] == 1:
                await redis.delete(name)  # the claim they lost to expires, here
            return await original_get(name)

        monkeypatch.setattr(redis, "get", _read_after_the_claim_expired)

        first, second = await asyncio.gather(claim(redis, KEY), claim(redis, KEY))

        holders = [outcome for outcome in (first, second) if outcome.token]
        assert len(holders) == 1, "both callers were told to proceed — both would create"
        assert [first.in_flight, second.in_flight].count(True) == 1
        assert reads["n"] >= 2, "the interleaving under test did not happen"

    @pytest.mark.asyncio
    async def test_a_key_that_stays_free_is_still_claimed_immediately(self, redis):
        """The contrast: the retry loop must not turn an unseen key into a
        refusal. Over-blocking here would 409 a caller who has never been seen."""
        outcome = await claim(redis, KEY)

        assert outcome.token
        assert outcome.in_flight is False

    @pytest.mark.asyncio
    async def test_a_lone_caller_after_a_genuine_expiry_still_claims(self, redis, monkeypatch):
        """One caller, whose predecessor's claim expired: it must proceed, not
        be told the key is in flight."""
        await redis.set(KEY, f"{IN_FLIGHT}:gone")
        original_get = redis.get

        async def _vanished(name):
            await redis.delete(name)
            return await original_get(name)

        monkeypatch.setattr(redis, "get", _vanished)

        assert (await claim(redis, KEY)).token


class TestFencing:
    """A request may outlive its claim; it may not corrupt its successor's."""

    @pytest.mark.asyncio
    async def test_a_lapsed_request_cannot_publish_over_a_successors_claim(self, redis):
        """Forced interleaving: the slow request is held until its claim has
        lapsed *and* a successor has claimed and completed the same key.

        Without fencing the slow request's `complete` overwrites the successor's
        record, and every later caller replays a response describing a resource
        the successor never created.
        """
        slow = await claim(redis, KEY)
        successor_done = asyncio.Event()

        async def _slow_request_finally_completes():
            await successor_done.wait()
            return await complete(redis, KEY, slow.token, ReplayedResponse(201, b'{"id": "slow"}'))

        async def _successor():
            await redis.delete(KEY)  # the slow request's claim lapsed
            held = await claim(redis, KEY)
            assert held.token, "the successor could not claim a key whose holder had lapsed"
            assert await complete(redis, KEY, held.token, ReplayedResponse(201, b'{"id": "successor"}'))
            successor_done.set()

        stored, _ = await asyncio.gather(_slow_request_finally_completes(), _successor())

        assert stored is False, "a lapsed request published its response over a successor's"
        replayed = (await claim(redis, KEY)).replay
        assert replayed is not None and replayed.body == b'{"id": "successor"}'

    @pytest.mark.asyncio
    async def test_a_lapsed_request_cannot_release_a_successors_claim(self, redis):
        """The other half: deleting the successor's claim would let a third
        caller create as well."""
        lapsed = await claim(redis, KEY)
        await redis.delete(KEY)
        successor = await claim(redis, KEY)

        dropped = await release(redis, KEY, lapsed.token)

        assert dropped is False, "a lapsed request deleted a live claim"
        assert (await claim(redis, KEY)).in_flight, "a third caller could now create as well"
        assert await release(redis, KEY, successor.token) is True

    @pytest.mark.asyncio
    async def test_the_holder_is_never_blocked_by_its_own_token(self, redis):
        """The contrast: fencing must refuse only a stale writer. The caller
        that still holds the claim completes and releases as it always did."""
        held = await claim(redis, KEY)

        assert await complete(redis, KEY, held.token, ReplayedResponse(201, b'{"id": "ok"}')) is True

        again = await claim(redis, KEY)
        assert again.replay is not None and again.replay.body == b'{"id": "ok"}'

    @pytest.mark.asyncio
    async def test_two_sequential_claims_get_different_tokens(self, redis):
        """A token that repeated would fence nothing."""
        first = await claim(redis, KEY)
        await release(redis, KEY, first.token)
        second = await claim(redis, KEY)

        assert first.token != second.token


class TestTheConfiguredTTLIsApplied:
    """The TTL is the only thing bounding the keyspace, and nothing asserted it.

    A replay that never expires is a slow leak; one that expires immediately is
    a feature that silently stops working. Both look identical to a test that
    checks the payload alone.
    """

    @pytest.mark.asyncio
    async def test_a_completed_record_carries_the_replay_ttl(self, redis):
        outcome = await claim(redis, "k")
        await complete(redis, "k", str(outcome.token), ReplayedResponse(status_code=201, body=b"{}"))

        ttl = await redis.ttl("k")

        assert 0 < ttl <= IDEMPOTENCY_TTL_SECONDS
        assert ttl > IDEMPOTENCY_CLAIM_TTL_SECONDS, "a completed record must outlive the in-flight claim"

    @pytest.mark.asyncio
    async def test_an_in_flight_claim_carries_the_shorter_claim_ttl(self, redis):
        """The contrast: a claim that outlived its request would wedge the key."""
        await claim(redis, "k")

        ttl = await redis.ttl("k")

        assert 0 < ttl <= IDEMPOTENCY_CLAIM_TTL_SECONDS


class TestTheClaimTTLIsTheConfiguredOne:
    """A TTL was used is not the same claim as *the configured* TTL was used.

    The existing assertion bounds the claim TTL by its own constant, which holds
    for any value the code happens to pass — including a hard-coded one. Pinning
    it to the configured number is the reach-floor argument applied to a
    constant (#15778 review).
    """

    @pytest.mark.asyncio
    async def test_the_claim_carries_exactly_the_configured_ttl(self, redis, monkeypatch):
        await claim(redis, "k")

        ttl = await redis.ttl("k")

        # fakeredis does not advance time between the two calls, so this is the
        # exact value rather than a bound.
        assert ttl == IDEMPOTENCY_CLAIM_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_the_completed_record_carries_exactly_the_replay_ttl(self, redis):
        held = await claim(redis, "k")
        await complete(redis, "k", str(held.token), ReplayedResponse(status_code=201, body=b"{}"))

        assert await redis.ttl("k") == IDEMPOTENCY_TTL_SECONDS
