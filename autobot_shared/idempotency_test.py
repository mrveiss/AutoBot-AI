# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The replay store's three states (#15778).

Against a real fakeredis rather than a mock: `SET NX` is the whole mechanism —
a stub that returns whatever the test wants would assert only that the code
calls the function it obviously calls.
"""

from __future__ import annotations

import fakeredis.aioredis
import pytest

from autobot_shared.idempotency import (
    IN_FLIGHT,
    ReplayedResponse,
    claim,
    complete,
    release,
    storage_key,
)


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis()


class TestTheThreeStates:
    @pytest.mark.asyncio
    async def test_an_unseen_key_is_claimed(self, redis):
        assert await claim(redis, "k") is None

    @pytest.mark.asyncio
    async def test_a_second_claim_reports_in_flight(self, redis):
        """The state that must not collapse into 'unseen': two retries racing
        would otherwise both proceed and both create."""
        await claim(redis, "k")

        assert await claim(redis, "k") == IN_FLIGHT

    @pytest.mark.asyncio
    async def test_a_completed_key_replays_the_original_response(self, redis):
        await claim(redis, "k")
        await complete(redis, "k", ReplayedResponse(status_code=201, body='{"id": "abc"}'))

        replayed = await claim(redis, "k")

        assert isinstance(replayed, ReplayedResponse)
        assert replayed.status_code == 201
        assert replayed.body == '{"id": "abc"}'

    @pytest.mark.asyncio
    async def test_a_released_key_is_claimable_again(self, redis):
        """A failed create is not a completed one: holding the key would make
        the retry the caller must perform impossible until the TTL expires."""
        await claim(redis, "k")
        await release(redis, "k")

        assert await claim(redis, "k") is None


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
        await redis.set("k", "{not json")

        assert await claim(redis, "k") == IN_FLIGHT

    @pytest.mark.asyncio
    async def test_a_record_missing_its_status_is_not_replayed(self, redis):
        await redis.set("k", '{"body": "{}"}')

        assert await claim(redis, "k") == IN_FLIGHT


class TestClaimExpiry:
    @pytest.mark.asyncio
    async def test_a_claim_that_vanished_between_set_and_get_reads_as_unseen(self, redis, monkeypatch):
        """Refusing there would strand a caller behind a key that no longer exists."""
        await claim(redis, "k")
        original_get = redis.get

        async def _vanished(name):
            await redis.delete(name)
            return await original_get(name)

        monkeypatch.setattr(redis, "get", _vanished)

        assert await claim(redis, "k") is None
