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
from services.feature_flags import EnforcementMode, EnforcementModeUnavailable

OWNER = "alice"
INTRUDER = "bob"
SESSION_ID = "alices-chat"
EXPORT_PATH = f"/chat/sessions/{SESSION_ID}/export"
LOGGER_NAME = "security.session_ownership"


class _Spy:
    """What the ownership decision actually did, recorded across one request."""

    def __init__(self):
        self.owner_lookups = 0
        self.violations = 0


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

    auth = MagicMock()
    auth.enable_auth = True

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("services.feature_flags.get_feature_flags", _get_flags))
        stack.enter_context(
            patch("autobot_shared.redis_client.get_redis_client", AsyncMock(return_value=MagicMock()))
        )
        stack.enter_context(
            patch("services.access_control_metrics.get_metrics_service", AsyncMock(return_value=None))
        )
        stack.enter_context(patch("security.session_ownership.get_auth_middleware", return_value=auth))
        stack.enter_context(patch.object(SessionOwnershipValidator, "get_session_owner", _owner))
        stack.enter_context(
            patch.object(SessionOwnershipValidator, "_is_org_admin_access", AsyncMock(return_value=False))
        )
        stack.enter_context(patch.object(SessionOwnershipValidator, "_audit_log_violation", _violation))
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
    return [r for r in caplog.records if r.levelno >= logging.WARNING and r.name == LOGGER_NAME]


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
        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
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
        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            with _real_dependency(_flags_returning(EnforcementMode.DISABLED), spy) as client:
                response = client.get(EXPORT_PATH)

        assert response.status_code != 404, "the export route did not resolve"
        assert spy.owner_lookups == 0, "a deliberate 'disabled' should still short-circuit — that is policy, unchanged"
        assert not _ownership_warnings(caplog), (
            "a deliberate 'disabled' now warns like an outage does; the two states are no longer "
            "tellable apart from the logs of a real request"
        )
