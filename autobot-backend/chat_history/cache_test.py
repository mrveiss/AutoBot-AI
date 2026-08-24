# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#6743: TTL resolution tests for chat_history.cache.

Pin the regression: chat:session:* keys must use a configurable TTL with
24h default and `AUTOBOT_CHAT_SESSION_CACHE_TTL` env-var override. See AC
#4 of issue #6743.
"""

import importlib
import logging
import os

import pytest

from autobot_shared.ssot_config import config


def _reload_cache_with_env(env_value):
    """Reload cache module with given env-var value (None = unset)."""
    if env_value is None:
        os.environ.pop("AUTOBOT_CHAT_SESSION_CACHE_TTL", None)
    else:
        config.misc.chat_session_cache_ttl = env_value
    import chat_history.cache as cache_mod

    importlib.reload(cache_mod)
    return cache_mod


@pytest.fixture(autouse=True)
def _restore_env():
    saved = config.misc.chat_session_cache_ttl
    yield
    if saved is None:
        os.environ.pop("AUTOBOT_CHAT_SESSION_CACHE_TTL", None)
    else:
        config.misc.chat_session_cache_ttl = saved
    import chat_history.cache as cache_mod

    importlib.reload(cache_mod)


def test_default_ttl_is_24_hours():
    cache_mod = _reload_cache_with_env(None)
    assert cache_mod._CHAT_SESSION_CACHE_TTL == 86_400


def test_env_var_override_accepts_positive_int():
    cache_mod = _reload_cache_with_env("7200")
    assert cache_mod._CHAT_SESSION_CACHE_TTL == 7200


def test_env_var_non_integer_falls_back_with_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="chat_history.cache"):
        cache_mod = _reload_cache_with_env("not-a-number")
    assert cache_mod._CHAT_SESSION_CACHE_TTL == 86_400
    assert any("not an integer" in r.getMessage() for r in caplog.records)


def test_env_var_zero_or_negative_falls_back_with_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="chat_history.cache"):
        cache_mod = _reload_cache_with_env("0")
    assert cache_mod._CHAT_SESSION_CACHE_TTL == 86_400
    assert any("must be positive" in r.getMessage() for r in caplog.records)


class TestTheTtlActuallySentToRedis:
    """#6743's bug was ``setex(key, 3600, ...)`` -- a literal that ignored the
    resolved TTL entirely.

    This used to assert ``"3600" not in inspect.getsource(...)`` (#13311),
    which proves nothing about what Redis receives: any other hard-coded
    number passes, and the assertion breaks the moment the call moves into a
    helper. Observe the argument instead.
    """

    @staticmethod
    def _mixin_with_recording_redis(cache_mod):
        """A CacheMixin instance whose Redis records every setex call."""
        mixin = cache_mod.CacheMixin()
        calls: list[tuple] = []

        class _Redis:
            @staticmethod
            def setex(key, ttl, payload):
                calls.append((key, ttl, payload))

        mixin.redis_client = _Redis()
        return mixin, calls

    @pytest.mark.asyncio
    async def test_setex_receives_the_resolved_ttl_not_a_literal(self):
        cache_mod = _reload_cache_with_env(None)
        mixin, calls = self._mixin_with_recording_redis(cache_mod)

        await mixin._async_cache_session("chat:session:abc", {"messages": []})

        assert len(calls) == 1, "session caching must reach Redis exactly once"
        key, ttl, _payload = calls[0]
        assert key == "chat:session:abc"
        assert ttl == cache_mod._CHAT_SESSION_CACHE_TTL == 86_400

    @pytest.mark.asyncio
    async def test_env_override_changes_what_redis_is_told(self):
        """The whole point of the knob: a configured TTL must reach Redis."""
        cache_mod = _reload_cache_with_env("7200")
        mixin, calls = self._mixin_with_recording_redis(cache_mod)

        await mixin._async_cache_session("chat:session:abc", {"messages": []})

        assert calls[0][1] == 7200, "a 3600 (or any hard-coded) literal would show up here"

    @pytest.mark.asyncio
    async def test_payload_is_the_serialized_session(self):
        """Guard the mirror: pinning the TTL must not let the body rot."""
        import json

        cache_mod = _reload_cache_with_env(None)
        mixin, calls = self._mixin_with_recording_redis(cache_mod)

        await mixin._async_cache_session("chat:session:abc", {"messages": [{"role": "user"}]})

        assert json.loads(calls[0][2]) == {"messages": [{"role": "user"}]}


# ---------------------------------------------------------------------------
# _CHAT_RECENT_MAX_ENTRIES resolution tests (#7570)
# ---------------------------------------------------------------------------


def _reload_cache_with_recent_env(env_value):
    """Reload cache module with AUTOBOT_CHAT_RECENT_MAX_ENTRIES set or unset."""
    if env_value is None:
        os.environ.pop("AUTOBOT_CHAT_RECENT_MAX_ENTRIES", None)
    else:
        config.misc.chat_recent_max_entries = env_value
    import chat_history.cache as cache_mod

    importlib.reload(cache_mod)
    return cache_mod


@pytest.fixture(autouse=False)
def _restore_recent_env():
    saved = config.misc.chat_recent_max_entries
    yield
    if saved is None:
        os.environ.pop("AUTOBOT_CHAT_RECENT_MAX_ENTRIES", None)
    else:
        config.misc.chat_recent_max_entries = saved
    import chat_history.cache as cache_mod

    importlib.reload(cache_mod)


def test_recent_default_max_entries_is_1000(_restore_recent_env):
    cache_mod = _reload_cache_with_recent_env(None)
    assert cache_mod._CHAT_RECENT_MAX_ENTRIES == 1000


def test_recent_env_var_override_accepts_positive_int(_restore_recent_env):
    cache_mod = _reload_cache_with_recent_env("500")
    assert cache_mod._CHAT_RECENT_MAX_ENTRIES == 500


def test_recent_env_var_non_integer_falls_back_with_warning(_restore_recent_env, caplog):
    with caplog.at_level(logging.WARNING, logger="chat_history.cache"):
        cache_mod = _reload_cache_with_recent_env("not-a-number")
    assert cache_mod._CHAT_RECENT_MAX_ENTRIES == 1000
    assert any("not an integer" in r.getMessage() for r in caplog.records)


def test_recent_env_var_zero_falls_back_with_warning(_restore_recent_env, caplog):
    with caplog.at_level(logging.WARNING, logger="chat_history.cache"):
        cache_mod = _reload_cache_with_recent_env("0")
    assert cache_mod._CHAT_RECENT_MAX_ENTRIES == 1000
    assert any("must be positive" in r.getMessage() for r in caplog.records)
