# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A disabled code-review pattern must stay disabled across reads (#13274).

``get_pattern_preferences`` builds its sync client with
``get_redis_client(async_client=False, database="analytics")``. Both shared pools
are ``decode_responses=True`` (``redis_management/connection_manager.py:500``
async and ``:618`` sync, from the same ``config.decode_responses`` which defaults
``True`` with no override), so ``hgetall`` returns a ``str``-keyed dict.

The reader probed that dict with ``pattern_id.encode()``::

    if pattern_id.encode() in prefs_raw:
        enabled_str = prefs_raw[pattern_id.encode()].decode()
        enabled = enabled_str.lower() == "true"
    else:
        enabled = True

A ``bytes`` key can never match a ``str`` key, so the ``if`` branch was dead and
every pattern fell through to the ``else`` default of enabled. ``POST
/patterns/toggle`` persisted the preference to Redis correctly and the very next
read threw it away — a pattern the user disabled silently re-enabled itself.
Nothing raised, so the surrounding ``except Exception`` never fired either.

``test_toggle_then_read_round_trips`` drives the real writer and the real reader
against one shared hash, so writer/reader drift fails the suite.
"""

import pytest

from api.analytics_code_review import REVIEW_PATTERNS, get_pattern_preferences, toggle_pattern_preference
from api.schemas_analytics import PatternToggleRequest

PATTERN_ID = next(iter(REVIEW_PATTERNS))
OTHER_PATTERN_ID = list(REVIEW_PATTERNS)[1]
PREFS_KEY = "code_review:pattern_prefs"


class _FakeSyncRedis:
    """Dict-backed stand-in with the sync hgetall/hset signatures used here."""

    def __init__(self, initial=None):
        self._hashes = {PREFS_KEY: dict(initial or {})}

    def hgetall(self, key):
        return dict(self._hashes.get(key, {}))

    def hset(self, key, field, value):
        self._hashes.setdefault(key, {})[field] = value
        return 1


def _install(monkeypatch, fake):
    """Both endpoints import the factory inside the function body."""
    import autobot_shared.redis_client as rc

    monkeypatch.setattr(rc, "get_redis_client", lambda *a, **k: fake)
    return fake


@pytest.mark.asyncio
async def test_stored_false_preference_is_honoured(monkeypatch):
    """The live configuration. Pre-fix this read back enabled=True."""
    _install(monkeypatch, _FakeSyncRedis({PATTERN_ID: "false"}))

    result = await get_pattern_preferences(admin_check=True)

    assert result["patterns"][PATTERN_ID]["enabled"] is False


@pytest.mark.asyncio
async def test_stored_true_preference_stays_enabled(monkeypatch):
    """An explicitly enabled pattern must not be flipped by the fix."""
    _install(monkeypatch, _FakeSyncRedis({PATTERN_ID: "true"}))

    result = await get_pattern_preferences(admin_check=True)

    assert result["patterns"][PATTERN_ID]["enabled"] is True


@pytest.mark.asyncio
async def test_unset_pattern_defaults_to_enabled(monkeypatch):
    """The documented default for a pattern with no stored preference."""
    _install(monkeypatch, _FakeSyncRedis({PATTERN_ID: "false"}))

    result = await get_pattern_preferences(admin_check=True)

    assert result["patterns"][OTHER_PATTERN_ID]["enabled"] is True


@pytest.mark.asyncio
async def test_toggle_then_read_round_trips(monkeypatch):
    """Drive the real writer, then the real reader, over one shared hash."""
    fake = _install(monkeypatch, _FakeSyncRedis())

    toggled = await toggle_pattern_preference(
        request=PatternToggleRequest(pattern_id=PATTERN_ID, enabled=False),
        admin_check=True,
    )
    assert toggled["status"] == "success"
    assert fake.hgetall(PREFS_KEY) == {PATTERN_ID: "false"}, "the writer never persisted the preference"

    result = await get_pattern_preferences(admin_check=True)

    assert result["patterns"][PATTERN_ID]["enabled"] is False, "the pattern silently re-enabled itself"


@pytest.mark.asyncio
async def test_bytes_values_still_work(monkeypatch):
    """A client without decode_responses must keep working."""
    _install(monkeypatch, _FakeSyncRedis({PATTERN_ID: b"false"}))

    result = await get_pattern_preferences(admin_check=True)

    assert result["patterns"][PATTERN_ID]["enabled"] is False


@pytest.mark.asyncio
async def test_no_redis_returns_all_enabled(monkeypatch):
    """The documented degraded path must be unchanged."""
    import autobot_shared.redis_client as rc

    monkeypatch.setattr(rc, "get_redis_client", lambda *a, **k: None)

    result = await get_pattern_preferences(admin_check=True)

    assert all(entry["enabled"] is True for entry in result["patterns"].values())
    assert set(result["patterns"]) == set(REVIEW_PATTERNS)
