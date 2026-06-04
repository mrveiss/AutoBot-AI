#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for config/validation.py — Issue #3880.

Covers the two bugs fixed in #3880:
1. ``if not value`` falsely rejected falsy-but-valid values (0, False, "0", "").
2. ``memory.redis.host`` was unconditionally required; it must be gated on
   ``memory.redis.enabled``.
"""

import os
import sys
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.validation import validate_startup_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_config(**overrides: Any) -> Dict[str, Any]:
    """Return a minimal valid config, with optional dot-notation overrides applied."""
    cfg: Dict[str, Any] = {
        "backend": {
            "server_host": "0.0.0.0",  # nosec B104 - intentional bind to all interfaces for service/test
            "server_port": 8001,
        },
        "memory": {
            "redis": {
                "enabled": True,
                "host": "127.0.0.1",
                "port": 6379,
            }
        },
    }
    for dotted, val in overrides.items():
        parts = dotted.split(".")
        node = cfg
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = val
    return cfg


# ---------------------------------------------------------------------------
# 1.  Truthiness fix — values of 0, False, "0", "" must NOT be rejected
# ---------------------------------------------------------------------------


class TestFalsyValidValues:
    """Ensure ``is None`` (not truthiness) is used for required-key checks."""

    def test_server_host_numeric_string_zero(self):
        """'0' is an unusual but syntactically valid host; must not be rejected."""
        cfg = _base_config(**{"backend.server_host": "0"})
        result = validate_startup_config(cfg)
        host_errors = [e for e in result.errors if "server_host" in e]
        assert host_errors == [], f"Unexpected errors: {host_errors}"

    def test_server_host_empty_string_is_still_present(self):
        """An empty string is not None — it is present (albeit unusual)."""
        cfg = _base_config(**{"backend.server_host": ""})
        result = validate_startup_config(cfg)
        host_errors = [e for e in result.errors if "server_host" in e]
        assert host_errors == [], "Empty string must not be treated as missing; got: " + str(host_errors)

    def test_redis_host_zero_string_not_rejected(self):
        """Redis host of '0' must not trigger a missing-key error."""
        cfg = _base_config(**{"memory.redis.host": "0"})
        result = validate_startup_config(cfg)
        redis_errors = [e for e in result.errors if "redis.host" in e]
        assert redis_errors == [], f"Unexpected errors: {redis_errors}"

    def test_server_host_none_is_rejected(self):
        """Only an actual None value must produce a required-key error."""
        cfg = _base_config()
        cfg["backend"]["server_host"] = None
        result = validate_startup_config(cfg)
        host_errors = [e for e in result.errors if "server_host" in e]
        assert len(host_errors) == 1

    def test_server_host_missing_key_is_rejected(self):
        """A completely absent key must produce a required-key error."""
        cfg = _base_config()
        del cfg["backend"]["server_host"]
        result = validate_startup_config(cfg)
        host_errors = [e for e in result.errors if "server_host" in e]
        assert len(host_errors) == 1


# ---------------------------------------------------------------------------
# 2.  Redis host gated on memory.redis.enabled
# ---------------------------------------------------------------------------


class TestRedisHostConditionalRequirement:
    """memory.redis.host must only be required when memory.redis.enabled is True."""

    def test_redis_enabled_true_and_host_present_is_valid(self):
        cfg = _base_config()
        result = validate_startup_config(cfg)
        redis_errors = [e for e in result.errors if "redis.host" in e]
        assert redis_errors == []

    def test_redis_enabled_true_and_host_missing_is_invalid(self):
        cfg = _base_config(**{"memory.redis.enabled": True})
        cfg["memory"]["redis"]["host"] = None
        result = validate_startup_config(cfg)
        redis_errors = [e for e in result.errors if "redis.host" in e]
        assert len(redis_errors) == 1

    def test_redis_disabled_and_host_missing_is_valid(self):
        """When Redis is disabled, missing host must NOT raise an error."""
        cfg = _base_config(**{"memory.redis.enabled": False})
        del cfg["memory"]["redis"]["host"]
        result = validate_startup_config(cfg)
        redis_errors = [e for e in result.errors if "redis.host" in e]
        assert redis_errors == [], "Redis disabled — host must not be required. Errors: " + str(redis_errors)

    def test_redis_disabled_and_host_none_is_valid(self):
        """None host with Redis disabled must also pass."""
        cfg = _base_config(**{"memory.redis.enabled": False})
        cfg["memory"]["redis"]["host"] = None
        result = validate_startup_config(cfg)
        redis_errors = [e for e in result.errors if "redis.host" in e]
        assert redis_errors == []

    def test_redis_enabled_flag_absent_defaults_to_required(self):
        """When the enabled flag is absent, treat Redis as enabled (backward compat)."""
        cfg = _base_config()
        del cfg["memory"]["redis"]["enabled"]
        # host is still present — should pass
        result = validate_startup_config(cfg)
        redis_errors = [e for e in result.errors if "redis.host" in e]
        assert redis_errors == []

    def test_redis_enabled_flag_absent_and_host_missing_is_invalid(self):
        """Missing enabled flag + missing host must fail (backward-compat guard)."""
        cfg = _base_config()
        del cfg["memory"]["redis"]["enabled"]
        del cfg["memory"]["redis"]["host"]
        result = validate_startup_config(cfg)
        redis_errors = [e for e in result.errors if "redis.host" in e]
        assert len(redis_errors) == 1


# ---------------------------------------------------------------------------
# 3.  Fully valid minimal config must produce zero errors
# ---------------------------------------------------------------------------


def test_valid_config_produces_no_errors():
    cfg = _base_config()
    result = validate_startup_config(cfg)
    assert result.valid is True
    assert result.errors == []
