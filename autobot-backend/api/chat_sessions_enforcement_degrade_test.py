# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A flag-store outage, seen from the route rather than from the validator (#14010).

`session_ownership_enforcement_mode_test.py` drives `SessionOwnershipValidator`
directly. That cannot see two things this file exists for:

1. **The construction path.** `validate_session_ownership` builds the validator
   with `feature_flags=None` whenever `get_feature_flags()` raises. Every test
   that constructs the validator itself passes `None` by hand and so asserts the
   handling while assuming the construction — which is the second, independent
   route to the same fail-open. Here `get_feature_flags` really raises and the
   dependency really constructs.

2. **Routing.** A test that calls the handler cannot tell a refusal from a route
   that does not exist, and a 404 makes a "was not allowed" assertion pass for
   the wrong reason. Every case below asserts the status is not 404, so the
   outcome is known to have come from the ownership decision.

The enforced case is here for the same reason: without it, "the degraded case
was not refused" would be satisfied by a harness incapable of refusing anything.

#15159 added the last section: the two ways of arriving at `log_only` produced
byte-identical decision records, separated only by the warning the section above
asserts. A log line is what a human greps; the record is what code reads, and an
audit trail or a #14010 AC4 measurement reads the record. Those tests assert on
the record the route was handed, never on log output.
"""

from __future__ import annotations

import contextlib
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import chat_sessions
from security.session_ownership import SessionOwnershipValidator
from services.feature_flags import EnforcementMode

OWNER = "alice"
INTRUDER = "bob"
SESSION_ID = "alices-chat"
EXPORT_PATH = f"/chat/sessions/{SESSION_ID}/export"
#: The ownership decision's own warnings. The mode resolver moved to
#: `security/enforcement_mode.py` with #15159, so the degrade warnings are
#: emitted under that name while the access decision still warns under the
#: validator's. Both are the ownership decision talking; filtering to one alone
#: would silently drop half the evidence.
LOGGER_NAMES = ("security.session_ownership", "security.enforcement_mode")
LOGGER_NAME = LOGGER_NAMES[0]


class _Spy:
    """What the ownership decision actually did, recorded across one request."""

    def __init__(self):
        self.owner_lookups = 0
        self.violations = 0
        self.decisions: list[dict] = []

    @property
    def decision(self) -> dict:
        """The single decision record this request produced."""
        assert len(self.decisions) == 1, f"expected exactly one ownership decision, got {len(self.decisions)}"
        return self.decisions[0]


@contextlib.contextmanager
def _real_dependency(flags, spy: _Spy):
    """Mount the router with the *real* `validate_session_ownership` dependency.

    Only the leaves are stubbed — Redis, the metrics service, the auth
    middleware and the ownership lookup. The construction of the validator, the
    resolution of the enforcement mode and the branch it takes are the code
    under test and are not patched.
    """

    async def _get_flags():
        if isinstance(flags, Exception):
            raise flags
        return flags

    async def _owner(_self, _session_id):
        spy.owner_lookups += 1
        return OWNER

    def _violation(_self, *_args, **_kwargs):
        spy.violations += 1

    real_validate = SessionOwnershipValidator.validate_ownership

    async def _validate(self, session_id, request):
        """Passthrough that records what the route was handed.

        The real method runs unchanged — this observes the decision, it does not
        make one — so the allow/deny assertions and the record assertions are
        reading the same single execution.
        """
        result = await real_validate(self, session_id, request)
        spy.decisions.append(result)
        return result

    auth = MagicMock()
    auth.enable_auth = True

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("services.feature_flags.get_feature_flags", _get_flags))
        stack.enter_context(patch("autobot_shared.redis_client.get_redis_client", AsyncMock(return_value=MagicMock())))
        stack.enter_context(patch("services.access_control_metrics.get_metrics_service", AsyncMock(return_value=None)))
        stack.enter_context(patch("security.session_ownership.get_auth_middleware", return_value=auth))
        stack.enter_context(patch.object(SessionOwnershipValidator, "get_session_owner", _owner))
        stack.enter_context(
            patch.object(SessionOwnershipValidator, "_is_org_admin_access", AsyncMock(return_value=False))
        )
        stack.enter_context(patch.object(SessionOwnershipValidator, "_audit_log_violation", _violation))
        stack.enter_context(patch.object(SessionOwnershipValidator, "validate_ownership", _validate))
        stack.enter_context(
            patch.object(SessionOwnershipValidator, "_record_violation_metrics", AsyncMock(return_value=None))
        )
        stack.enter_context(
            patch.object(
                SessionOwnershipValidator,
                "_get_authenticated_user",
                MagicMock(return_value={"username": INTRUDER, "user_id": "bob-id", "auth_disabled": False}),
            )
        )

        app = FastAPI()
        app.include_router(chat_sessions.router)
        yield TestClient(app, raise_server_exceptions=False)


def _ownership_warnings(caplog):
    """Warnings from the ownership decision only.

    `caplog` collects the whole root logger, so unrelated noise from the handler
    downstream of the decision (a stubbed Redis, a missing session file) would
    otherwise make "a deliberate disabled logs no warning" impossible to state.
    """
    return [r for r in caplog.records if r.levelno >= logging.WARNING and r.name in LOGGER_NAMES]


def _flags_returning(mode: EnforcementMode):
    flags = MagicMock()
    flags.get_enforcement_mode = AsyncMock(return_value=mode)
    flags.get_endpoint_enforcement = AsyncMock(return_value=None)
    return flags


class TestTheRouteExistsAndCanRefuse:
    """The control case. Without it nothing below means anything."""

    def test_an_enforced_mode_refuses_a_non_owner_at_the_route(self):
        spy = _Spy()
        with _real_dependency(_flags_returning(EnforcementMode.ENFORCED), spy) as client:
            response = client.get(EXPORT_PATH)

        assert response.status_code != 404, "the export route did not resolve; a 404 would fake every refusal here"
        assert response.status_code == 403
        assert spy.owner_lookups >= 1, "the refusal did not come from an ownership lookup"


class TestAFailedFlagsServiceDoesNotSkipTheCheck:
    """The construction path: `get_feature_flags()` raising is an outage, not a policy."""

    def test_the_ownership_lookup_still_runs_and_the_violation_is_recorded(self):
        spy = _Spy()
        with _real_dependency(RuntimeError("flag store unreachable"), spy) as client:
            response = client.get(EXPORT_PATH)

        assert response.status_code != 404, "the export route did not resolve"
        # log_only is the shipped degraded posture: allowed, but not silently.
        assert response.status_code != 403
        assert spy.owner_lookups >= 1, (
            "the ownership lookup never ran during a flag-store outage — the check is being skipped, "
            "which is the #14010 fail-open"
        )
        assert spy.violations == 1, "the violation was not audited during the outage"

    def test_the_degrade_is_audible_from_a_real_request(self, caplog):
        spy = _Spy()
        with caplog.at_level(logging.WARNING):
            with _real_dependency(RuntimeError("flag store unreachable"), spy) as client:
                client.get(EXPORT_PATH)

        warnings = [r.getMessage() for r in _ownership_warnings(caplog)]

        assert warnings, "a whole request served with an undetermined enforcement mode logged no warning"
        assert any("14010" in m and "log_only" in m for m in warnings), (
            "no warning identified the degrade; an operator reading the logs cannot tell this request "
            "from one served under a deliberate policy"
        )


class TestADeliberateDisabledStaysDistinguishableAtTheRoute:
    """The contrast, at the same level. Policy is unchanged by #14010."""

    def test_it_skips_the_lookup_and_logs_no_warning(self, caplog):
        spy = _Spy()
        with caplog.at_level(logging.WARNING):
            with _real_dependency(_flags_returning(EnforcementMode.DISABLED), spy) as client:
                response = client.get(EXPORT_PATH)

        assert response.status_code != 404, "the export route did not resolve"
        assert spy.owner_lookups == 0, "a deliberate 'disabled' should still short-circuit — that is policy, unchanged"
        assert not _ownership_warnings(caplog), (
            "a deliberate 'disabled' now warns like an outage does; the two states are no longer "
            "tellable apart from the logs of a real request"
        )


