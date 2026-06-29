# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for SLM JWKS verifier (#10197).

Covers:
- Authority RS256 token verifies and yields normalized claims
- Algorithm-confusion: RS256 token must not verify via HS256 path
- alg=none rejected
- Legacy SLM HS256 token still verifies (via decode_token_async)
- Unknown kid triggers a JWKS refresh
- JWKS-unreachable returns None (no crash)
- Expired authority token rejected
- Claims normalization (username / sub / admin / authority_token)

The tests are isolated from the real backend: a test RSA keypair signs tokens
and a mocked httpx response serves the JWKS payload.
"""

from __future__ import annotations

import base64
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# ---------------------------------------------------------------------------
# Ensure autobot-slm-backend and autobot_shared are importable
# ---------------------------------------------------------------------------
_SLM_ROOT = Path(__file__).resolve().parent.parent
_SHARED_ROOT = _SLM_ROOT.parent / "autobot_shared"

for _p in [str(_SLM_ROOT), str(_SLM_ROOT.parent)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Stub heavy SLM deps before any import triggers them
import types as _types

for _name in [
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm",
    "models",
    "models.database",
    "models.schemas",
    "services.database",
    "services.deployment",
    "services.fleet_sync_guard",
    "services.reconciler",
    "services.role_registry",
    "services.service_categorizer",
    "services.service_orchestrator",
    "services.sync_orchestrator",
    "user_management",
    "user_management.models",
    "user_management.models.user",
    "user_management.database",
]:
    if _name not in sys.modules:
        _mod = MagicMock()
        _mod.__name__ = _name
        _mod.__package__ = _name.split(".")[0]
        _mod.__spec__ = None
        sys.modules[_name] = _mod

# Stub config before jwks_verifier imports it
_config_stub = _types.ModuleType("config")
_settings_stub = MagicMock()
_settings_stub.authority_base_url = (
    "http://localhost:8001"  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default
)
_settings_stub.authority_jwks_path = "/.well-known/jwks.json"
_settings_stub.jwks_cache_ttl_seconds = 3600
_settings_stub.jwks_fetch_timeout_seconds = 10.0
_settings_stub.secret_key = "test-hs256-secret-for-unit-tests-only-32ch"
_settings_stub.algorithm = "HS256"
_config_stub.settings = _settings_stub
sys.modules["config"] = _config_stub

# ---------------------------------------------------------------------------
# Now import the modules under test
# ---------------------------------------------------------------------------
from autobot_shared.auth.jwt_core import JWTDecodeError, encode_jwt  # noqa: E402
from services import jwks_verifier  # noqa: E402

# ---------------------------------------------------------------------------
# RSA keypair fixtures
# ---------------------------------------------------------------------------

_KID = "autobot-test-1"
_HS256_SECRET = "test-hs256-secret-for-unit-tests-only-32ch"


@pytest.fixture(scope="module")
def rsa_keypair():
    """Generate a test RSA-2048 keypair once per module."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pem_public = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return pem_private, pem_public


@pytest.fixture(scope="module")
def rsa_keypair_b():
    """A second RSA keypair — for wrong-key tests."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pem_public = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return pem_private, pem_public


# ---------------------------------------------------------------------------
# JWKS builder — converts a PEM public key to a JWKS JSON response dict
# ---------------------------------------------------------------------------


def _make_jwks(pem_public: str, kid: str = _KID) -> Dict[str, Any]:
    """Build a JWKS dict from a PEM public key, mimicking the backend response."""
    from cryptography.hazmat.primitives import serialization as _ser
    from jwt.algorithms import RSAAlgorithm

    pub_key_obj = _ser.load_pem_public_key(pem_public.encode("utf-8"), backend=default_backend())
    base_jwk = json.loads(RSAAlgorithm.to_jwk(pub_key_obj))
    base_jwk.pop("key_ops", None)
    base_jwk.update({"use": "sig", "alg": "RS256", "kid": kid})
    return {"keys": [base_jwk]}


def _make_authority_token(
    pem_private: str,
    claims: Dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Sign an RS256 authority token with the given private key."""
    payload = claims or {"username": "alice", "user_id": "uid-1", "role": "admin"}
    return encode_jwt(
        payload,
        private_key=pem_private,
        algorithm="RS256",
        kid=_KID,
        expires_delta=expires_delta if expires_delta is not None else timedelta(hours=1),
    )


# ---------------------------------------------------------------------------
# Helper: mock the httpx fetch inside jwks_verifier
# ---------------------------------------------------------------------------


def _mock_httpx_fetch(jwks_dict: Dict[str, Any] | None):
    """Return a context-manager patch that makes _fetch_jwks return jwks_dict."""

    async def _fake_fetch(url: str, timeout: float):
        return jwks_dict

    return patch.object(jwks_verifier, "_fetch_jwks", side_effect=_fake_fetch)


