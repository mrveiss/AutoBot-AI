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


def test_no_3600_literal_in_module_source():
    """Pin the regression: original bug was `setex(key, 3600, ...)`."""
    import inspect

    import chat_history.cache as cache_mod

    src = inspect.getsource(cache_mod.CacheMixin._async_cache_session)
    assert "3600" not in src, "TTL must not be a 3600 literal in _async_cache_session"


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
