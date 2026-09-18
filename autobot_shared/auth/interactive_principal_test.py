# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Only a person's interactive login counts as a human decider (#17042)."""

import pytest

from autobot_shared.auth.interactive_principal import NON_LOGIN_CLAIMS, is_interactive_human, is_login_token

_LOGIN_CLAIMS = {"username": "alice", "role": "user", "email": "a@example.test", "user_id": "u-1", "iat": 1}
_JWT_HUMAN = {"username": "alice", "role": "user", "auth_method": "jwt", "login_token": True}
_SESSION_HUMAN = {"username": "alice", "role": "user", "auth_method": "session"}


def test_a_login_token_carries_no_purpose_claim():
    assert is_login_token(_LOGIN_CLAIMS)


@pytest.mark.parametrize("claim", sorted(NON_LOGIN_CLAIMS))
def test_any_purpose_claim_disqualifies_a_token_whatever_its_value(claim):
    for value in (True, False, None, "", "x"):
        assert not is_login_token({**_LOGIN_CLAIMS, claim: value}), (claim, value)


@pytest.mark.parametrize("user", [_JWT_HUMAN, _SESSION_HUMAN])
def test_a_login_jwt_or_session_is_a_human(user):
    assert is_interactive_human(user)


@pytest.mark.parametrize(
    ("label", "user"),
    [
        ("nothing resolved", None),
        ("empty", {}),
        ("internal service key", {"username": "service:slm", "role": "admin", "service": True}),
        ("run JWT", {"username": "run:r1", "role": "run_jwt", "auth_method": "run_jwt"}),
        ("device JWT", {"username": "device:d1", "user_id": "u-1", "auth_method": "device_jwt"}),
        ("dev header", {"username": "dev_admin", "role": "admin", "auth_method": "development"}),
        ("auth disabled", {"user_id": "admin", "username": "admin", "role": "admin", "auth_disabled": True}),
        ("jwt without the login marker", {"username": "alice", "auth_method": "jwt"}),
        ("jwt with a falsy login marker", {**_JWT_HUMAN, "login_token": False}),
        ("jwt with a truthy non-bool marker", {**_JWT_HUMAN, "login_token": "yes"}),
        ("websocket jwt", {"username": "alice", "auth_method": "jwt_websocket", "login_token": True}),
        ("unknown method", {"username": "alice", "auth_method": "api_key"}),
        ("service flag on a session", {**_SESSION_HUMAN, "service": True}),
        ("auth-disabled flag on a jwt", {**_JWT_HUMAN, "auth_disabled": True}),
        ("service-named login", {**_JWT_HUMAN, "username": "service:backend"}),
        ("run-named session", {**_SESSION_HUMAN, "username": "run:r1"}),
        ("device-named login", {**_JWT_HUMAN, "username": "device:d1"}),
    ],
)
def test_everything_else_is_refused(label, user):
    assert not is_interactive_human(user), label
