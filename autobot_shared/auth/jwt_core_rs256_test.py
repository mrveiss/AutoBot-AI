# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""RS256 and algorithm-confusion tests for autobot_shared.auth.jwt_core (#10196)."""

from datetime import timedelta

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from autobot_shared.auth.jwt_core import (
    JWTDecodeError,
    JWTExpiredError,
    _peek_alg,
    decode_jwt,
    decode_jwt_multi,
    decode_jwt_no_verify_exp,
    decode_jwt_or_none,
    encode_jwt,
)

_HS256_SECRET = "test-hs256-secret-for-unit-tests-only-32chars"


# ---------------------------------------------------------------------------
# Fixtures: RSA keypair
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rsa_keypair():
    """Generate a test RSA-2048 keypair once per module."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    public_key = private_key.public_key()
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return pem_private, pem_public


@pytest.fixture(scope="module")
def rsa_keypair_b(rsa_keypair):
    """A second, different RSA keypair — used to test wrong-key rejection."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    public_key = private_key.public_key()
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return pem_private, pem_public


# ---------------------------------------------------------------------------
# encode_jwt / decode_jwt — RS256 round-trip
# ---------------------------------------------------------------------------


def test_rs256_roundtrip_basic(rsa_keypair):
    pem_priv, pem_pub = rsa_keypair
    token = encode_jwt({"sub": "alice", "role": "admin"}, private_key=pem_priv, algorithm="RS256")
    payload = decode_jwt(token, public_key=pem_pub, algorithms=["RS256"])
    assert payload["sub"] == "alice"
    assert payload["role"] == "admin"


def test_rs256_token_carries_kid(rsa_keypair):
    """Tokens signed with RS256 must embed the kid header."""
    pem_priv, pem_pub = rsa_keypair
    token = encode_jwt(
        {"sub": "alice"},
        private_key=pem_priv,
        algorithm="RS256",
        kid="autobot-1",
    )
    header = _peek_alg.__module__  # confirm module imported
    import jwt as _jwt

    unverified = _jwt.get_unverified_header(token)
    assert unverified.get("kid") == "autobot-1"
    assert unverified.get("alg") == "RS256"


def test_rs256_expiry_from_expiry_hours(rsa_keypair):
    pem_priv, pem_pub = rsa_keypair
    token = encode_jwt({"sub": "alice"}, private_key=pem_priv, algorithm="RS256", expiry_hours=1)
    payload = decode_jwt(token, public_key=pem_pub, algorithms=["RS256"])
    assert "exp" in payload