#: How each way of arriving at an enforcement mode is wired into the harness,
#: keyed by what an operator would call it. Enumerated rather than repeated in
#: each test so a fifth resolution cannot be added without a line here.
RESOLUTIONS: dict[str, object] = {
    "chosen log_only": _flags_returning(EnforcementMode.LOG_ONLY),
    "degraded log_only": RuntimeError("flag store unreachable"),
    "deliberate disabled": _flags_returning(EnforcementMode.DISABLED),
    "enforced": _flags_returning(EnforcementMode.ENFORCED),
}

#: What each resolution did *before* #15159, pinned as data: the HTTP status a
#: non-owner got, and whether the ownership lookup ran. #15159 changes what the
#: decision records and nothing about what it does, so every one of these has to
#: still hold afterwards.
PRE_15159_BEHAVIOUR: dict[str, tuple[bool, int]] = {
    # name: (refused with 403, ownership lookups)
    "chosen log_only": (False, 1),
    "degraded log_only": (False, 1),
    "deliberate disabled": (False, 0),
    "enforced": (True, 1),
}


class TestAllowDenyIsUnchangedByTheMarker:
    """The boundary #15159 must not cross.

    `log_only` means allow-and-audit, deliberately: denying on a degraded read
    would turn a flag blip into a platform-wide read outage (#14010, owner
    ruling). Adding a marker to the record is only safe if the record is all it
    adds, so the outcome of every resolution is pinned here as data rather than
    left to be re-derived per test.
    """

    def test_the_behaviour_table_covers_every_resolution(self):
        """A table that drifts from the enumeration stops covering a case silently."""
        assert RESOLUTIONS, "the resolution enumeration is empty; the tests below assert nothing"
        assert set(RESOLUTIONS) == set(PRE_15159_BEHAVIOUR), (
            "a resolution has no pinned pre-#15159 behaviour; add it deliberately rather than "
            "letting it drop out of the invariance check"
        )

    @pytest.mark.parametrize("resolution", list(RESOLUTIONS))
    def test_each_resolution_allows_or_denies_exactly_as_it_did(self, resolution):
        refuses, expected_lookups = PRE_15159_BEHAVIOUR[resolution]
        spy = _Spy()

        with _real_dependency(RESOLUTIONS[resolution], spy) as client:
            response = client.get(EXPORT_PATH)

        assert response.status_code != 404, "the export route did not resolve; a 404 fakes every outcome here"
        assert (response.status_code == 403) is refuses, (
            f"'{resolution}' now {'allows' if refuses else 'refuses'} a non-owner where it "
            f"{'refused' if refuses else 'allowed'} before — #15159 may only change what the decision records"
        )
        assert spy.owner_lookups == expected_lookups, (
            f"'{resolution}' changed whether the ownership lookup runs " f"({spy.owner_lookups} vs {expected_lookups})"
        )


