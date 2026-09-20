# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Only a person's interactive login counts as a human decider (#17042)."""

import pytest

from autobot_shared.auth.interactive_principal import (
    LOGIN_TOKEN_TYPE,
    NON_LOGIN_CLAIMS,
    is_interactive_human,
    is_login_token,
)

_LOGIN_CLAIMS = {
    "username": "alice",
    "role": "user",
    "email": "a@example.test",
    "user_id": "u-1",
    "iat": 1,
    "token_type": LOGIN_TOKEN_TYPE,
}
_JWT_HUMAN = {"username": "alice", "role": "user", "auth_method": "jwt", "login_token": True}
_SESSION_HUMAN = {"username": "alice", "role": "user", "auth_method": "session"}
_WS_HUMAN = {"username": "alice", "role": "user", "auth_method": "jwt_websocket", "login_token": True}


def test_a_token_minted_as_a_login_is_a_login():
    assert is_login_token(_LOGIN_CLAIMS)


def test_a_token_without_the_login_type_is_not_a_login():
    """Absence of purpose claims is not evidence: a pre-2026-09-18 or foreign token is refused."""
    claims = {key: value for key, value in _LOGIN_CLAIMS.items() if key != "token_type"}
    assert not is_login_token(claims)


@pytest.mark.parametrize("token_type", ["device", "LOGIN", "", None, True])
def test_any_other_token_type_is_not_a_login(token_type):
    assert not is_login_token({**_LOGIN_CLAIMS, "token_type": token_type})


@pytest.mark.parametrize("claim", sorted(NON_LOGIN_CLAIMS))
def test_any_purpose_claim_disqualifies_even_a_login_typed_token(claim):
    for value in (True, False, None, "", "x"):
        assert not is_login_token({**_LOGIN_CLAIMS, claim: value}), (claim, value)


@pytest.mark.parametrize("user", [_JWT_HUMAN, _SESSION_HUMAN, _WS_HUMAN])
def test_a_login_jwt_session_or_websocket_login_is_a_human(user):
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
        ("websocket jwt without the login marker", {"username": "alice", "auth_method": "jwt_websocket"}),
        ("websocket jwt with a falsy login marker", {**_WS_HUMAN, "login_token": False}),
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
