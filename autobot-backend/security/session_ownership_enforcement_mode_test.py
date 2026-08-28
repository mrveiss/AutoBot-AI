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
    async def test_an_unset_flag_still_means_disabled(self):
        """The default posture is a separate decision (#14010 step 2) — untouched."""
        from services.feature_flags import FeatureFlags

        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        flags = FeatureFlags.__new__(FeatureFlags)
        flags._get_redis = AsyncMock(return_value=redis)
        flags._enforcement_default_logged = False

        assert await flags.get_enforcement_mode() == EnforcementMode.DISABLED


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


# ---------------------------------------------------------------------------
# The distinction itself, asserted in both directions (#14010 criterion 3).
#
# The tests above pin that the failure path is *audible*. On their own that is
# the vacuous half of "distinguishable": adding a `logger.warning` to the
# deliberate `disabled` branch would keep every one of them green while the two
# states became indistinguishable to whoever is reading the logs during an
# incident. What follows asserts the other direction — the deliberate path is
# silent, and no message is shared between the two — so the tests fail if the
# paths ever converge rather than only if the failure path goes quiet.
# ---------------------------------------------------------------------------

#: Every route by which the mode ends up *undetermined*, keyed by what an
#: operator would call it. Enumerated rather than written out three times so a
#: fourth route cannot be added without a line here; the tests below refuse to
#: run against an empty or under-populated mapping, because a test that iterates
#: nothing passes for free.
UNDETERMINED_ROUTES: dict[str, Exception | None] = {
    "flags service failed to construct": None,
    "flag store unreachable": EnforcementModeUnavailable("flag store unreachable"),
    "unexpected error resolving the mode": RuntimeError("unexpected failure"),
}

#: The exact routes #14010 lists. Pinned as a value so that deleting an entry
#: from ``UNDETERMINED_ROUTES`` breaks the suite instead of quietly shrinking
#: what every parametrized test below covers.
UNDETERMINED_ROUTE_NAMES = frozenset(
    {
        "flags service failed to construct",
        "flag store unreachable",
        "unexpected error resolving the mode",
    }
)


def _validator_for_route(route: str):
    """A validator wired for one of :data:`UNDETERMINED_ROUTES`."""
    failure = UNDETERMINED_ROUTES[route]
    return _validator(None if failure is None else _flags_raising(failure))


async def _records_from(validator, caplog) -> list[logging.LogRecord]:
    """Every record ``_get_enforcement_mode`` emits, at any level.

    Captured at DEBUG deliberately: the deliberate-`disabled` branch is expected
    to be quiet at WARNING, and a comparison that only ever looked at WARNING
    could not tell "logged nothing" from "logged the same thing one level down".
    """
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="security.session_ownership"):
        await validator._get_enforcement_mode()
    return list(caplog.records)


def test_the_route_enumeration_is_not_empty():
    """A parametrization over an empty mapping collects nothing and passes.

    This is the guard that stops every test in this section from becoming a
    no-op if ``UNDETERMINED_ROUTES`` is ever emptied or trimmed.
    """
    assert UNDETERMINED_ROUTES, "the undetermined-route enumeration is empty; the tests below assert nothing"
    assert set(UNDETERMINED_ROUTES) == UNDETERMINED_ROUTE_NAMES, (
        "the enumerated undetermined routes drifted from the three #14010 identifies; "
        "add the new route to UNDETERMINED_ROUTE_NAMES deliberately, do not let it disappear"
    )


def test_the_verbatim_parametrization_covers_every_mode():
    """`test_a_resolved_mode_is_returned_verbatim` is parametrized over a literal list.

    If a fourth `EnforcementMode` were added, that list would silently stop
    covering it — the parametrized test would keep passing over the old three.
    """
    covered = {
        mark.args[1][i]
        for mark in TestAPolicyDecisionIsUnchanged.test_a_resolved_mode_is_returned_verbatim.pytestmark
        if mark.name == "parametrize"
        for i in range(len(mark.args[1]))
    }

    assert covered, "the verbatim parametrization is empty"
    assert covered == set(
        EnforcementMode
    ), f"EnforcementMode members not covered verbatim: {set(EnforcementMode) - covered}"


