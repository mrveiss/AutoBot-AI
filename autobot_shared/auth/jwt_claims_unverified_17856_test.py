# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one unverified-claims decoder and its two callers' error contracts (#17856)."""

import base64
import json

import pytest

from autobot_shared.auth.jwt_core import decode_jwt_claims_unverified


def _token(payload: object) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).rstrip(b"=").decode("ascii")
    return f"h.{body}.s"


@pytest.mark.parametrize("claims", [{"sub": "a"}, {"sub": "ab"}, {"sub": "abc"}, {"x": 1, "sub": "é"}])
def test_every_padding_length_decodes(claims: dict) -> None:
    assert decode_jwt_claims_unverified(_token(claims)) == claims


@pytest.mark.parametrize(
    ("token", "message"),
    [
        ("only.two", "is not a well-formed JWT"),
        (_token([1, 2]), "payload is not a JSON object"),
        ("h.!!!.s", "payload is undecodable"),
        ("h.éé.s", "payload is undecodable"),
    ],
)
def test_malformed_tokens_raise_value_error(token: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        decode_jwt_claims_unverified(token)
