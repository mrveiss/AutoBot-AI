#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for the config-sync helpers in api/settings.py.

Covers Issues #3881 (allowlist + depth guard) and #3882 (async file ops).

The endpoint itself (sync_config) requires live DB/auth/ConfigService
dependencies so it is tested via the helper functions:
  - _exceeds_depth       (#3881 depth guard)
  - _SYNC_ALLOWED_TOP_LEVEL_KEYS / _SYNC_MAX_DEPTH / _SYNC_MAX_PAYLOAD_BYTES
  - _atomic_write_json   (#3882 asyncio.to_thread usage)
  - _compute_flat_diff   (regression guard)
  - _count_unchanged_keys
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from api.settings import (
    _SYNC_ALLOWED_TOP_LEVEL_KEYS,
    _SYNC_MAX_DEPTH,
    _SYNC_MAX_PAYLOAD_BYTES,
    _atomic_write_json,
    _compute_flat_diff,
    _count_unchanged_keys,
    _exceeds_depth,
)

# ---------------------------------------------------------------------------
# _exceeds_depth — Issue #3881
# ---------------------------------------------------------------------------


class TestExceedsDepth:
    """_exceeds_depth() rejects payloads that are nested too deeply."""

    def test_flat_dict_not_exceeded(self):
        assert _exceeds_depth({"a": 1, "b": 2}) is False

    def test_depth_at_limit_is_ok(self):
        # Build a dict nested exactly _SYNC_MAX_DEPTH levels deep.
        obj: dict = {}
        node = obj
        for _ in range(_SYNC_MAX_DEPTH):
            node["x"] = {}
            node = node["x"]
        node["leaf"] = "value"
        assert _exceeds_depth(obj) is False

    def test_depth_one_over_limit_is_exceeded(self):
        # One extra level beyond the limit must trigger the guard.
        obj: dict = {}
        node = obj
        for _ in range(_SYNC_MAX_DEPTH + 1):
            node["x"] = {}
            node = node["x"]
        node["leaf"] = "value"
        assert _exceeds_depth(obj) is True

    def test_non_dict_value_not_counted_as_depth(self):
        assert _exceeds_depth({"a": [1, 2, 3]}) is False
        assert _exceeds_depth({"a": "string"}) is False
        assert _exceeds_depth({"a": 42}) is False

    def test_empty_dict_is_fine(self):
        assert _exceeds_depth({}) is False


# ---------------------------------------------------------------------------
# Allowlist constants — Issue #3881
# ---------------------------------------------------------------------------


class TestAllowlistConstants:
    """Sanity-check that the allowlist contains expected keys and excludes others."""

    def test_known_valid_keys_are_present(self):
        for key in ("backend", "memory", "logging", "security", "ui", "chat"):
            assert key in _SYNC_ALLOWED_TOP_LEVEL_KEYS, f"'{key}' missing from allowlist"

    def test_internal_keys_are_absent(self):
        """Internal / runtime keys that must never be synced."""
        for key in ("__runtime__", "auth", "jwt", "tokens", "password"):
            assert key not in _SYNC_ALLOWED_TOP_LEVEL_KEYS, f"'{key}' should not be in the allowlist"

    def test_max_depth_is_reasonable(self):
        assert _SYNC_MAX_DEPTH >= 4, "Max depth must accommodate real nested configs"

    def test_max_payload_is_positive(self):
        assert _SYNC_MAX_PAYLOAD_BYTES > 0


# ---------------------------------------------------------------------------
# _atomic_write_json — Issue #3882 (asyncio.to_thread for blocking calls)
# ---------------------------------------------------------------------------


class TestAtomicWriteJson:
    """_atomic_write_json() must use asyncio.to_thread for os.replace/os.unlink."""

    @pytest.mark.asyncio
    async def test_writes_valid_json_to_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "settings.json"
            data = {
                "backend": {"server_host": "0.0.0.0"}  # nosec B104 - intentional bind to all interfaces for service/test
            }
            await _atomic_write_json(target, data)
            assert target.exists()
            written = json.loads(target.read_text(encoding="utf-8"))
            assert written == data

    @pytest.mark.asyncio
    async def test_os_replace_called_via_to_thread(self):
        """Verify asyncio.to_thread is used for os.replace — not a bare call."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "out.json"
            calls_recorded: list = []

            original_to_thread = asyncio.to_thread

            async def spy_to_thread(fn, *args, **kwargs):
                calls_recorded.append((fn, args))
                return await original_to_thread(fn, *args, **kwargs)

            with patch("api.settings.asyncio.to_thread", side_effect=spy_to_thread):
                await _atomic_write_json(target, {"k": "v"})

            fns_called = [fn for fn, _ in calls_recorded]
            assert os.replace in fns_called, "os.replace must be dispatched via asyncio.to_thread"

    @pytest.mark.asyncio
    async def test_cleanup_via_to_thread_on_failure(self):
        """On write failure, cleanup (os.unlink) must also use asyncio.to_thread."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "out.json"
            cleanup_calls: list = []

            original_to_thread = asyncio.to_thread

            async def spy_to_thread(fn, *args, **kwargs):
                if fn is os.replace:
                    raise OSError("simulated rename failure")
                if fn is os.unlink:
                    cleanup_calls.append(args)
                    # Actually do the unlink so we don't leak temp files.
                    return await original_to_thread(fn, *args, **kwargs)
                return await original_to_thread(fn, *args, **kwargs)

            with patch("api.settings.asyncio.to_thread", side_effect=spy_to_thread):
                with pytest.raises(OSError, match="simulated rename failure"):
                    await _atomic_write_json(target, {"k": "v"})

            assert len(cleanup_calls) == 1, "os.unlink must be called exactly once via asyncio.to_thread on failure"

    @pytest.mark.asyncio
    async def test_creates_parent_dirs_if_needed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "nested" / "deep" / "settings.json"
            await _atomic_write_json(target, {"x": 1})
            assert target.exists()


# ---------------------------------------------------------------------------
# _compute_flat_diff — regression guard
# ---------------------------------------------------------------------------


class TestComputeFlatDiff:
    """_compute_flat_diff() returns correct leaf-level diff."""

    def test_no_change_returns_empty(self):
        cfg = {"a": 1, "b": {"c": 2}}
        assert _compute_flat_diff(cfg, cfg) == {}

    def test_added_key_detected(self):
        before = {"a": 1}
        after = {"a": 1, "b": 2}
        diff = _compute_flat_diff(before, after)
        assert "b" in diff
        assert diff["b"]["before"] is None
        assert diff["b"]["after"] == 2

    def test_changed_nested_key_uses_dot_notation(self):
        before = {"mem": {"redis": {"host": "old"}}}
        after = {"mem": {"redis": {"host": "new"}}}
        diff = _compute_flat_diff(before, after)
        assert "mem.redis.host" in diff

    def test_unchanged_nested_key_not_in_diff(self):
        before = {"a": {"b": 1, "c": 2}}
        after = {"a": {"b": 1, "c": 99}}
        diff = _compute_flat_diff(before, after)
        assert "a.b" not in diff
        assert "a.c" in diff


# ---------------------------------------------------------------------------
# _count_unchanged_keys — regression guard
# ---------------------------------------------------------------------------


class TestCountUnchangedKeys:
    def test_all_changed(self):
        incoming = {"a": 1}
        changed = {"a": {"before": 0, "after": 1}}
        assert _count_unchanged_keys(incoming, changed) == 0

    def test_none_changed(self):
        incoming = {"a": 1, "b": 2}
        assert _count_unchanged_keys(incoming, {}) == 2

    def test_partial_change(self):
        incoming = {"a": 1, "b": 2, "c": 3}
        changed = {"b": {"before": 0, "after": 2}}
        result = _count_unchanged_keys(incoming, changed)
        # 3 total leaf keys, 1 changed → 2 unchanged
        assert result == 2
