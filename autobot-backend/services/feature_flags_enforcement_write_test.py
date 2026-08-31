# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The admin write path for the enforcement posture, and what its answer means (#15089).

``set_enforcement_mode`` used to write the key, then reach for a ``_redis``
attribute the async Redis client does not have, raise, and return ``False``. An
operator moving the posture through the admin API therefore got a 500 for a
change that had in fact landed, while the audit entry the same block was trying
to record was never written at all -- reported state and real state disagreeing,
on an authorization control.

The tests below pin both halves of the repair: the happy path really writes, and
a failure really does mean nothing changed. The fakes deliberately answer only
what ``redis.asyncio.Redis`` answers, so the next wrong-surface call cannot be
tested green.
"""

import json

import pytest
import redis.asyncio as async_redis

from constants.threshold_constants import CategoryDefaults
from services.feature_flags import (
    ENFORCEMENT_HISTORY_KEY,
    ENFORCEMENT_HISTORY_LENGTH,
    ENFORCEMENT_MODE_KEY,
    EnforcementMode,
    FeatureFlags,
)

# Bookkeeping the fakes need to be observable at all. Everything outside this
# set has to exist on the real client -- see the surface guards at the bottom.
_TEST_ONLY_ATTRIBUTES = frozenset({"store", "lists", "dispatch_error", "command_error", "commands"})


class _FakePipeline:
    """A MULTI buffer: commands queue, and ``execute`` applies them or none."""

    def __init__(self, client: "_FakeAsyncRedis") -> None:
        self._client = client
        self.commands: list[tuple] = []

    def set(self, key, value, **kwargs):
        self.commands.append(("set", key, value))
        return self

    def get(self, key):
        self.commands.append(("get", key))
        return self

    def lpush(self, key, value):
        self.commands.append(("lpush", key, value))
        return self

    def ltrim(self, key, start, stop):
        self.commands.append(("ltrim", key, start, stop))
        return self

    async def execute(self, raise_on_error: bool = True):
        """Apply the queued commands.

        ``dispatch_error`` models the connection dying before ``EXEC``: nothing
        is applied, which is what makes a ``False`` answer truthful.
        ``command_error`` models one command erroring *inside* ``EXEC``, which
        Redis does not roll back -- the rest of the transaction still applies.
        """
        if self._client.dispatch_error is not None:
            raise self._client.dispatch_error

        results = []
        for command in self.commands:
            error = self._client.command_error.get(command[0]) if self._client.command_error else None
            if error is not None:
                if raise_on_error:
                    raise error
                results.append(error)
                continue
            results.append(self._client.apply(command))
        return results


class _FakeAsyncRedis:
    """Only the surface ``redis.asyncio.Redis`` actually offers."""

    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self.store: dict[str, str] = dict(initial or {})
        self.lists: dict[str, list[str]] = {}
        self.dispatch_error: Exception | None = None
        self.command_error: dict[str, Exception] = {}

    def apply(self, command: tuple):
        name = command[0]
        if name == "set":
            self.store[command[1]] = command[2]
            return True
        if name == "get":
            return self.store.get(command[1])
        if name == "lpush":
            self.lists.setdefault(command[1], []).insert(0, command[2])
            return len(self.lists[command[1]])
        if name == "ltrim":
            # LTRIM on a key that does not exist is a no-op in Redis; it does
            # not create an empty list, and the fake must not either.
            if command[1] in self.lists:
                self.lists[command[1]] = self.lists[command[1]][command[2] : command[3] + 1]
            return True
        raise AssertionError(f"unmodelled command {name}")

    def pipeline(self, transaction: bool = True):
        return _FakePipeline(self)

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, nx: bool = False):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def lpush(self, key, value):
        """Present so the pre-#15089 ordering can be run as a contrast mutation."""
        if self.dispatch_error is not None:
            raise self.dispatch_error
        return self.apply(("lpush", key, value))

    async def ltrim(self, key, start, stop):
        if self.dispatch_error is not None:
            raise self.dispatch_error
        return self.apply(("ltrim", key, start, stop))

    async def lrange(self, key, start, stop):
        entries = self.lists.get(key, [])
        return entries[start : stop + 1] if stop >= 0 else entries[start:]

    async def scan(self, cursor, match=None, count=None):
        return 0, [key for key in self.store if match is None or key.startswith(match.rstrip("*"))]

    async def delete(self, *keys):
        return sum(1 for key in keys if self.store.pop(key, None) is not None)


