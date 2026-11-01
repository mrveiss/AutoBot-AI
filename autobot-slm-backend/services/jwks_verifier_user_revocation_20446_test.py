# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An RS256 authority token issued before its user's revocation marker is refused (#20446).

A real RS256 token, signed with a real key, goes through the real ``verify_authority_token``,
the real JWKS key lookup and the real shared marker rule (``password_epoch``). The marker is
written the way #20443 writes it on deactivate and delete: ``set_password_epoch(username)``.
Only storage is stood in for (the marker store, the claim cache, the jti denylist, the JWKS fetch).
"""

from __future__ import annotations

import importlib.util
import sys
import time
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm

from autobot_shared.auth.jwt_core import encode_jwt
from autobot_shared.user_management import password_epoch
from autobot_shared.user_management.password_epoch import RevocationCheckUnavailable

_SLM_ROOT = Path(__file__).resolve().parent.parent
_KID = "kid-20446"
_spec = importlib.util.spec_from_file_location("_jwks_verifier_20446", _SLM_ROOT / "services" / "jwks_verifier.py")
jwks_verifier = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jwks_verifier)

_config = types.ModuleType("config")
_config.settings = MagicMock(
    authority_base_url="http://authority.invalid", authority_jwks_path="/jwks", jwks_cache_ttl_seconds=3600
)
_config.settings.jwks_fetch_timeout_seconds = 5.0
_cache = types.ModuleType("services.oidc_token_cache")
_cache.get_cached_claims = AsyncMock(return_value=None)
_cache.cache_claims = AsyncMock(return_value=None)


@pytest.fixture(scope="module")
def key_pair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    jwk = {"keys": [{**__import__("json").loads(RSAAlgorithm.to_jwk(key.public_key())), "kid": _KID, "use": "sig"}]}
    return pem, jwk


@pytest.fixture
def markers(key_pair):
    """The real marker rule over an in-memory store, with the JWKS served from the test key."""
    store: dict[str, int] = {}

    async def get_epoch(subject):
        return store.get(subject)

    async def set_epoch(subject, *, now=None):
        store[subject] = int(time.time()) if now is None else now
        return store[subject]

    password_epoch.use_epoch_store(get_epoch=get_epoch, set_epoch=set_epoch)
    jwks_verifier._invalidate_cache()
    stubs = {"config": _config, "services.oidc_token_cache": _cache}
    with (
        patch.dict(sys.modules, stubs),
        patch.object(jwks_verifier, "_fetch_jwks", AsyncMock(return_value=key_pair[1])),
    ):
        yield store
    password_epoch.reset_epoch_store()


def _token(key_pair, username: str = "alice", age_seconds: int = 60) -> str:
    claims = {"username": username, "user_id": "uid-1", "role": "user", "iat": int(time.time()) - age_seconds}
    return encode_jwt(claims, private_key=key_pair[0], algorithm="RS256", kid=_KID, expiry_hours=1)


@pytest.mark.asyncio
async def test_a_live_users_token_is_admitted_and_carries_iat_and_username(key_pair, markers):
    claims = await jwks_verifier.verify_authority_token(_token(key_pair))
    assert claims["sub"] == "alice" and isinstance(claims["iat"], int)


@pytest.mark.asyncio
async def test_a_token_issued_before_the_users_marker_is_refused(key_pair, markers):
    token = _token(key_pair)
    assert await jwks_verifier.verify_authority_token(token) is not None
    await password_epoch.set_password_epoch("alice")  # what deactivate and delete write (#20443)
    assert await jwks_verifier.verify_authority_token(token) is None


@pytest.mark.asyncio
async def test_a_token_issued_after_the_marker_and_another_users_marker_are_admitted(key_pair, markers):
    await password_epoch.set_password_epoch("alice", now=int(time.time()) - 600)
    await password_epoch.set_password_epoch("bob")
    assert await jwks_verifier.verify_authority_token(_token(key_pair)) is not None


@pytest.mark.asyncio
async def test_a_cached_claim_set_is_refused_once_the_marker_is_written(key_pair, markers):
    cached = {"sub": "alice", "username": "alice", "iat": int(time.time()) - 60, "authority_token": True}
    await password_epoch.set_password_epoch("alice")
    with patch.object(_cache, "get_cached_claims", AsyncMock(return_value=cached)):
        assert await jwks_verifier.verify_authority_token("cached-token") is None


@pytest.mark.asyncio
async def test_a_marker_store_that_cannot_answer_denies_with_the_shared_503(key_pair, markers):
    password_epoch.use_epoch_store(
        get_epoch=AsyncMock(side_effect=RevocationCheckUnavailable("down")), set_epoch=AsyncMock()
    )
    with pytest.raises(HTTPException) as denied:
        await jwks_verifier.verify_authority_token(_token(key_pair))
    assert denied.value.status_code == 503