# ---------------------------------------------------------------------------
# Helpers — reset module-level cache between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_cache():
    """Clear the JWKS in-process cache before every test."""
    jwks_verifier._invalidate_cache()
    yield
    jwks_verifier._invalidate_cache()


# ---------------------------------------------------------------------------
# Test: authority RS256 token verifies + claims normalized
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authority_rs256_token_accepted_and_claims_normalized(rsa_keypair):
    pem_priv, pem_pub = rsa_keypair
    token = _make_authority_token(pem_priv, claims={"username": "alice", "user_id": "uid-1", "role": "admin"})
    jwks = _make_jwks(pem_pub)

    with _mock_httpx_fetch(jwks):
        result = await jwks_verifier.verify_authority_token(token)

    assert result is not None, "Valid authority RS256 token should verify"
    assert result["username"] == "alice"
    assert result["sub"] == "alice"
    assert result["role"] == "admin"
    assert result["admin"] is True
    assert result["authority_token"] is True


@pytest.mark.asyncio
async def test_authority_rs256_user_role_maps_admin_false(rsa_keypair):
    pem_priv, pem_pub = rsa_keypair
    token = _make_authority_token(pem_priv, claims={"username": "bob", "role": "user"})
    jwks = _make_jwks(pem_pub)

    with _mock_httpx_fetch(jwks):
        result = await jwks_verifier.verify_authority_token(token)

    assert result is not None
    assert result["admin"] is False
    assert result["role"] == "user"


# ---------------------------------------------------------------------------
# Test: algorithm-confusion — RS256 token MUST NOT verify via HS256
# ---------------------------------------------------------------------------


def test_algorithm_confusion_rs256_vs_hs256_direct():
    """The shared jwt_core guard rejects RS256 token when secret= only supplied."""
    # We can't call verify_authority_token with HS256 path — it routes to RS256.
    # Directly test that decode_jwt rejects the attempt.
    from cryptography.hazmat.backends import default_backend as _db
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

    from autobot_shared.auth.jwt_core import decode_jwt

    priv = _rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=_db())
    pem_priv = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode("utf-8")

    token = encode_jwt({"sub": "evil"}, private_key=pem_priv, algorithm="RS256")
    with pytest.raises(JWTDecodeError):
        decode_jwt(token, secret=_HS256_SECRET, algorithms=["HS256"])


