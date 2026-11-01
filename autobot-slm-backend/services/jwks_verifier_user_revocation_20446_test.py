# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An RS256 authority token issued before its user's revocation marker is refused (#20446).

A real RS256 token, signed with a real key, goes through the real ``verify_authority_token``,
the real JWKS key lookup and the real shared marker rule (``password_epoch``). An authority token
names a user of the backend's database, whose markers the backend writes to Redis; the SLM keeps
its own users' markers in its database. The two stores are SEPARATE here, so a marker in only one
of them shows which one the verifier reads. Only storage is stood in for (a Redis, the SLM's
table, the claim cache, the jti denylist, the JWKS fetch).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm

from autobot_shared.auth.jwt_core import encode_jwt
from autobot_shared.user_management import password_epoch

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
    jwk = {"keys": [{**json.loads(RSAAlgorithm.to_jwk(key.public_key())), "kid": _KID, "use": "sig"}]}
    return pem, jwk


class _Markers:
    """The two marker stores: the backend's users' (Redis) and the SLM's own (its database)."""

    def __init__(self) -> None:
        self.redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        self.slm: dict[str, int] = {}

    async def in_redis(self, subject: str, epoch: int | None = None) -> None:
        await self.redis.set(f"{password_epoch.PASSWORD_EPOCH_PREFIX}{subject}", str(epoch or int(time.time())))

    def in_slm_table(self, subject: str, epoch: int | None = None) -> None:
        self.slm[subject] = epoch or int(time.time())


@pytest.fixture
def markers(key_pair):
    """The real marker rule over a Redis and a separate SLM store, with the JWKS served from the test key."""
    stores = _Markers()

    async def get_epoch(subject):
        return stores.slm.get(subject)

    password_epoch.use_epoch_store(get_epoch=get_epoch, set_epoch=AsyncMock())
    jwks_verifier._invalidate_cache()
    stubs = {"config": _config, "services.oidc_token_cache": _cache}
    with (
        patch.dict(sys.modules, stubs),
        patch.object(jwks_verifier, "_fetch_jwks", AsyncMock(return_value=key_pair[1])),
        patch.object(password_epoch, "get_async_redis_client", AsyncMock(return_value=stores.redis)),
    ):
        yield stores
    password_epoch.reset_epoch_store()


def _token(key_pair, username: str = "alice", age_seconds: int = 60) -> str:
    claims = {"username": username, "user_id": "uid-1", "role": "user", "iat": int(time.time()) - age_seconds}
    return encode_jwt(claims, private_key=key_pair[0], algorithm="RS256", kid=_KID, expiry_hours=1)


@pytest.mark.asyncio
async def test_a_live_users_token_is_admitted_and_carries_iat_and_username(key_pair, markers):
    claims = await jwks_verifier.verify_authority_token(_token(key_pair))
    assert claims["sub"] == "alice" and isinstance(claims["iat"], int)


@pytest.mark.asyncio
async def test_a_token_issued_before_the_users_redis_marker_is_refused(key_pair, markers):
    token = _token(key_pair)
    assert await jwks_verifier.verify_authority_token(token) is not None
    await markers.in_redis("alice")  # what the backend writes on deactivate, delete and password change
    assert await jwks_verifier.verify_authority_token(token) is None


@pytest.mark.asyncio
async def test_a_marker_only_in_the_slms_own_table_does_not_touch_an_authority_token(key_pair, markers):
    """That table holds the SLM's own users, who sign in with HS256 tokens; a same-named user is another account."""
    markers.in_slm_table("alice")
    assert await jwks_verifier.verify_authority_token(_token(key_pair)) is not None


@pytest.mark.asyncio
async def test_a_token_issued_after_the_marker_and_another_users_marker_are_admitted(key_pair, markers):
    await markers.in_redis("alice", int(time.time()) - 600)
    await markers.in_redis("bob")
    assert await jwks_verifier.verify_authority_token(_token(key_pair)) is not None


@pytest.mark.asyncio
async def test_a_cached_claim_set_is_refused_once_the_redis_marker_is_written(key_pair, markers):
    cached = {"sub": "alice", "username": "alice", "iat": int(time.time()) - 60, "authority_token": True}
    await markers.in_redis("alice")
    with patch.object(_cache, "get_cached_claims", AsyncMock(return_value=cached)):
        assert await jwks_verifier.verify_authority_token("cached-token") is None


@pytest.mark.asyncio
async def test_redis_that_cannot_answer_denies_with_the_shared_503_whatever_the_slm_store_says(key_pair, markers):
    with patch.object(password_epoch, "get_async_redis_client", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as denied:
            await jwks_verifier.verify_authority_token(_token(key_pair))
    assert denied.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["username", "iat"])
async def test_a_cached_claim_set_without_a_username_or_iat_is_refused(key_pair, markers, missing):
    cached = {"sub": "alice", "username": "alice", "iat": int(time.time()) - 60, "authority_token": True}
    cached[missing] = None
    with patch.object(_cache, "get_cached_claims", AsyncMock(return_value=cached)):
        assert await jwks_verifier.verify_authority_token("cached-token") is None


@pytest.mark.asyncio
async def test_a_signed_token_without_an_iat_is_refused_but_with_one_is_admitted(key_pair, markers):
    import jwt  # noqa: PLC0415

    claims = {"username": "alice", "role": "user", "exp": int(time.time()) + 3600}
    bare = jwt.encode(claims, key_pair[0], algorithm="RS256", headers={"kid": _KID})
    assert await jwks_verifier.verify_authority_token(bare) is None
    assert await jwks_verifier.verify_authority_token(_token(key_pair)) is not None