def _flags(redis: _FakeAsyncRedis) -> FeatureFlags:
    flags = FeatureFlags()

    async def _get_redis():
        return redis

    flags._get_redis = _get_redis
    return flags


class TestTheAdminWritePathActuallyWrites:
    """The regression: every admin write reported failure after succeeding."""

    @pytest.mark.asyncio
    async def test_setting_the_mode_returns_true_and_the_key_is_set(self):
        redis = _FakeAsyncRedis()

        assert await _flags(redis).set_enforcement_mode(EnforcementMode.ENFORCED) is True
        assert redis.store[ENFORCEMENT_MODE_KEY] == EnforcementMode.ENFORCED.value

    @pytest.mark.asyncio
    async def test_the_change_is_recorded_in_the_history_the_stats_reader_reads(self):
        """The audit trail was never written at all before this fix."""
        redis = _FakeAsyncRedis()

        await _flags(redis).set_enforcement_mode(EnforcementMode.LOG_ONLY)

        entries = redis.lists[ENFORCEMENT_HISTORY_KEY]
        assert len(entries) == 1
        assert json.loads(entries[0])["mode"] == EnforcementMode.LOG_ONLY.value

    @pytest.mark.asyncio
    async def test_every_mode_an_operator_can_choose_is_written_back(self):
        modes = list(EnforcementMode)
        assert modes, "an empty enumeration would assert nothing at all"

        for mode in modes:
            redis = _FakeAsyncRedis()

            assert await _flags(redis).set_enforcement_mode(mode) is True, f"{mode.value} was not written"
            assert redis.store[ENFORCEMENT_MODE_KEY] == mode.value

    @pytest.mark.asyncio
    async def test_the_history_is_trimmed_to_its_documented_length(self):
        redis = _FakeAsyncRedis()
        redis.lists[ENFORCEMENT_HISTORY_KEY] = ["old"] * (ENFORCEMENT_HISTORY_LENGTH + 50)

        await _flags(redis).set_enforcement_mode(EnforcementMode.ENFORCED)

        assert len(redis.lists[ENFORCEMENT_HISTORY_KEY]) == ENFORCEMENT_HISTORY_LENGTH


class TestAFailedWriteMeansNothingChanged:
    """The chosen semantics: ``False`` is only ever returned for a posture that
    did not move. Returning ``False`` for a write that landed is the shape that
    kept this invisible, so it is pinned here rather than left to convention."""

    @pytest.mark.asyncio
    async def test_a_failure_before_exec_returns_false_and_leaves_the_key_unset(self):
        redis = _FakeAsyncRedis()
        redis.dispatch_error = ConnectionError("connection lost before EXEC")

        result = await _flags(redis).set_enforcement_mode(EnforcementMode.ENFORCED)

        assert result is False
        assert ENFORCEMENT_MODE_KEY not in redis.store, "False must mean the posture did not move"
        assert ENFORCEMENT_HISTORY_KEY not in redis.lists

    @pytest.mark.asyncio
    async def test_a_deliberate_posture_survives_a_failed_change(self):
        """The half-write's real danger: an operator's existing choice replaced
        by a value the API then reports as not applied."""
        redis = _FakeAsyncRedis({ENFORCEMENT_MODE_KEY: EnforcementMode.LOG_ONLY.value})
        redis.dispatch_error = ConnectionError("connection lost before EXEC")

        assert await _flags(redis).set_enforcement_mode(EnforcementMode.DISABLED) is False
        assert redis.store[ENFORCEMENT_MODE_KEY] == EnforcementMode.LOG_ONLY.value

    @pytest.mark.asyncio
    async def test_a_lost_audit_entry_does_not_report_a_change_that_happened_as_a_failure(self):
        """Redis does not roll back a command that errors inside ``EXEC``, so the
        posture really did move; saying otherwise would be the original defect
        in a rarer form. The loss is logged, not converted into a false ``False``."""
        redis = _FakeAsyncRedis()
        redis.command_error = {"lpush": TypeError("WRONGTYPE against a key holding the wrong kind of value")}

        result = await _flags(redis).set_enforcement_mode(EnforcementMode.ENFORCED)

        assert result is True
        assert redis.store[ENFORCEMENT_MODE_KEY] == EnforcementMode.ENFORCED.value
        assert ENFORCEMENT_HISTORY_KEY not in redis.lists

    @pytest.mark.asyncio
    async def test_an_unreachable_flag_store_is_a_failure_not_a_silent_success(self):
        flags = FeatureFlags()

        async def _no_redis():
            return None

        flags._get_redis = _no_redis

        assert await flags.set_enforcement_mode(EnforcementMode.ENFORCED) is False


