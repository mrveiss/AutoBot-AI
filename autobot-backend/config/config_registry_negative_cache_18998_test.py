# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ConfigRegistry remembers that Redis holds nothing for a key (#18998).

Redis calls are counted on a fake client reached through the real
``_fetch_from_redis``; time is advanced through the ``config.registry._now`` seam,
never slept.
"""

import os
from unittest.mock import patch

import pytest

from config import registry as registry_module
from config.registry import ConfigRegistry


class _FakeRedis:
    def __init__(self, store=None):
        self.store = dict(store or {})
        self.gets = 0
        self.sets = []

    def get(self, key):
        self.gets += 1
        return self.store.get(key)

    def set(self, key, value):
        self.sets.append((key, value))
        self.store[key] = value


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def redis():
    ConfigRegistry.clear_cache()
    fake = _FakeRedis()
    clock = _Clock()
    ConfigRegistry._redis_client = fake
    with patch.object(registry_module, "_now", clock), patch.dict(os.environ, {}, clear=True):
        fake.clock = clock
        yield fake
    ConfigRegistry.clear_cache()


class TestMissIsCachedWithinTheTtl:
    def test_second_read_of_a_missing_key_makes_no_redis_call(self, redis):
        """Reverting ``_remember_miss(key)`` in ``get`` makes this 2, not 1."""
        ConfigRegistry.get("absent.key", "d")
        ConfigRegistry.get("absent.key", "d")
        assert redis.gets == 1

    def test_read_after_the_ttl_asks_redis_again(self, redis):
        """Reverting the ``< cls._ttl_seconds`` bound in ``_is_miss_valid`` leaves this at 1."""
        ConfigRegistry.get("absent.key")
        redis.clock.t += ConfigRegistry._ttl_seconds + 1
        ConfigRegistry.get("absent.key")
        assert redis.gets == 2

    def test_a_key_set_elsewhere_is_visible_after_the_ttl(self, redis):
        """Same line as the previous test: the expiry is what lets a later value in."""
        assert ConfigRegistry.get("later.key") is None
        redis.store["autobot:config:later.key"] = "now-here"
        assert ConfigRegistry.get("later.key") is None  # still inside the TTL
        redis.clock.t += ConfigRegistry._ttl_seconds + 1
        assert ConfigRegistry.get("later.key") == "now-here"

    def test_different_caller_defaults_stay_correct_on_a_cached_miss(self, redis):
        """Reverting to cache the resolved caller default makes the second call return "a"."""
        assert ConfigRegistry.get("absent.key", "a") == "a"
        assert ConfigRegistry.get("absent.key", "b") == "b"
        assert redis.gets == 1

    def test_env_set_after_a_cached_miss_is_still_seen(self, redis):
        """Env is re-resolved on every read; caching the env tier would pin the old answer."""
        assert ConfigRegistry.get("some.knob", "d") == "d"
        with patch.dict(os.environ, {"AUTOBOT_SOME_KNOB": "from-env"}):
            assert ConfigRegistry.get("some.knob", "d") == "from-env"
        assert redis.gets == 1


class TestSetInvalidates:
    def test_set_clears_a_cached_miss(self, redis):
        """Reverting ``cls._miss_timestamps.pop`` in ``_update_cache`` leaves the miss live,
        but the positive cache entry from set() still answers; so assert on the miss table."""
        ConfigRegistry.get("will.set")
        assert "will.set" in ConfigRegistry._miss_timestamps
        ConfigRegistry.set("will.set", "v")
        assert "will.set" not in ConfigRegistry._miss_timestamps
        assert ConfigRegistry.get("will.set") == "v"

    def test_refresh_clears_a_cached_miss_and_rereads(self, redis):
        """Reverting the ``_miss_timestamps.pop`` in ``refresh`` makes refresh read nothing from Redis."""
        ConfigRegistry.get("r.key")
        redis.store["autobot:config:r.key"] = "fresh"
        assert ConfigRegistry.refresh("r.key") == "fresh"
        assert redis.gets == 2

    def test_clear_cache_forgets_misses(self, redis):
        """Reverting ``_miss_timestamps.clear()`` in ``clear_cache`` leaves the entry."""
        ConfigRegistry.get("m.key")
        ConfigRegistry.clear_cache()
        assert ConfigRegistry._miss_timestamps == {}

    def test_dict_values_are_stored_as_json(self, redis):
        """Reverting the ``json.dumps`` branch in ``set`` stores a Python repr."""
        ConfigRegistry.set("llm.tiered_routing", {"enabled": False})
        assert redis.sets == [("autobot:config:llm.tiered_routing", '{"enabled": false}')]


class _RaisingRedis(_FakeRedis):
    def get(self, key):
        self.gets += 1
        raise ConnectionError("boom")


class TestFailedGetIsNotAMiss:
    def test_a_raising_get_is_not_remembered_and_the_next_read_asks_again(self, redis):
        """Reverting ``return _FETCH_FAILED`` to ``return None`` records a miss and hides a real
        value for the TTL; ``redis.gets`` would stay 1 on the second read."""
        failing = _RaisingRedis()
        ConfigRegistry._redis_client = failing
        assert ConfigRegistry.get("err.key", "d") == "d"
        assert ConfigRegistry._miss_timestamps == {}
        assert ConfigRegistry.get("err.key", "d") == "d"
        assert failing.gets == 2

    def test_a_nil_get_is_remembered_and_the_next_read_does_not_ask(self, redis):
        """Contrast: a GET that succeeds with nil records the miss and is not repeated."""
        assert ConfigRegistry.get("nil.key", "d") == "d"
        assert "nil.key" in ConfigRegistry._miss_timestamps
        assert ConfigRegistry.get("nil.key", "d") == "d"
        assert redis.gets == 1

    def test_a_value_is_seen_once_redis_recovers_from_a_failed_get(self, redis):
        """The failed read must not hide the value Redis holds once it answers again."""
        ConfigRegistry._redis_client = _RaisingRedis()
        ConfigRegistry.get("heal.key")
        ConfigRegistry._redis_client = redis
        redis.store["autobot:config:heal.key"] = "real"
        assert ConfigRegistry.get("heal.key") == "real"


class TestNoClientNoNegativeCache:
    def test_a_miss_without_a_redis_client_is_not_remembered(self):
        """Reverting the ``_redis_client is None`` guard in ``_remember_miss`` hides a value for a
        full TTL after Redis comes back."""
        ConfigRegistry.clear_cache()
        with patch.object(ConfigRegistry, "_fetch_from_redis", return_value=None):
            ConfigRegistry.get("x.key")
        assert ConfigRegistry._miss_timestamps == {}
        ConfigRegistry.clear_cache()