def test_rs256_expired_raises_jwt_expired_error(rsa_keypair):
    pem_priv, pem_pub = rsa_keypair
    token = encode_jwt(
        {"sub": "alice"},
        private_key=pem_priv,
        algorithm="RS256",
        expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(JWTExpiredError):
        decode_jwt(token, public_key=pem_pub, algorithms=["RS256"])


def test_rs256_wrong_public_key_raises_jwt_decode_error(rsa_keypair, rsa_keypair_b):
    """RS256 token verified with a different public key must be rejected."""
    pem_priv, _ = rsa_keypair
    _, pem_pub_b = rsa_keypair_b
    token = encode_jwt({"sub": "alice"}, private_key=pem_priv, algorithm="RS256")
    with pytest.raises(JWTDecodeError):
        decode_jwt(token, public_key=pem_pub_b, algorithms=["RS256"])


# ---------------------------------------------------------------------------
# Algorithm-confusion prevention (SECURITY-CRITICAL)
# ---------------------------------------------------------------------------


def test_algorithm_confusion_rs256_token_rejected_with_hs256_secret(rsa_keypair):
    """RS256 token MUST NOT verify when passed the HS256 secret.

    This is the primary algorithm-confusion attack vector.  PyJWT's
    ``algorithms=`` guard prevents it, and our own header-routing guard
    catches it before PyJWT is even called.
    """
    pem_priv, pem_pub = rsa_keypair
    token = encode_jwt({"sub": "alice"}, private_key=pem_priv, algorithm="RS256")
    with pytest.raises(JWTDecodeError):
        decode_jwt(token, secret=_HS256_SECRET, algorithms=["HS256"])


def test_algorithm_confusion_hs256_token_rejected_with_public_key(rsa_keypair):
    """HS256 token MUST NOT verify when passed an RSA public key."""
    _, pem_pub = rsa_keypair
    token = encode_jwt({"sub": "alice"}, secret=_HS256_SECRET, algorithm="HS256")
    with pytest.raises(JWTDecodeError):
        decode_jwt(token, public_key=pem_pub, algorithms=["RS256"])


def test_alg_none_rejected_rs256(rsa_keypair):
    """A manually-crafted ``alg=none`` token must be rejected.

    We fabricate an alg=none token by using PyJWT with options={"verify_signature":False}
    only to get the structure, then confirm our decode_jwt rejects it.
    """
    import base64
    import json

    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload_b = base64.urlsafe_b64encode(json.dumps({"sub": "evil"}).encode()).rstrip(b"=").decode()
    none_token = f"{header}.{payload_b}."

    _, pem_pub = rsa_keypair
    with pytest.raises(JWTDecodeError):
        decode_jwt(none_token, public_key=pem_pub, algorithms=["RS256"])


def test_algorithm_mismatch_in_algorithms_list_rejected(rsa_keypair):
    """RS256 token presented to an HS256-only allow-list is rejected."""
    pem_priv, _ = rsa_keypair
    token = encode_jwt({"sub": "alice"}, private_key=pem_priv, algorithm="RS256")
    with pytest.raises(JWTDecodeError):
        # algorithms=["HS256"] explicitly: token's RS256 alg is not in the list
        decode_jwt(token, secret=_HS256_SECRET, algorithms=["HS256"])


def test_encode_jwt_rejects_unsupported_algorithm():
    with pytest.raises(ValueError, match="Unsupported algorithm"):
        encode_jwt({"sub": "x"}, secret="s", algorithm="ES256")


# ---------------------------------------------------------------------------
# decode_jwt_no_verify_exp with RS256
# ---------------------------------------------------------------------------


def test_decode_jwt_no_verify_exp_rs256_expired_still_decodes(rsa_keypair):
    pem_priv, pem_pub = rsa_keypair
    token = encode_jwt(
        {"sub": "alice"},
        private_key=pem_priv,
        algorithm="RS256",
        expires_delta=timedelta(seconds=-60),
    )
    payload = decode_jwt_no_verify_exp(token, public_key=pem_pub, algorithms=["RS256"])
    assert payload["sub"] == "alice"


def test_decode_jwt_no_verify_exp_rs256_rejects_wrong_key(rsa_keypair, rsa_keypair_b):
    pem_priv, _ = rsa_keypair
    _, pem_pub_b = rsa_keypair_b
    token = encode_jwt({"sub": "alice"}, private_key=pem_priv, algorithm="RS256")
    with pytest.raises(JWTDecodeError):
        decode_jwt_no_verify_exp(token, public_key=pem_pub_b, algorithms=["RS256"])


def test_decode_jwt_no_verify_exp_rs256_algo_confusion_blocked(rsa_keypair):
    pem_priv, _ = rsa_keypair
    token = encode_jwt({"sub": "alice"}, private_key=pem_priv, algorithm="RS256")
    with pytest.raises(JWTDecodeError):
        decode_jwt_no_verify_exp(token, secret=_HS256_SECRET, algorithms=["HS256"])


# ---------------------------------------------------------------------------
# decode_jwt_or_none with RS256
# ---------------------------------------------------------------------------


def test_decode_jwt_or_none_rs256_success(rsa_keypair):
    pem_priv, pem_pub = rsa_keypair
    token = encode_jwt({"sub": "bob"}, private_key=pem_priv, algorithm="RS256")
    result = decode_jwt_or_none(token, public_key=pem_pub, algorithms=["RS256"])
    assert result is not None
    assert result["sub"] == "bob"


def test_decode_jwt_or_none_rs256_expired_returns_none(rsa_keypair):
    pem_priv, pem_pub = rsa_keypair
    token = encode_jwt(
        {"sub": "bob"},
        private_key=pem_priv,
        algorithm="RS256",
        expires_delta=timedelta(seconds=-1),
    )
    assert decode_jwt_or_none(token, public_key=pem_pub, algorithms=["RS256"]) is None


def test_decode_jwt_or_none_rs256_wrong_key_returns_none(rsa_keypair, rsa_keypair_b):
    pem_priv, _ = rsa_keypair
    _, pem_pub_b = rsa_keypair_b
    token = encode_jwt({"sub": "bob"}, private_key=pem_priv, algorithm="RS256")
    assert decode_jwt_or_none(token, public_key=pem_pub_b, algorithms=["RS256"]) is None


# ---------------------------------------------------------------------------
# decode_jwt_multi — dual-accept migration helper
# ---------------------------------------------------------------------------


def test_decode_jwt_multi_accepts_rs256(rsa_keypair):
    pem_priv, pem_pub = rsa_keypair
    token = encode_jwt({"sub": "alice"}, private_key=pem_priv, algorithm="RS256")
    payload = decode_jwt_multi(token, public_key=pem_pub, hs256_secret=_HS256_SECRET)
    assert payload["sub"] == "alice"


def test_decode_jwt_multi_accepts_hs256_legacy(rsa_keypair):
    """Legacy HS256 tokens still accepted during migration window."""
    _, pem_pub = rsa_keypair
    token = encode_jwt({"sub": "legacy-user"}, secret=_HS256_SECRET)
    payload = decode_jwt_multi(token, public_key=pem_pub, hs256_secret=_HS256_SECRET)
    assert payload["sub"] == "legacy-user"


def test_decode_jwt_multi_rs256_rejected_with_wrong_public_key(rsa_keypair, rsa_keypair_b):
    pem_priv, _ = rsa_keypair
    _, pem_pub_b = rsa_keypair_b
    token = encode_jwt({"sub": "alice"}, private_key=pem_priv, algorithm="RS256")
    with pytest.raises(JWTDecodeError):
        decode_jwt_multi(token, public_key=pem_pub_b, hs256_secret=_HS256_SECRET)


def test_decode_jwt_multi_rs256_wrong_hs256_secret_is_irrelevant(rsa_keypair):
    """RS256 token routed to public-key path; wrong HS256 secret is not used."""
    pem_priv, pem_pub = rsa_keypair
    token = encode_jwt({"sub": "alice"}, private_key=pem_priv, algorithm="RS256")
    # Even with a garbage HS256 secret, RS256 verification works because the
    # secret is never used for RS256 tokens.
    payload = decode_jwt_multi(token, public_key=pem_pub, hs256_secret="garbage")
    assert payload["sub"] == "alice"


def test_decode_jwt_multi_hs256_wrong_secret_rejected(rsa_keypair):
    _, pem_pub = rsa_keypair
    token = encode_jwt({"sub": "alice"}, secret=_HS256_SECRET)
    with pytest.raises(JWTDecodeError):
        decode_jwt_multi(token, public_key=pem_pub, hs256_secret="wrong-secret-32charssssssssssssssss")


def test_decode_jwt_multi_expired_rs256_raises_jwt_expired_error(rsa_keypair):
    pem_priv, pem_pub = rsa_keypair
    token = encode_jwt(
        {"sub": "alice"},
        private_key=pem_priv,
        algorithm="RS256",
        expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(JWTExpiredError):
        decode_jwt_multi(token, public_key=pem_pub, hs256_secret=_HS256_SECRET)


# ---------------------------------------------------------------------------
# JWKS endpoint — public key round-trip
# ---------------------------------------------------------------------------


def test_jwks_n_e_reconstruct_signing_key_and_verify(rsa_keypair):
    """The n/e values in the JWK must reconstruct a key that verifies signed tokens."""
    import json

    from jwt.algorithms import RSAAlgorithm

    pem_priv, pem_pub = rsa_keypair

    # Simulate what the JWKS endpoint emits
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    public_key_obj = serialization.load_pem_public_key(pem_pub.encode(), backend=default_backend())
    base_jwk = json.loads(RSAAlgorithm.to_jwk(public_key_obj))
    base_jwk.update({"use": "sig", "alg": "RS256", "kid": "autobot-1"})
    base_jwk.pop("key_ops", None)

    # Reconstruct public key from JWK
    reconstructed_pub = RSAAlgorithm.from_jwk(json.dumps(base_jwk))

    # Mint a fresh token and verify with the reconstructed key
    token = encode_jwt({"sub": "alice"}, private_key=pem_priv, algorithm="RS256")
    payload = decode_jwt(token, public_key=reconstructed_pub, algorithms=["RS256"])  # type: ignore[arg-type]
    assert payload["sub"] == "alice"


# ---------------------------------------------------------------------------
# Backward compatibility: legacy HS256 callers unchanged
# ---------------------------------------------------------------------------


def test_hs256_encode_decode_still_works():
    """The positional (secret) HS256 API is unchanged — no regression."""
    token = encode_jwt({"sub": "alice"}, secret=_HS256_SECRET)
    payload = decode_jwt(token, secret=_HS256_SECRET)
    assert payload["sub"] == "alice"


def test_hs256_decode_jwt_or_none_positional_secret_still_works():
    """Positional call ``decode_jwt_or_none(token, secret)`` still works."""
    token = encode_jwt({"sub": "alice"}, secret=_HS256_SECRET)
    result = decode_jwt_or_none(token, _HS256_SECRET)
    assert result is not None
    assert result["sub"] == "alice"
