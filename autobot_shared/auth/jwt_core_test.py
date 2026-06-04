# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for autobot_shared.auth.jwt_core (#3840).
"""

from datetime import timedelta

import pytest

from autobot_shared.auth.jwt_core import (
    JWTDecodeError,
    JWTExpiredError,
    decode_jwt,
    decode_jwt_or_none,
    encode_jwt,
    hash_password,
    verify_password,
)

_SECRET = "test-secret-key-for-unit-tests-only-32chars"


# ---------------------------------------------------------------------------
# encode_jwt / decode_jwt
# ---------------------------------------------------------------------------


def test_roundtrip_basic_payload() -> None:
    token = encode_jwt({"sub": "alice", "role": "admin"}, secret=_SECRET)
    payload = decode_jwt(token, secret=_SECRET)
    assert payload["sub"] == "alice"
    assert payload["role"] == "admin"


def test_expiry_from_expiry_hours() -> None:
    token = encode_jwt({"sub": "alice"}, secret=_SECRET, expiry_hours=1)
    payload = decode_jwt(token, secret=_SECRET)
    assert "exp" in payload


def test_expiry_from_expires_delta() -> None:
    token = encode_jwt({"sub": "alice"}, secret=_SECRET, expires_delta=timedelta(minutes=5))
    payload = decode_jwt(token, secret=_SECRET)
    assert "exp" in payload


def test_existing_exp_not_overwritten() -> None:
    from datetime import datetime, timezone

    future = int((datetime.now(tz=timezone.utc) + timedelta(hours=2)).timestamp())
    token = encode_jwt({"sub": "alice", "exp": future}, secret=_SECRET, expiry_hours=1)
    payload = decode_jwt(token, secret=_SECRET)
    # exp in payload should equal the value we put in, not the expiry_hours override
    assert payload["exp"] == future


def test_decode_wrong_secret_raises() -> None:
    token = encode_jwt({"sub": "alice"}, secret=_SECRET)
    with pytest.raises(JWTDecodeError):
        decode_jwt(token, secret="wrong-secret-key-for-unit-tests-only-32ch")


def test_decode_expired_token_raises_jwt_expired_error() -> None:
    token = encode_jwt({"sub": "alice"}, secret=_SECRET, expires_delta=timedelta(seconds=-1))
    with pytest.raises(JWTExpiredError):
        decode_jwt(token, secret=_SECRET)


def test_decode_malformed_token_raises_jwt_decode_error() -> None:
    with pytest.raises(JWTDecodeError):
        decode_jwt("not.a.jwt", secret=_SECRET)


# ---------------------------------------------------------------------------
# decode_jwt_or_none
# ---------------------------------------------------------------------------


def test_decode_jwt_or_none_returns_payload_on_success() -> None:
    token = encode_jwt({"sub": "bob"}, secret=_SECRET)
    result = decode_jwt_or_none(token, secret=_SECRET)
    assert result is not None
    assert result["sub"] == "bob"


def test_decode_jwt_or_none_returns_none_on_expired() -> None:
    token = encode_jwt({"sub": "bob"}, secret=_SECRET, expires_delta=timedelta(seconds=-1))
    assert decode_jwt_or_none(token, secret=_SECRET) is None


def test_decode_jwt_or_none_returns_none_on_invalid() -> None:
    assert decode_jwt_or_none("garbage", secret=_SECRET) is None


# ---------------------------------------------------------------------------
# hash_password / verify_password
# ---------------------------------------------------------------------------


def test_hash_and_verify_roundtrip() -> None:
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", hashed) is True


def test_verify_wrong_password_returns_false() -> None:
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("wrong-password", hashed) is False


def test_hash_produces_bcrypt_prefix() -> None:
    hashed = hash_password("some-password")
    assert hashed.startswith("$2b$")


def test_verify_bad_hash_returns_false() -> None:
    # Should not raise — returns False gracefully
    result = verify_password("any-password", "not-a-valid-hash")
    assert result is False