class TestRolloutStatisticsHasASuccessPath:
    """``get_rollout_statistics`` reported ``unknown`` on every call, because the
    ``_redis`` access raised before anything could be read. The error-path test
    beside this one passed only because the error path was the only path."""

    @pytest.mark.asyncio
    async def test_statistics_report_the_real_mode_and_the_recorded_history(self):
        redis = _FakeAsyncRedis()
        flags = _flags(redis)
        await flags.set_enforcement_mode(EnforcementMode.ENFORCED)

        stats = await flags.get_rollout_statistics()

        assert stats["current_mode"] == EnforcementMode.ENFORCED.value
        assert stats["current_mode"] != CategoryDefaults.UNKNOWN
        assert len(stats["history"]) == 1
        assert stats["history"][0]["mode"] == EnforcementMode.ENFORCED.value

    @pytest.mark.asyncio
    async def test_endpoint_overrides_are_reported_from_the_scan(self):
        redis = _FakeAsyncRedis({"feature_flag:access_control:endpoint:/api/chat": EnforcementMode.ENFORCED.value})
        flags = _flags(redis)
        await flags.set_enforcement_mode(EnforcementMode.LOG_ONLY)

        stats = await flags.get_rollout_statistics()

        assert stats["endpoint_overrides"] == {"/api/chat": EnforcementMode.ENFORCED.value}
        assert stats["total_endpoints_configured"] == 1


class TestTheFakesCannotAnswerWhatTheRealClientCannot:
    """A fake that answers ``_redis`` would have kept every test above green
    while production raised on every call. That is the whole reason this file
    builds its own doubles instead of using ``MagicMock``."""

    def test_the_real_async_client_has_no_redis_attribute(self):
        assert not hasattr(async_redis.Redis, "_redis")

    def test_the_fake_client_has_no_redis_attribute(self):
        assert "_redis" not in _TEST_ONLY_ATTRIBUTES, "the allowlist must not be able to smuggle it back"
        assert not hasattr(_FakeAsyncRedis(), "_redis")

    def test_the_fake_client_exposes_nothing_the_real_client_lacks(self):
        surface = {name for name in dir(_FakeAsyncRedis()) if not name.startswith("__")}
        checked = sorted(surface - _TEST_ONLY_ATTRIBUTES - {"apply"})
        assert checked, "an empty surface would assert nothing at all"

        invented = [name for name in checked if not hasattr(async_redis.Redis, name)]
        assert invented == [], f"the fake answers what the real client does not: {invented}"

    def test_the_fake_pipeline_exposes_nothing_the_real_pipeline_lacks(self):
        real = async_redis.client.Pipeline
        surface = {name for name in dir(_FakePipeline(_FakeAsyncRedis())) if not name.startswith("_")}
        checked = sorted(surface - _TEST_ONLY_ATTRIBUTES)
        assert checked, "an empty surface would assert nothing at all"

        invented = [name for name in checked if not hasattr(real, name)]
        assert invented == [], f"the fake pipeline answers what the real one does not: {invented}"

    def test_the_service_never_reaches_through_a_private_redis_attribute(self):
        """The guard for the four call sites this issue names."""
        import inspect

        import services.feature_flags as module

        source = inspect.getsource(module)
        assert source, "an unreadable module would assert nothing at all"
        assert "redis._redis." not in source
