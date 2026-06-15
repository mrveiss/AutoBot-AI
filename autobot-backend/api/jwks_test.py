# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the JWKS endpoint at /.well-known/jwks.json (#10196).

These tests exercise _build_jwks() directly (no FastAPI test client needed)
so they run without standing up the full backend stack.
"""

import json

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from autobot_shared.auth.jwt_core import decode_jwt, encode_jwt

# ---------------------------------------------------------------------------
# Helpers: minimal AuthenticationMiddleware stub
# ---------------------------------------------------------------------------


class _StubMiddleware:
    """Minimal stub that provides the attributes consumed by _build_jwks."""

    def __init__(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key()
        self.jwt_private_key = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        self.jwt_public_key = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        self.jwt_kid = "autobot-test-1"


@pytest.fixture(scope="module")
def stub_mw():
    return _StubMiddleware()


@pytest.fixture(scope="module")
def jwks_response(stub_mw, monkeypatch):
    """Build a JWKS dict using our stub middleware."""
    # Patch get_auth_middleware to return the stub
    from unittest.mock import patch

    import api.jwks as jwks_module

    with patch.object(jwks_module, "get_auth_middleware", return_value=stub_mw):
        return jwks_module._build_jwks()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_jwks_has_keys_list(stub_mw):
    from unittest.mock import patch

    import api.jwks as jwks_module

    with patch.object(jwks_module, "get_auth_middleware", return_value=stub_mw):
        jwks = jwks_module._build_jwks()
    assert "keys" in jwks
    assert len(jwks["keys"]) == 1


def test_jwks_key_fields(stub_mw):
    from unittest.mock import patch

    import api.jwks as jwks_module

    with patch.object(jwks_module, "get_auth_middleware", return_value=stub_mw):
        jwks = jwks_module._build_jwks()

    key = jwks["keys"][0]
    assert key["kty"] == "RSA"
    assert key["use"] == "sig"
    assert key["alg"] == "RS256"
    assert key["kid"] == "autobot-test-1"
    assert "n" in key
    assert "e" in key
    # "key_ops" is replaced by "use"
    assert "key_ops" not in key


def test_jwks_n_e_reconstruct_key_and_verify_token(stub_mw):
    """The JWK n/e values must reconstruct a key that verifies a freshly-minted token."""
    from unittest.mock import patch

    import api.jwks as jwks_module

    with patch.object(jwks_module, "get_auth_middleware", return_value=stub_mw):
        jwks = jwks_module._build_jwks()

    key_dict = jwks["keys"][0]

    # Reconstruct public key from JWK n/e
    reconstructed_pub = RSAAlgorithm.from_jwk(json.dumps(key_dict))

    # Mint a token with the stub's private key
    token = encode_jwt(
        {"sub": "test-user", "role": "admin"},
        private_key=stub_mw.jwt_private_key,
        algorithm="RS256",
        kid=stub_mw.jwt_kid,
    )

    # Verify using the reconstructed public key from the JWK
    payload = decode_jwt(token, public_key=reconstructed_pub, algorithms=["RS256"])  # type: ignore[arg-type]
    assert payload["sub"] == "test-user"
    assert payload["role"] == "admin"


def test_jwks_kid_matches_token_kid(stub_mw):
    """The kid in the JWK must match the kid embedded in signed tokens."""
    from unittest.mock import patch

    import jwt as _jwt

    import api.jwks as jwks_module

    with patch.object(jwks_module, "get_auth_middleware", return_value=stub_mw):
        jwks = jwks_module._build_jwks()

    key_kid = jwks["keys"][0]["kid"]

    token = encode_jwt(
        {"sub": "alice"},
        private_key=stub_mw.jwt_private_key,
        algorithm="RS256",
        kid=stub_mw.jwt_kid,
    )
    token_kid = _jwt.get_unverified_header(token)["kid"]
    assert key_kid == token_kid == stub_mw.jwt_kid
