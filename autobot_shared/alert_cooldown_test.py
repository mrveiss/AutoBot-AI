# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for the multi-tier alert cooldown system (Issue #1948).

Uses a stub ``autobot_shared.redis_client`` injected before the module under
test is imported — the same pattern used by ``message_bus_test.py`` — so a
live Redis connection is never required.
"""

import sys
import types
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Install redis_client stub BEFORE importing alert_cooldown
# ---------------------------------------------------------------------------


def _install_redis_stub() -> None:
    """Inject a fake autobot_shared.redis_client into sys.modules."""
    mod_name = "autobot_shared.redis_client"
    if mod_name in sys.modules:
        return
    stub = types.ModuleType(mod_name)
    stub.get_redis_client = MagicMock(name="stub_get_redis_client")
    sys.modules[mod_name] = stub


_install_redis_stub()

# Safe to import now
from autobot_shared.alert_cooldown import (  # noqa: E402
    AlertCooldownManager,
    AlertTier,
    _fingerprint,
    _normalise,
    _resolve_cooldown_ttl,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis(*, rate_count: int = 0, cooldown_exists: bool = False, stored_recurrence: int = 0):
    """Return a mock synchronous Redis client with configurable state.

    Args:
        rate_count: Value returned by ``get()`` for the rate key (0 means
                    no existing counter, treated as None by the manager).
        cooldown_exists: Whether ``exists()`` returns 1 for the cooldown key.
        stored_recurrence: Value returned by ``get()`` for the cooldown key
                           (used when reading existing recurrence count).
    """
    client = MagicMock()

    # pipeline().execute() used by _increment_rate_counter
    pipe = MagicMock()
    pipe.incr = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = MagicMock(return_value=[1, True])
    client.pipeline = MagicMock(return_value=pipe)

    # Rate-counter GET — None means "no sends yet"
    rate_raw = str(rate_count).encode() if rate_count > 0 else None

    # Cooldown GET — returns recurrence if key exists, else None
    cooldown_raw = str(stored_recurrence).encode() if cooldown_exists else None

    def _side_effect_get(key):
        if key.startswith("alerts:rate:"):
            return rate_raw
        if key.startswith("alerts:cooldown:"):
            return cooldown_raw
        return None

    client.get = MagicMock(side_effect=_side_effect_get)
    client.exists = MagicMock(return_value=1 if cooldown_exists else 0)
    client.set = MagicMock(return_value=True)

    return client


def _make_manager(redis_client) -> AlertCooldownManager:
    """Return an AlertCooldownManager whose _get_client() returns the supplied mock."""
    mgr = AlertCooldownManager()
    mgr._get_client = MagicMock(return_value=redis_client)
    return mgr


# ---------------------------------------------------------------------------
# Tests — semantic normalisation & fingerprinting
# ---------------------------------------------------------------------------


class TestNormalise:
    def test_strips_leading_trailing_whitespace(self) -> None:
        assert _normalise("  hello world  ") == "hello world"

    def test_replaces_integers(self) -> None:
        assert _normalise("Disk at 95%") == "Disk at <N>%"

    def test_replaces_floats(self) -> None:
        assert _normalise("Load: 1.23") == "Load: <N>"

    def test_removes_iso_timestamp_with_T(self) -> None:
        result = _normalise("Error at 2025-03-31T12:00:00Z on node-3")
        assert "2025" not in result
        assert "12:00" not in result

    def test_removes_iso_timestamp_with_space(self) -> None:
        result = _normalise("Error at 2025-03-31 12:00:00 on host")
        assert "2025" not in result

    def test_collapses_whitespace(self) -> None:
        assert _normalise("a   b\tc") == "a b c"

    def test_similar_alerts_same_fingerprint(self) -> None:
        """Two alerts differing only in a counter produce the same fingerprint."""
        fp1 = _fingerprint("Disk usage at 95% on node-3")
        fp2 = _fingerprint("Disk usage at 96% on node-3")
        assert fp1 == fp2

    def test_different_alerts_different_fingerprint(self) -> None:
        fp1 = _fingerprint("Disk usage at 95%")
        fp2 = _fingerprint("CPU usage at 95%")
        assert fp1 != fp2

    def test_fingerprint_is_64_char_hex(self) -> None:
        fp = _fingerprint("any alert text")
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_timestamp_alerts_same_fingerprint(self) -> None:
        """Alerts identical except for timestamp share a fingerprint."""
        fp1 = _fingerprint("Job failed at 2025-01-01T00:00:00Z")
        fp2 = _fingerprint("Job failed at 2025-06-15T09:30:00Z")
        assert fp1 == fp2


# ---------------------------------------------------------------------------
# Tests — progressive cooldown TTL resolution
# ---------------------------------------------------------------------------


class TestResolveCooldownTtl:
    def test_first_send_uses_base_cooldown(self) -> None:
        """Recurrence 0: progressive schedule gives 0 h, so base cooldown wins."""
        ttl = _resolve_cooldown_ttl(AlertTier.FLASH, recurrence=0)
        assert ttl == AlertTier.FLASH.base_cooldown_seconds  # 300 s

    def test_second_send_uses_6h(self) -> None:
        """Recurrence 1 → 6 h, which exceeds FLASH base (5 min)."""
        ttl = _resolve_cooldown_ttl(AlertTier.FLASH, recurrence=1)
        assert ttl == 6 * 3600

    def test_third_send_uses_12h(self) -> None:
        ttl = _resolve_cooldown_ttl(AlertTier.FLASH, recurrence=2)
        assert ttl == 12 * 3600

    def test_fourth_and_beyond_capped_at_24h(self) -> None:
        ttl = _resolve_cooldown_ttl(AlertTier.FLASH, recurrence=3)
        assert ttl == 24 * 3600
        ttl_high = _resolve_cooldown_ttl(AlertTier.FLASH, recurrence=99)
        assert ttl_high == 24 * 3600

    def test_routine_base_wins_over_zero_schedule(self) -> None:
        """ROUTINE has a 60-min base; recurrence 0 schedule is 0 → base wins."""
        ttl = _resolve_cooldown_ttl(AlertTier.ROUTINE, recurrence=0)
        assert ttl == AlertTier.ROUTINE.base_cooldown_seconds  # 3600 s


# ---------------------------------------------------------------------------
# Tests — AlertTier enum properties
# ---------------------------------------------------------------------------


class TestAlertTierProperties:
    def test_flash_rate(self) -> None:
        assert AlertTier.FLASH.max_per_hour == 6
        assert AlertTier.FLASH.base_cooldown_seconds == 5 * 60

    def test_priority_rate(self) -> None:
        assert AlertTier.PRIORITY.max_per_hour == 4
        assert AlertTier.PRIORITY.base_cooldown_seconds == 30 * 60

    def test_routine_rate(self) -> None:
        assert AlertTier.ROUTINE.max_per_hour == 2
        assert AlertTier.ROUTINE.base_cooldown_seconds == 60 * 60

    def test_tier_names(self) -> None:
        assert AlertTier.FLASH.tier_name == "flash"
        assert AlertTier.PRIORITY.tier_name == "priority"
        assert AlertTier.ROUTINE.tier_name == "routine"


# ---------------------------------------------------------------------------
# Tests — AlertCooldownManager.should_send
# ---------------------------------------------------------------------------


class TestShouldSend:
    def test_first_alert_always_passes(self) -> None:
        """With no existing rate count and no cooldown key, alert must pass."""
        client = _make_redis(rate_count=0, cooldown_exists=False)
        mgr = _make_manager(client)
        assert mgr.should_send("Service down", AlertTier.FLASH) is True

    def test_suppressed_when_in_cooldown(self) -> None:
        """If the cooldown key exists, the alert must be suppressed."""
        client = _make_redis(cooldown_exists=True)
        mgr = _make_manager(client)
        assert mgr.should_send("Service down", AlertTier.FLASH) is False

    def test_suppressed_when_rate_limit_reached(self) -> None:
        """When the hourly counter equals max_per_hour, suppress the alert."""
        client = _make_redis(rate_count=AlertTier.FLASH.max_per_hour, cooldown_exists=False)
        mgr = _make_manager(client)
        assert mgr.should_send("Any alert", AlertTier.FLASH) is False

    def test_passes_when_rate_below_limit(self) -> None:
        """Counter below max_per_hour and no cooldown — alert should pass."""
        client = _make_redis(rate_count=AlertTier.FLASH.max_per_hour - 1, cooldown_exists=False)
        mgr = _make_manager(client)
        assert mgr.should_send("Any alert", AlertTier.FLASH) is True

    def test_rate_limit_checked_before_cooldown(self) -> None:
        """Rate limit failure short-circuits before checking cooldown."""
        client = _make_redis(rate_count=AlertTier.PRIORITY.max_per_hour, cooldown_exists=True)
        mgr = _make_manager(client)
        # Both limits are hit; rate must be checked first (exists should not be called).
        result = mgr.should_send("Alert text", AlertTier.PRIORITY)
        assert result is False
        client.exists.assert_not_called()

    def test_different_tiers_are_independent(self):
        """FLASH rate exhaustion must not suppress ROUTINE alerts."""
        flash_client = _make_redis(rate_count=AlertTier.FLASH.max_per_hour)
        routine_client = _make_redis(rate_count=0)

        def tier_client(tier):
            if tier == AlertTier.FLASH:
                return flash_client
            return routine_client

        # Use separate manager instances to avoid shared state
        flash_mgr = _make_manager(flash_client)
        routine_mgr = _make_manager(routine_client)

        assert flash_mgr.should_send("Disk full", AlertTier.FLASH) is False
        assert routine_mgr.should_send("Disk full", AlertTier.ROUTINE) is True

    def test_fail_open_when_redis_unavailable(self) -> None:
        """When Redis is None, alert must be allowed through (fail-open)."""
        mgr = AlertCooldownManager()
        mgr._get_client = MagicMock(return_value=None)
        assert mgr.should_send("Alert", AlertTier.FLASH) is True


# ---------------------------------------------------------------------------
# Tests — AlertCooldownManager.record_sent
# ---------------------------------------------------------------------------


class TestRecordSent:
    def test_increments_rate_counter(self) -> None:
        """record_sent must call pipeline().incr() and pipeline().execute()."""
        client = _make_redis()
        mgr = _make_manager(client)
        mgr.record_sent("Service down", AlertTier.FLASH)

        pipe = client.pipeline.return_value
        pipe.incr.assert_called_once()
        pipe.expire.assert_called_once()
        pipe.execute.assert_called_once()

    def test_sets_cooldown_key(self) -> None:
        """record_sent must call client.set() for the cooldown key."""
        client = _make_redis()
        mgr = _make_manager(client)
        mgr.record_sent("Service down", AlertTier.FLASH)

        assert client.set.called
        call_args = client.set.call_args
        key = call_args[0][0]
        assert "alerts:cooldown:flash:" in key

    def test_cooldown_ttl_matches_base_on_first_send(self) -> None:
        """First send (recurrence 0): TTL must be tier base cooldown (300 s for FLASH)."""
        client = _make_redis(cooldown_exists=False)
        mgr = _make_manager(client)
        mgr.record_sent("Service down", AlertTier.FLASH)

        call_kwargs = client.set.call_args[1]
        assert call_kwargs.get("ex") == AlertTier.FLASH.base_cooldown_seconds

    def test_cooldown_ttl_escalates_on_recurrence(self) -> None:
        """Second send (stored recurrence=1): TTL must escalate to 6 h."""
        client = _make_redis(cooldown_exists=True, stored_recurrence=1)
        mgr = _make_manager(client)
        mgr.record_sent("Service down", AlertTier.FLASH)

        call_kwargs = client.set.call_args[1]
        assert call_kwargs.get("ex") == 6 * 3600

    def test_no_op_when_redis_unavailable(self) -> None:
        """record_sent must not raise when Redis is unavailable."""
        mgr = AlertCooldownManager()
        mgr._get_client = MagicMock(return_value=None)
        # Should complete without raising
        mgr.record_sent("Alert", AlertTier.ROUTINE)


# ---------------------------------------------------------------------------
# Tests — cooldown key namespacing
# ---------------------------------------------------------------------------


class TestKeyNamespacing:
    def test_cooldown_key_format(self) -> None:
        mgr = AlertCooldownManager()
        fp = _fingerprint("test alert")
        key = mgr._cooldown_key(AlertTier.FLASH, fp)
        assert key == f"alerts:cooldown:flash:{fp}"

    def test_rate_window_key_format(self) -> None:
        import time

        mgr = AlertCooldownManager()
        key = mgr._rate_window_key(AlertTier.PRIORITY)
        window_ts = int(time.time()) // 3600
        assert key == f"alerts:rate:priority:{window_ts}"

    def test_cooldown_keys_differ_across_tiers(self) -> None:
        """Same fingerprint must produce different keys for different tiers."""
        mgr = AlertCooldownManager()
        fp = _fingerprint("same alert")
        key_flash = mgr._cooldown_key(AlertTier.FLASH, fp)
        key_routine = mgr._cooldown_key(AlertTier.ROUTINE, fp)
        assert key_flash != key_routine


# ---------------------------------------------------------------------------
# Tests — round-trip (should_send → record_sent → should_send)
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_send_then_blocked(self) -> None:
        """After record_sent, should_send must return False (cooldown active)."""
        # Simulate: first check passes, then after record_sent the key exists.
        client_before = _make_redis(rate_count=0, cooldown_exists=False)
        mgr = _make_manager(client_before)

        assert mgr.should_send("Down", AlertTier.PRIORITY) is True
        mgr.record_sent("Down", AlertTier.PRIORITY)

        # Simulate state after record_sent: cooldown key now exists.
        client_after = _make_redis(rate_count=1, cooldown_exists=True)
        mgr._get_client = MagicMock(return_value=client_after)

        assert mgr.should_send("Down", AlertTier.PRIORITY) is False
