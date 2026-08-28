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
from unittest.mock import AsyncMock, MagicMock, patch

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
    @pytest.mark.parametrize("mode", [EnforcementMode.DISABLED, EnforcementMode.LOG_ONLY, EnforcementMode.ENFORCED])
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
        assert mode != "disabled", "an unreachable flag store was read as 'authorization is off' — the #14010 defect"

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
        assert any("log_only" in r.getMessage() for r in warnings), "the warning must say what it degraded to"


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
    async def test_an_unset_flag_no_longer_means_disabled(self):
        """#14866 made the default posture the decision this deferred (#14010 step 2).

        An unset key resolved to `disabled`, so `validate_ownership` took the
        fast path and returned before the ownership lookup -- on every install,
        because nothing had ever written the key. It now resolves to the same
        posture provisioning seeds, which runs every check and audits every
        violation without refusing a request that succeeds today.
        """
        from services.feature_flags import PROVISIONED_ENFORCEMENT_MODE_DEFAULT, FeatureFlags

        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        flags = FeatureFlags.__new__(FeatureFlags)
        flags._get_redis = AsyncMock(return_value=redis)
        flags._enforcement_default_logged = False

        assert await flags.get_enforcement_mode() == PROVISIONED_ENFORCEMENT_MODE_DEFAULT
        assert PROVISIONED_ENFORCEMENT_MODE_DEFAULT != EnforcementMode.DISABLED


class TestTheDegradedModeStillRunsAndRecordsTheCheck:
    """The wiring, not the helper.

    Every test above pins `_get_enforcement_mode` in isolation. A correct
    resolver whose *consumer* still short-circuits would leave all of them
    green while the check remained inert — which is the shape of the bug being
    fixed, one level up. So this drives `validate_ownership` itself, with a real
    ownership mismatch, and asserts the violation is both allowed **and**
    recorded.
    """

    @pytest.mark.asyncio
    async def test_a_mismatch_during_an_outage_is_allowed_but_audited(self):
        validator = _validator(_flags_raising(EnforcementModeUnavailable("redis down")))
        validator.get_session_owner = AsyncMock(return_value="alice")
        validator._is_org_admin_access = AsyncMock(return_value=False)
        validator._audit_log_violation = MagicMock()
        validator._record_violation_metrics = AsyncMock()
        validator._get_authenticated_user = MagicMock(return_value={"username": "bob", "auth_disabled": False})

        auth = MagicMock()
        auth.enable_auth = True
        with patch("security.session_ownership.get_auth_middleware", return_value=auth):
            result = await validator.validate_ownership("sess-1234abcd", MagicMock())

        # Allowed — log_only does not block, so no request that works today breaks.
        assert result["authorized"] is True
        assert result["reason"] == "log_only_mode"
        assert result["actual_owner"] == "alice"

        # ...but the check ran and the violation was recorded. Under the pre-fix
        # "disabled" mode this path was short-circuited before the ownership
        # lookup, so neither of these was ever called.
        validator._audit_log_violation.assert_called_once()
        validator._record_violation_metrics.assert_awaited_once()
        assert (
            validator.get_session_owner.await_count >= 1
        ), "the ownership lookup never ran — the check is still being skipped"

    @pytest.mark.asyncio
    async def test_a_deliberate_disabled_still_short_circuits(self):
        """The contrast case, so the test above cannot pass for the wrong reason."""
        validator = _validator(_flags_returning(EnforcementMode.DISABLED))
        validator.get_session_owner = AsyncMock(return_value="alice")
        validator._is_org_admin_access = AsyncMock(return_value=False)
        validator._audit_log_violation = MagicMock()
        validator._record_violation_metrics = AsyncMock()
        validator._get_authenticated_user = MagicMock(return_value={"username": "bob", "auth_disabled": False})

        auth = MagicMock()
        auth.enable_auth = True
        with patch("security.session_ownership.get_auth_middleware", return_value=auth):
            result = await validator.validate_ownership("sess-1234abcd", MagicMock())

        assert result["authorized"] is True
        assert result["reason"] != "log_only_mode"
        validator._audit_log_violation.assert_not_called()
        assert (
            validator.get_session_owner.await_count == 0
        ), "a deliberate 'disabled' should still skip the lookup — that is policy, unchanged"
