# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unified config manager coverage, unwrapped from its #15189 swallow.

Every one of the ten checks below used to live in one giant
``test_config_consolidation`` body, wrapped ``try: assert ...; except Exception:
return False``. The bare except caught the ``AssertionError`` each assert could
raise, so pytest saw a function that always returned a boolean and never
propagated a failure — one of the ten sites counted against
``_SWALLOWED_ASSERTIONS["autobot-backend"]`` in
``repo_tests/tests_that_return_instead_of_asserting_test.py`` (#15189).

Unwrapping it did not just make the asserts able to fire — most of them had
silently drifted from the module they claim to check, because the swallow hid
every one of nine remaining checks behind the first failure:

* ``unified_config_manager._get_default_config()`` never existed on
  ``ConfigManager``; the real function is the module-level
  ``config.defaults.get_default_config()``. Every check that called it
  (sections, multimodal, npu, security) was one `AttributeError` away from
  running at all, and none of them ran past the first one to raise it.
* The multimodal check asserted ``voice.confidence_threshold == 0.8``.
  ``config/defaults.py`` fixed that value to ``0.7`` under #13207 (the
  lookup that read it was pointed at a section that did not exist, so 0.8
  was never actually in effect) and left a comment saying so. The test's
  0.8 was the stale pre-fix number.
* The "environment variable handling" check read `os.getenv` directly and
  asserted nothing about it either way — printing a found value was its
  only behaviour. It is replaced below with a real round trip through
  ``config.loader.apply_env_overrides``.

None of that is a regression introduced by this rewrite; it is what the
swallow already contained and could not report.
"""

from __future__ import annotations

import pytest

from config import unified_config_manager
from config.defaults import get_default_config
from config.loader import apply_env_overrides

EXPECTED_DEFAULT_SECTIONS = (
    "backend",
    "deployment",
    "data",
    "redis",
    "memory",
    "multimodal",
    "npu",
    "hardware",
    "system",
    "network",
    "task_transport",
    "security",
    "ui",
    "chat",
    "logging",
)


def test_basic_config_loading() -> None:
    """``to_dict()`` returns the live, non-empty runtime config."""
    config = unified_config_manager.to_dict()
    assert isinstance(config, dict), "to_dict() should return a dictionary"
    assert len(config) > 0, "the runtime config should not be empty"


def test_default_config_completeness() -> None:
    """Every section the rest of this module depends on is present."""
    defaults = get_default_config()
    missing = [section for section in EXPECTED_DEFAULT_SECTIONS if section not in defaults]
    assert not missing, f"missing expected default sections: {missing}"


def test_sensitive_data_filtering() -> None:
    """Passwords and API keys are redacted; ordinary fields are untouched."""
    test_data = {
        "redis": {"host": "localhost", "password": "secret123", "port": 6379},
        "api": {"endpoint": "http://api.example.com", "api_key": "key123"},
    }
    filtered = unified_config_manager._filter_sensitive_data(test_data)
    assert filtered["redis"]["password"] == "***REDACTED***"
    assert filtered["api"]["api_key"] == "***REDACTED***"
    assert filtered["redis"]["host"] == "localhost"
    assert filtered["redis"]["port"] == 6379


@pytest.mark.asyncio
async def test_async_config_operations(tmp_path, monkeypatch) -> None:
    """Async save/load round-trips through disk without touching the repo.

    ``ConfigManager.config_dir`` resolves from ``PATH.PROJECT_ROOT``, which is
    this repo's root when tests run from it — the original body wrote a real
    ``config/test.json`` at the repo root on every execution. `monkeypatch`
    redirects it to `tmp_path` for the duration of this test only, restored
    automatically afterward, so no state leaks to a sibling test (#13224's
    class of defect).
    """
    monkeypatch.setattr(unified_config_manager, "config_dir", tmp_path)
    loaded = await unified_config_manager.load_config_async("test", use_cache=False)
    assert isinstance(loaded, dict), "async load should return a dictionary"

    payload = {"test_key": "test_value", "timestamp": "2025-11-11"}
    await unified_config_manager.save_config_async("test", payload)
    reloaded = await unified_config_manager.load_config_async("test", use_cache=False)
    assert reloaded.get("test_key") == "test_value", "saved data should be retrievable"


def test_redis_cache_key_generation() -> None:
    """The cache key carries the configured prefix and the config type."""
    cache_key = unified_config_manager._get_redis_cache_key("test")
    assert cache_key.startswith("config:"), "cache key should have the correct prefix"
    assert "test" in cache_key, "cache key should contain the config type"


def test_nested_config_access() -> None:
    """``get_nested`` reaches a dict section and a leaf value."""
    backend_config = unified_config_manager.get_nested("backend.llm", {})
    assert isinstance(backend_config, dict), "nested config should be a dictionary"

    redis_host = unified_config_manager.get_nested("redis.host", "default")
    assert redis_host is not None, "should retrieve the nested Redis host"


def test_environment_variable_overrides_apply_to_config(monkeypatch) -> None:
    """``AUTOBOT_`` env vars land at the mapped path, converted to the right type.

    The original check only printed whichever of three env vars happened to
    be set in the OS environment and asserted nothing — the vacuous "return
    True either way" shape this file exists to remove, just without the
    swallow to hide it. `apply_env_overrides` is the real consumer.
    """
    monkeypatch.setenv("AUTOBOT_BACKEND_PORT", "9999")
    overridden = apply_env_overrides({})
    assert overridden == {
        "backend": {"server_port": 9999}
    }, "AUTOBOT_BACKEND_PORT should override backend.server_port as an int"


def test_multimodal_config_consolidation() -> None:
    """Vision/voice/context thresholds match the values #13207 actually set."""
    multimodal = get_default_config()["multimodal"]
    assert "vision" in multimodal
    assert "voice" in multimodal
    assert "context" in multimodal

    assert multimodal["vision"]["confidence_threshold"] == 0.7
    # 0.7, not the pre-#13207 0.8 this test used to assert — see module docstring.
    assert multimodal["voice"]["confidence_threshold"] == 0.7
    assert multimodal["context"]["decision_threshold"] == 0.9


def test_npu_config_consolidation() -> None:
    """NPU defaults come up disabled, on CPU, at max optimization."""
    npu = get_default_config()["npu"]
    assert npu["enabled"] is False, "NPU should be disabled by default"
    assert npu["device"] == "CPU", "default device should be CPU"
    assert npu["optimization_level"] == "PERFORMANCE"


def test_security_config_consolidation() -> None:
    """Sandboxing is on and destructive commands are blocked by default."""
    security = get_default_config()["security"]
    assert security["enable_sandboxing"] is True
    assert "rm -rf" in security["blocked_commands"]
