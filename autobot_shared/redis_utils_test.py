# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Direct tests for the shared Redis decode helpers (#13290).

``decode_redis_list`` was added for ``FT.INFO`` walking and was previously
covered only indirectly, through two setup scripts. It is in ``autobot_shared``
and therefore reachable by any caller, so it gets its own coverage here.
"""

import pytest

from autobot_shared.redis_utils import (
    COMPARE_AND_DELETE_LUA,
    COMPARE_AND_PEXPIRE_LUA,
    decode_redis_list,
    decode_redis_value,
    delete_if_value,
    expire_if_value,
)


class TestDecodeRedisValue:
    """Leaf decoding."""

    def test_bytes_are_decoded(self):
        assert decode_redis_value(b"hello") == "hello"

    def test_str_passes_through(self):
        assert decode_redis_value("hello") == "hello"

    def test_none_passes_through(self):
        assert decode_redis_value(None) is None


class TestDecodeRedisList:
    """Recursive RESP-array decoding."""

    def test_flat_list_of_bytes(self):
        assert decode_redis_list([b"a", b"b"]) == ["a", "b"]

    def test_nested_lists_are_walked_to_every_leaf(self):
        assert decode_redis_list([b"a", ["b", [b"c"]]]) == ["a", ["b", ["c"]]]

    def test_already_decoded_input_is_not_double_decoded(self):
        assert decode_redis_list(["a", ["b"]]) == ["a", ["b"]]

    def test_non_str_scalars_pass_through(self):
        assert decode_redis_list([1, 1.5, None]) == [1, 1.5, None]

    def test_bare_scalar_is_delegated_to_decode_redis_value(self):
        assert decode_redis_list(b"solo") == "solo"
        assert decode_redis_list(None) is None

    def test_empty_list(self):
        assert decode_redis_list([]) == []

    def test_ft_info_shape_is_decoded_end_to_end(self):
        """The shape this helper exists for: a nested FT.INFO reply."""
        reply = [b"index_name", b"llama_index", b"attributes", [[b"type", b"VECTOR", b"DIM", b"768"]]]

        assert decode_redis_list(reply) == [
            "index_name",
            "llama_index",
            "attributes",
            [["type", "VECTOR", "DIM", "768"]],
        ]


class TestDeleteIfValue:
    """The atomic release-if-owner, against fakeredis's real Lua engine."""

    @staticmethod
    def _redis():
        import fakeredis

        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.mark.asyncio
    async def test_a_matching_holder_is_deleted(self):
        redis = self._redis()
        await redis.set("fence", "agent-a")
        assert await delete_if_value(redis, "fence", "agent-a") is True
        assert await redis.get("fence") is None

    @pytest.mark.asyncio
    async def test_a_newer_holder_is_left_alone(self):
        redis = self._redis()
        await redis.set("fence", "agent-newer")
        assert await delete_if_value(redis, "fence", "agent-a") is False
        assert await redis.get("fence") == "agent-newer"

    @pytest.mark.asyncio
    async def test_an_absent_key_is_not_an_error(self):
        assert await delete_if_value(self._redis(), "fence", "agent-a") is False

    @pytest.mark.asyncio
    async def test_the_delete_is_one_script_not_a_client_side_get(self):
        redis = self._redis()
        await redis.set("fence", "agent-a")
        script_calls = []
        real_eval = redis.eval

        async def spy(script, numkeys, *args):
            script_calls.append((script, numkeys, args))
            return await real_eval(script, numkeys, *args)

        redis.eval = spy
        await delete_if_value(redis, "fence", "agent-a")
        assert script_calls == [(COMPARE_AND_DELETE_LUA, 1, ("fence", "agent-a"))]


#: Lock TTLs for the heartbeat tests: a short one the holder starts with, and the one a heartbeat sets.
_START_TTL_MS = 1_000
_NEWER_HOLDER_TTL_MS = 5_000
_HEARTBEAT_TTL_MS = 60_000


class TestExpireIfValue:
    """The atomic heartbeat-if-owner, against fakeredis's real Lua engine (#19379)."""

    @staticmethod
    def _redis():
        import fakeredis

        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.mark.asyncio
    async def test_a_matching_holder_gets_the_new_ttl(self):
        redis = self._redis()
        await redis.set("lock", "owner-a", px=_START_TTL_MS)
        assert await expire_if_value(redis, "lock", "owner-a", _HEARTBEAT_TTL_MS) is True
        assert _START_TTL_MS < await redis.pttl("lock") <= _HEARTBEAT_TTL_MS

    @pytest.mark.asyncio
    async def test_a_newer_holder_keeps_its_own_ttl(self):
        redis = self._redis()
        await redis.set("lock", "owner-newer", px=_NEWER_HOLDER_TTL_MS)
        assert await expire_if_value(redis, "lock", "owner-a", _HEARTBEAT_TTL_MS) is False
        assert await redis.get("lock") == "owner-newer" and await redis.pttl("lock") <= _NEWER_HOLDER_TTL_MS

    @pytest.mark.asyncio
    async def test_an_absent_key_is_not_recreated(self):
        redis = self._redis()
        assert await expire_if_value(redis, "lock", "owner-a", _HEARTBEAT_TTL_MS) is False
        assert await redis.get("lock") is None

    @pytest.mark.asyncio
    async def test_the_extend_is_one_script_not_a_client_side_get(self):
        redis = self._redis()
        await redis.set("lock", "owner-a")
        script_calls = []
        real_eval = redis.eval

        async def spy(script, numkeys, *args):
            script_calls.append((script, numkeys, args))
            return await real_eval(script, numkeys, *args)

        redis.eval = spy
        await expire_if_value(redis, "lock", "owner-a", _HEARTBEAT_TTL_MS)
        assert script_calls == [(COMPARE_AND_PEXPIRE_LUA, 1, ("lock", "owner-a", _HEARTBEAT_TTL_MS))]