class TestTheDecisionRecordSeparatesADegradedLogOnlyFromAChosenOne:
    """#15159 itself, asserted on the record and never on log output.

    The log is the weak distinguisher this issue exists to replace: a side effect
    on another stream, invisible to an audit record, a metric, or the #14010 AC4
    measurement that has to know whether the window it counted was healthy.
    """

    def _decision_for(self, resolution: str) -> dict:
        spy = _Spy()
        with _real_dependency(RESOLUTIONS[resolution], spy) as client:
            response = client.get(EXPORT_PATH)
        assert response.status_code != 404, "the export route did not resolve"
        return spy.decision

    def test_a_chosen_log_only_reports_the_plain_reason(self):
        decision = self._decision_for("chosen log_only")

        assert decision["reason"] == "log_only_mode"
        assert decision["enforcement_degraded"] is False

    def test_a_degraded_log_only_is_marked_as_degraded(self):
        decision = self._decision_for("degraded log_only")

        assert decision["enforcement_degraded"] is True, (
            "a log_only reached because the flag store could not be read reports itself as a chosen "
            "posture — an AC4 measurement cannot exclude the outage window"
        )
        assert decision["reason"] != "log_only_mode"
        assert "degraded" in decision["reason"]

    def test_the_two_log_only_reasons_do_not_converge(self):
        """The decisive assertion: same mode, same outcome, different provenance."""
        chosen = self._decision_for("chosen log_only")
        degraded = self._decision_for("degraded log_only")

        assert chosen["authorized"] is degraded["authorized"] is True, "the two must still behave identically"
        assert chosen["reason"] != degraded["reason"], (
            "a never-seeded install and a flag-store outage produce the same decision record again; "
            "nothing in the record says which population a log_only violation belongs to (#15159)"
        )

    def test_the_marker_takes_both_values_and_is_not_a_constant(self):
        """A field that exists and never varies distinguishes nothing.

        Wiring the marker in but never setting it would leave every assertion
        that only checks its presence green. This one fails on that mutation.
        """
        observed = {
            self._decision_for(name)["enforcement_degraded"] for name in ("chosen log_only", "degraded log_only")
        }

        assert observed == {True, False}, (
            f"the degraded marker only ever took {observed!r} — it is present but inert, and the two "
            "log_only states are still indistinguishable in the record"
        )
