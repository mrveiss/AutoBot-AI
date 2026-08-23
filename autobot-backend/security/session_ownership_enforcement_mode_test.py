# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An unreachable flag store must not read as "authorization is off" (#14010).

`_get_enforcement_mode` returned `"disabled"` in three situations, and
`validate_ownership` fast-paths on that value — skipping the check entirely. Two
of the three were infrastructure faults, not decisions:

- the feature-flags service could not be constructed (`get_feature_flags()` raised)
- reading the mode raised

A fourth route sat one layer deeper and is the reason the other two rarely fired:
`FeatureFlags.get_enforcement_mode` caught every exception itself and returned
`DISABLED`, commented "Fail-safe". For an authorization control that is fail-
**open**: a Redis blip silently turned off every ownership check platform-wide,
for its duration, with nothing louder than a debug line.

The distinction these pin: *deliberately disabled* and *could not be determined*
are different facts. The first is policy and is left exactly as it was. The
second now degrades to `log_only` — every check still runs and every violation is
still recorded — and says so at WARNING.

What this does **not** change is the default posture when the flag is simply
unset. That is a separate decision with real blast radius (#14010 step 2), and
is deliberately untouched here.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from security.session_ownership import DEGRADED_ENFORCEMENT_MODE, SessionOwnershipValidator
from services.feature_flags import EnforcementMode, EnforcementModeUnavailable


def _validator(feature_flags):
    validator = SessionOwnershipValidator.__new__(SessionOwnershipValidator)
    validator.redis = MagicMock()
    validator.feature_flags = feature_flags
    validator.metrics_service = None
    return validator


def _flags_returning(mode: EnforcementMode):
    flags = MagicMock()
    flags.get_enforcement_mode = AsyncMock(return_value=mode)
    return flags


def _flags_raising(exc: Exception):
    flags = MagicMock()
    flags.get_enforcement_mode = AsyncMock(side_effect=exc)
    return flags


class TestAPolicyDecisionIsUnchanged:
    """The half that must NOT move: a mode someone actually set."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "mode", [EnforcementMode.DISABLED, EnforcementMode.LOG_ONLY, EnforcementMode.ENFORCED]
    )
    async def test_a_resolved_mode_is_returned_verbatim(self, mode):
        assert await _validator(_flags_returning(mode))._get_enforcement_mode() == mode.value

    @pytest.mark.asyncio
    async def test_a_deliberate_disabled_still_disables(self):
        """The operator's own choice is still honoured — this is not a posture change."""
        validator = _validator(_flags_returning(EnforcementMode.DISABLED))

        assert await validator._get_enforcement_mode() == "disabled"


class TestAnUndeterminedModeDoesNotDisableEnforcement:
    """The half that was fail-open."""

    @pytest.mark.asyncio
    async def test_an_unreadable_mode_degrades_to_log_only(self):
        validator = _validator(_flags_raising(EnforcementModeUnavailable("redis down")))

        mode = await validator._get_enforcement_mode()

        assert mode == DEGRADED_ENFORCEMENT_MODE == "log_only"
        assert mode != "disabled", (
            "an unreachable flag store was read as 'authorization is off' — the #14010 defect"
        )

    @pytest.mark.asyncio
    async def test_a_missing_flags_service_degrades_to_log_only(self):
        """`feature_flags=None` means construction failed, not that policy is off."""
        mode = await _validator(None)._get_enforcement_mode()

        assert mode == DEGRADED_ENFORCEMENT_MODE
        assert mode != "disabled"

    @pytest.mark.asyncio
    async def test_an_unexpected_error_degrades_rather_than_disabling(self):
        mode = await _validator(_flags_raising(RuntimeError("boom")))._get_enforcement_mode()

        assert mode == DEGRADED_ENFORCEMENT_MODE

    @pytest.mark.asyncio
    async def test_the_degrade_is_audible(self, caplog):
        """A silent degrade is the same bug one level quieter.

        The original failure logged at debug, so a deployment could run
        indefinitely with every check inert and nothing saying so.
        """
        with caplog.at_level(logging.WARNING):
            await _validator(_flags_raising(EnforcementModeUnavailable("redis down")))._get_enforcement_mode()

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warnings, "an undetermined enforcement mode must not degrade quietly"
        assert any("log_only" in r.getMessage() for r in warnings), (
            "the warning must say what it degraded to"
        )


class TestTheFlagStoreReportsFailureInsteadOfInventingAnAnswer:
    """The deepest of the four routes, and the one that hid the others."""

    @pytest.mark.asyncio
    async def test_a_read_failure_raises_rather_than_returning_disabled(self):
        from services.feature_flags import FeatureFlags

        flags = FeatureFlags.__new__(FeatureFlags)
        flags._get_redis = AsyncMock(side_effect=ConnectionError("redis down"))

        with pytest.raises(EnforcementModeUnavailable):
            await flags.get_enforcement_mode()

    @pytest.mark.asyncio
    async def test_an_unset_flag_still_means_disabled(self):
        """The default posture is a separate decision (#14010 step 2) — untouched."""
        from services.feature_flags import FeatureFlags

        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        flags = FeatureFlags.__new__(FeatureFlags)
        flags._get_redis = AsyncMock(return_value=redis)
        flags._enforcement_default_logged = False

        assert await flags.get_enforcement_mode() == EnforcementMode.DISABLED