# ---------------------------------------------------------------------------
# Test: alg=none rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alg_none_rejected():
    """A manually crafted alg=none token must be rejected by verify_authority_token."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload_b = base64.urlsafe_b64encode(json.dumps({"sub": "evil"}).encode()).rstrip(b"=").decode()
    none_token = f"{header}.{payload_b}."

    result = await jwks_verifier.verify_authority_token(none_token)
    assert result is None, "alg=none token must be rejected"


# ---------------------------------------------------------------------------
# Test: legacy SLM HS256 token still verifies via decode_token_async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_hs256_token_still_verifies():
    """Legacy SLM HS256 tokens accepted by decode_token_async HS256 path.

    Imports AuthService directly from the source file to bypass the
    sys.modules["services.auth"] MagicMock stub installed for other tests.
    """
    import importlib.util

    _auth_path = str(Path(__file__).parent / "auth.py")
    spec = importlib.util.spec_from_file_location("_auth_direct", _auth_path)
    _auth_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_auth_mod)  # type: ignore[union-attr]

    svc = _auth_mod.AuthService()
    token = encode_jwt({"sub": "legacy", "admin": True, "role": "admin"}, secret=_HS256_SECRET)
    payload = await svc.decode_token_async(token)
    assert payload is not None, "Legacy HS256 token should verify"
    assert payload["sub"] == "legacy"


# ---------------------------------------------------------------------------
# Test: sync decode_token returns None for RS256 tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_decode_token_returns_none_for_rs256(rsa_keypair):
    """Sync decode_token must not accept RS256 tokens — returns None."""
    import importlib.util

    pem_priv, _ = rsa_keypair
    token = _make_authority_token(pem_priv)

    _auth_path = str(Path(__file__).parent / "auth.py")
    spec = importlib.util.spec_from_file_location("_auth_direct2", _auth_path)
    _auth_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_auth_mod)  # type: ignore[union-attr]

    svc = _auth_mod.AuthService()
    result = svc.decode_token(token)
    assert result is None, "Sync decode_token must return None for RS256 tokens"


# ---------------------------------------------------------------------------
# Test: unknown kid triggers a refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_kid_triggers_refresh(rsa_keypair):
    """A token with a kid absent from the cache triggers exactly one refresh."""
    pem_priv, pem_pub = rsa_keypair
    token = _make_authority_token(pem_priv)
    jwks = _make_jwks(pem_pub)

    fetch_calls = []

    async def _counting_fetch(url: str, timeout: float):
        fetch_calls.append(url)
        return jwks

    with patch.object(jwks_verifier, "_fetch_jwks", side_effect=_counting_fetch):
        # Cache is empty; first call will trigger one fetch (TTL-expired path),
        # and since kid is present after that fetch no second fetch happens.
        result = await jwks_verifier.verify_authority_token(token)

    assert result is not None
    assert len(fetch_calls) == 1, "Should fetch exactly once when cache was empty"


@pytest.mark.asyncio
async def test_unknown_kid_after_stale_cache_triggers_second_refresh(rsa_keypair, rsa_keypair_b):
    """Stale cache with wrong kid triggers a refresh; if kid still absent → None."""
    pem_priv_a, pem_pub_a = rsa_keypair
    _, pem_pub_b = rsa_keypair_b

    # Pre-populate cache with keypair B's key (different kid)
    wrong_jwks = _make_jwks(pem_pub_b, kid="other-kid")
    good_jwks = _make_jwks(pem_pub_a, kid=_KID)

    # Token signed with keypair A (kid=_KID) but cache only has "other-kid"
    token = _make_authority_token(pem_priv_a)

    # Seed cache with wrong key so it looks "fresh" (non-expired)
    import time

    with patch.object(jwks_verifier, "_fetch_jwks", AsyncMock(return_value=wrong_jwks)):
        await jwks_verifier._refresh_cache("http://test", 10.0)

    # Now call with _KID absent → should refresh once and find it
    fetch_calls = []

    async def _second_fetch(url: str, timeout: float):
        fetch_calls.append(url)
        return good_jwks

    with patch.object(jwks_verifier, "_fetch_jwks", side_effect=_second_fetch):
        # Force cache as non-expired so only unknown-kid refresh fires
        jwks_verifier._cache_fetched_at = time.monotonic()
        result = await jwks_verifier.verify_authority_token(token)

    assert result is not None, "Should succeed after refresh revealed the correct kid"
    assert len(fetch_calls) == 1, "Exactly one refresh for unknown kid"


# ---------------------------------------------------------------------------
# Test: JWKS unreachable returns None (no crash)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jwks_unreachable_returns_none(rsa_keypair):
    """When the JWKS endpoint is unreachable, verify_authority_token returns None."""
    pem_priv, _ = rsa_keypair
    token = _make_authority_token(pem_priv)

    with _mock_httpx_fetch(None):  # _fetch_jwks returns None → unreachable
        result = await jwks_verifier.verify_authority_token(token)

    assert result is None, "JWKS-unreachable must return None without raising"


# ---------------------------------------------------------------------------
# Test: expired authority RS256 token rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_authority_token_rejected(rsa_keypair):
    pem_priv, pem_pub = rsa_keypair
    token = _make_authority_token(pem_priv, expires_delta=timedelta(seconds=-1))
    jwks = _make_jwks(pem_pub)

    with _mock_httpx_fetch(jwks):
        result = await jwks_verifier.verify_authority_token(token)

    assert result is None, "Expired RS256 token must be rejected"


# ---------------------------------------------------------------------------
# Test: wrong signing key rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_signing_key_rejected(rsa_keypair, rsa_keypair_b):
    """Token signed with keypair A but JWKS carries keypair B's key → rejected."""
    pem_priv_a, _ = rsa_keypair
    _, pem_pub_b = rsa_keypair_b

    token = _make_authority_token(pem_priv_a)
    jwks_with_wrong_key = _make_jwks(pem_pub_b, kid=_KID)

    with _mock_httpx_fetch(jwks_with_wrong_key):
        result = await jwks_verifier.verify_authority_token(token)

    assert result is None, "Token signed by different key must be rejected"


# ---------------------------------------------------------------------------
# Test: non-RS256 token passed to verify_authority_token returns None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hs256_token_to_verify_authority_returns_none():
    """verify_authority_token called with an HS256 token returns None (not crash)."""
    token = encode_jwt({"sub": "attacker"}, secret=_HS256_SECRET)
    result = await jwks_verifier.verify_authority_token(token)
    assert result is None


# ---------------------------------------------------------------------------
# Test: _normalize_claims handles sub-only tokens (legacy authority shape)
# ---------------------------------------------------------------------------


def test_normalize_claims_sub_only():
    """If authority token has sub but no username, sub is promoted to username."""
    payload = {"sub": "carol", "role": "user"}
    result = jwks_verifier._normalize_claims(payload)
    assert result["username"] == "carol"
    assert result["sub"] == "carol"
    assert result["admin"] is False
    assert result["authority_token"] is True


def test_normalize_claims_username_preferred_over_sub():
    """username claim takes precedence over sub for canonical identity."""
    payload = {"sub": "old-sub", "username": "alice", "role": "admin"}
    result = jwks_verifier._normalize_claims(payload)
    assert result["username"] == "alice"
    assert result["sub"] == "alice"
    assert result["admin"] is True