class TestADeliberateDisabledIsDistinguishableFromAFailure:
    """#14010 criterion 3, asserted so that convergence fails the suite."""

    @pytest.mark.asyncio
    async def test_the_deliberate_path_is_silent_where_every_failure_route_warns(self, caplog):
        """The asymmetry *is* the distinction: one warns, the other does not."""
        assert UNDETERMINED_ROUTES, "nothing enumerated — this test would assert nothing"

        for route in UNDETERMINED_ROUTES:
            records = await _records_from(_validator_for_route(route), caplog)
            assert [
                r for r in records if r.levelno >= logging.WARNING
            ], f"the '{route}' route degraded without a warning — an outage would be silent"

        deliberate = await _records_from(_validator(_flags_returning(EnforcementMode.DISABLED)), caplog)

        assert not [r for r in deliberate if r.levelno >= logging.WARNING], (
            "a deliberate 'disabled' now warns like a failure does; the two states have converged "
            "in the logs and #14010 criterion 3 is no longer met"
        )

    @pytest.mark.asyncio
    async def test_no_message_is_shared_between_the_deliberate_and_failure_paths(self, caplog):
        """Different levels are not enough if the text is the same.

        An operator greps for a message, not for a level.
        """
        deliberate = {
            r.getMessage() for r in await _records_from(_validator(_flags_returning(EnforcementMode.DISABLED)), caplog)
        }

        for route in UNDETERMINED_ROUTES:
            failure = {r.getMessage() for r in await _records_from(_validator_for_route(route), caplog)}
            assert failure, f"the '{route}' route logged nothing at all"
            assert not (failure & deliberate), (
                f"the '{route}' route and a deliberate 'disabled' share log text {failure & deliberate!r} — "
                "the two are no longer tellable apart"
            )

    @pytest.mark.asyncio
    async def test_every_failure_route_says_it_is_not_a_deliberate_disabled(self, caplog):
        """The warning has to state the distinction, not merely be loud.

        A warning saying only "degrading to log_only" leaves the reader to infer
        whether someone chose it.
        """
        assert UNDETERMINED_ROUTES

        for route in UNDETERMINED_ROUTES:
            messages = " ".join(r.getMessage() for r in await _records_from(_validator_for_route(route), caplog))
            assert "log_only" in messages, f"the '{route}' warning does not say what it degraded to"
            assert "14010" in messages, f"the '{route}' warning does not point at the decision it is not making"

    @pytest.mark.asyncio
    async def test_the_specific_unavailable_handler_is_not_shadowed_by_the_generic_one(self, caplog):
        """Ordering, not just content.

        `except EnforcementModeUnavailable` sits before `except Exception`. Swap
        them and the specific message is never reached: both routes would report
        the generic "could not be resolved" wording, and every other test here
        would still pass because both still warn and both still degrade. This is
        the assertion that fails on that swap.
        """
        unavailable = " ".join(
            r.getMessage() for r in await _records_from(_validator_for_route("flag store unreachable"), caplog)
        )
        generic = " ".join(
            r.getMessage()
            for r in await _records_from(_validator_for_route("unexpected error resolving the mode"), caplog)
        )

        assert "UNDETERMINED" in unavailable, (
            "a declared EnforcementModeUnavailable was handled by the generic branch — "
            "the specific handler has been shadowed by reordering"
        )
        assert "could not be resolved" not in unavailable, "the flag-store failure fell through to the generic handler"
        assert (
            "could not be resolved" in generic
        ), "the generic handler no longer reports an unexpected failure distinctly"

    @pytest.mark.asyncio
    async def test_the_decision_reason_differs_between_a_deliberate_disabled_and_an_outage(self, caplog):
        """One level up: the value `validate_ownership` hands its caller.

        Log text is what a human reads; `reason` is what code reads. Both have
        to separate the two states, or a caller auditing results cannot tell an
        operator's decision from an outage either.
        """

        async def _reason_for(validator):
            validator.get_session_owner = AsyncMock(return_value="alice")
            validator._is_org_admin_access = AsyncMock(return_value=False)
            validator._audit_log_violation = MagicMock()
            validator._record_violation_metrics = AsyncMock()
            validator._get_authenticated_user = MagicMock(return_value={"username": "bob", "auth_disabled": False})
            auth = MagicMock()
            auth.enable_auth = True
            with patch("security.session_ownership.get_auth_middleware", return_value=auth):
                return (await validator.validate_ownership("sess-1234abcd", MagicMock()))["reason"]

        deliberate = await _reason_for(_validator(_flags_returning(EnforcementMode.DISABLED)))

        assert deliberate == "enforcement_disabled"

        for route in UNDETERMINED_ROUTES:
            degraded = await _reason_for(_validator_for_route(route))
            assert degraded != deliberate, (
                f"the '{route}' route now reports the same reason as a deliberate 'disabled' — "
                "a caller cannot tell an outage from a policy decision"
            )
            assert degraded != "enforcement_disabled"
