# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Both callers of the shared unverified-claims decoder keep their own error contract (#17856)."""

import base64
import json

import pytest

from a2a.peer_identity import jwt_subject_for_audit
from llm_shared.provider_auth import ProviderAuthError, _decode_jwt_claims


def _token(payload: object) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).rstrip(b"=").decode("ascii")
    return f"h.{body}.s"


def test_peer_identity_returns_the_subject() -> None:
    assert jwt_subject_for_audit("Bearer " + _token({"sub": "peer-1"})) == "peer-1"


@pytest.mark.parametrize("token", ["only.two", "h.!!!.s", _token([1]), _token({"no": "sub"})])
def test_peer_identity_returns_none_on_any_failure(token: str) -> None:
    assert jwt_subject_for_audit("Bearer " + token) is None


def test_provider_auth_returns_the_claims() -> None:
    assert _decode_jwt_claims(_token({"iss": "x", "aud": "c"})) == {"iss": "x", "aud": "c"}


@pytest.mark.parametrize(
    ("token", "message"),
    [
        ("only.two", "id_token is not a well-formed JWT"),
        (_token([1]), "id_token payload is not a JSON object"),
    ],
)
def test_provider_auth_raises_its_own_error_with_the_same_message(token: str, message: str) -> None:
    with pytest.raises(ProviderAuthError) as info:
        _decode_jwt_claims(token)
    assert str(info.value) == message


def test_provider_auth_undecodable_payload_message_prefix() -> None:
    with pytest.raises(ProviderAuthError, match=r"^id_token payload is undecodable: "):
        _decode_jwt_claims("h.!!!.s")
