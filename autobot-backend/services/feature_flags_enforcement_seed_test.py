# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Provisioning writes the enforcement posture, and never twice (#14866).

``feature_flag:access_control:enforcement_mode`` existed in no Redis database on
the deployed install, so ``get_enforcement_mode`` took its unset branch, returned
``DISABLED``, and ``validate_ownership`` short-circuited before the ownership
lookup on every gated call site. The fix is a provisioning writer, not a change
of meaning: the tests below pin **both** halves of that -- the key gets written,
and what an unset key or ``log_only`` mean is left exactly as it was.
"""

import pytest

from services.feature_flags import (
    ENFORCEMENT_MODE_KEY,
    PROVISIONED_ENFORCEMENT_MODE_DEFAULT,
    PROVISIONED_ENFORCEMENT_MODE_ENV,
    EnforcementMode,
    EnforcementModeUnavailable,
    FeatureFlags,
    resolve_provisioned_enforcement_mode,
)


class _FakeRedis:
    """Enough of the async client to observe SET NX semantics faithfully."""

    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self.store: dict[str, str] = dict(initial or {})
        self.set_calls: list[tuple[str, str, bool]] = []

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, nx: bool = False):
        self.set_calls.append((key, value, nx))
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


def _flags(redis: _FakeRedis) -> FeatureFlags:
    flags = FeatureFlags()

    async def _get_redis():
        return redis

    flags._get_redis = _get_redis
    return flags


class TestProvisioningWritesThePostureWhenTheInstallHasNone:
    """The unwritten key is the production state this issue exists to end."""

    @pytest.mark.asyncio
    async def test_the_key_is_written_when_it_is_absent(self):
        redis = _FakeRedis()

        written, effective = await _flags(redis).seed_enforcement_mode()

        assert written is True
        assert redis.store[ENFORCEMENT_MODE_KEY] == PROVISIONED_ENFORCEMENT_MODE_DEFAULT.value
        assert effective is PROVISIONED_ENFORCEMENT_MODE_DEFAULT
        assert redis.set_calls, "the seeder must actually reach the flag store"

    @pytest.mark.asyncio
    async def test_the_value_written_is_the_prescribed_posture(self):
        """Asserted against the constant, so the posture has exactly one home."""
        redis = _FakeRedis()

        await _flags(redis).seed_enforcement_mode()

        assert redis.store[ENFORCEMENT_MODE_KEY] == PROVISIONED_ENFORCEMENT_MODE_DEFAULT.value

    def test_the_prescribed_posture_is_the_one_the_issues_record(self):
        """#14010 AC4 asks for the ``log_only`` measurement before any flip to
        ``enforced``; #14866 calls it "the safe first value". Neither issue
        prescribes ``disabled``, which would provision an install into exactly
        the posture that protects nothing."""
        assert PROVISIONED_ENFORCEMENT_MODE_DEFAULT is EnforcementMode.LOG_ONLY
        assert PROVISIONED_ENFORCEMENT_MODE_DEFAULT is not EnforcementMode.DISABLED

    @pytest.mark.asyncio
    async def test_the_write_is_guarded_by_set_nx_rather_than_a_read_first(self):
        """Two provisioning runs racing must not both write. The guard is the
        Redis operation, not a check we perform before it."""
        redis = _FakeRedis()

        await _flags(redis).seed_enforcement_mode()

        assert redis.set_calls == [(ENFORCEMENT_MODE_KEY, PROVISIONED_ENFORCEMENT_MODE_DEFAULT.value, True)]


class TestReprovisioningNeverOverwritesAnOperatorsChoice:
    """Idempotency is the difference between provisioning and clobbering."""

    @pytest.mark.asyncio
    async def test_an_existing_value_is_left_untouched(self):
        redis = _FakeRedis({ENFORCEMENT_MODE_KEY: EnforcementMode.ENFORCED.value})

        written, effective = await _flags(redis).seed_enforcement_mode()

        assert written is False
        assert effective is EnforcementMode.ENFORCED
        assert redis.store[ENFORCEMENT_MODE_KEY] == EnforcementMode.ENFORCED.value

    @pytest.mark.asyncio
    async def test_a_deliberate_disabled_survives_reprovisioning(self):
        """An operator turning enforcement off on purpose is a decision, and a
        deploy must not quietly undo it."""
        redis = _FakeRedis({ENFORCEMENT_MODE_KEY: EnforcementMode.DISABLED.value})

        written, effective = await _flags(redis).seed_enforcement_mode()

        assert written is False
        assert effective is EnforcementMode.DISABLED
        assert redis.store[ENFORCEMENT_MODE_KEY] == EnforcementMode.DISABLED.value

    @pytest.mark.asyncio
    async def test_every_mode_an_operator_could_have_set_is_preserved(self):
        modes = list(EnforcementMode)
        assert modes, "an empty enumeration would assert nothing at all"

        for mode in modes:
            redis = _FakeRedis({ENFORCEMENT_MODE_KEY: mode.value})

            written, effective = await _flags(redis).seed_enforcement_mode()

            assert written is False, f"{mode.value} was overwritten by re-provisioning"
            assert effective is mode

    @pytest.mark.asyncio
    async def test_a_dry_run_writes_nothing(self):
        redis = _FakeRedis()

        written, effective = await _flags(redis).seed_enforcement_mode(dry_run=True)

        assert written is True, "a dry run still reports what it would do"
        assert effective is PROVISIONED_ENFORCEMENT_MODE_DEFAULT
        assert redis.set_calls == []
        assert ENFORCEMENT_MODE_KEY not in redis.store


class TestTheResolvedPostureIsNeverInvented:
    """A misconfigured posture must fail provisioning, not silently become one."""

    def test_an_explicit_mode_wins(self):
        assert resolve_provisioned_enforcement_mode("enforced") is EnforcementMode.ENFORCED

    def test_the_environment_selects_the_posture(self, monkeypatch):
        monkeypatch.setenv(PROVISIONED_ENFORCEMENT_MODE_ENV, EnforcementMode.ENFORCED.value)

        assert resolve_provisioned_enforcement_mode() is EnforcementMode.ENFORCED

    def test_an_unset_environment_falls_back_to_the_recorded_default(self, monkeypatch):
        monkeypatch.delenv(PROVISIONED_ENFORCEMENT_MODE_ENV, raising=False)

        assert resolve_provisioned_enforcement_mode() is PROVISIONED_ENFORCEMENT_MODE_DEFAULT

    def test_an_unrecognised_mode_is_refused_rather_than_defaulted(self):
        with pytest.raises(ValueError) as excinfo:
            resolve_provisioned_enforcement_mode("mostly_enforced")

        assert "mostly_enforced" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_a_missing_flag_store_is_reported_not_assumed_provisioned(self):
        flags = FeatureFlags()

        async def _no_redis():
            return None

        flags._get_redis = _no_redis

        with pytest.raises(EnforcementModeUnavailable):
            await flags.seed_enforcement_mode()


class TestTheReaderAndTheSeederStateOneDefault:
    """Seeding alone left the two halves disagreeing.

    The seeder writes ``log_only``; the reader read an absent key as
    ``disabled``. That gap is why the control was off everywhere -- an install
    provisioning had not reached was indistinguishable from one deliberately
    turned off, and only the second of those is a decision anybody made. The
    reader now falls back to the same constant the seeder writes, so "never
    provisioned" cannot mean "enforcement off".
    """

    @pytest.mark.asyncio
    async def test_an_unset_flag_resolves_to_the_provisioned_default(self):
        redis = _FakeRedis()
        flags = _flags(redis)
        flags._enforcement_default_logged = False

        assert await flags.get_enforcement_mode() is PROVISIONED_ENFORCEMENT_MODE_DEFAULT

    @pytest.mark.asyncio
    async def test_an_unset_flag_no_longer_disables_enforcement(self):
        """The assertion that would have caught the original defect."""
        redis = _FakeRedis()
        flags = _flags(redis)
        flags._enforcement_default_logged = False

        assert await flags.get_enforcement_mode() is not EnforcementMode.DISABLED

    @pytest.mark.asyncio
    async def test_a_provisioned_posture_is_what_the_reader_returns(self):
        redis = _FakeRedis()
        flags = _flags(redis)

        await flags.seed_enforcement_mode()

        assert await flags.get_enforcement_mode() is PROVISIONED_ENFORCEMENT_MODE_DEFAULT
