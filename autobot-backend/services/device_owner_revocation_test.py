# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A device JWT dies with its owner's revocation marker (#20446, owner ruling 16).

Real tokens from ``mint_device_jwt`` go through the real ``validate_device_jwt`` and the real
shared marker gate. Only the stores are stood in: a ``fakeredis`` server for the marker and the
caches, and the testkit fake session for the device/user rows.
"""

import os
import secrets
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import fakeredis.aioredis
import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError

from autobot_shared.auth.jwt_core import JWTDecodeError, decode_jwt
from autobot_shared.auth.revocation_unavailable import REVOCATION_UNAVAILABLE_DETAIL
from autobot_shared.user_management.password_epoch import PASSWORD_EPOCH_PREFIX, set_password_epoch
from services.device_jwt import mint_device_jwt, validate_device_jwt
from testkit.fake_async_session import FakeAsyncSession, FakeResult

_SECRET = secrets.token_hex(32)


class _Server(fakeredis.aioredis.FakeRedis):
    """A Redis whose marker keys can be made unreadable, like an outage."""

    marker_down = False

    async def get(self, name, *args, **kwargs):
        if self.marker_down and str(name).startswith(PASSWORD_EPOCH_PREFIX):
            raise RedisConnectionError("down")
        return await super().get(name, *args, **kwargs)


@pytest.fixture(autouse=True)
def _env():
    os.environ["DEVICE_JWT_SECRET"] = _SECRET
    yield


@pytest.fixture
def redis():
    server = _Server(decode_responses=False)

    async def _client(*args, **kwargs):
        return server

    with (
        patch("services.device_jwt.get_async_redis_client", _client),
        patch("services.device_owner_revocation.get_async_redis_client", _client),
        patch("autobot_shared.user_management.password_epoch.get_async_redis_client", _client),
    ):
        yield server


def _rows(device_id: str, owner):
    """Answers for the two reads, in order: the device row, then the owner row (when asked)."""
    device = FakeResult([SimpleNamespace(id=device_id, revoked_at=None)])
    return [device, FakeResult([] if owner is None else [owner])]


def _database(device_id: str, owner="skip"):
    """Patch the session factory; ``owner`` is a row, ``None`` (no row) or "skip" (not read)."""
    session = FakeAsyncSession(results=_rows(device_id, None if owner == "skip" else owner), strict=True)

    async def _factory():
        yield session

    return patch("user_management.database.get_async_session", _factory), session


def _owner(username="alice", deleted_at=None):
    return SimpleNamespace(username=username, deleted_at=deleted_at)


def _token(user_id: str):
    device_id = str(uuid.uuid4())
    token = mint_device_jwt(device_id=device_id, user_id=user_id, scope="read")
    iat = int(decode_jwt(token, _SECRET, audience="autobot:device")["iat"])
    return device_id, token, iat


@pytest.mark.asyncio
async def test_owner_deactivated_marker_voids_the_device_token(redis):
    owner_id = str(uuid.uuid4())
    device_id, token, iat = _token(owner_id)
    await set_password_epoch("alice", now=iat + 10)  # what deactivation writes
    db, _ = _database(device_id, _owner())
    with db, pytest.raises(JWTDecodeError, match="revoked"):
        await validate_device_jwt(token)


@pytest.mark.asyncio
async def test_control_another_users_marker_leaves_this_device_working(redis):
    owner_id = str(uuid.uuid4())
    device_id, token, iat = _token(owner_id)
    await set_password_epoch("bob", now=iat + 10)
    db, _ = _database(device_id, _owner())
    with db:
        assert (await validate_device_jwt(token))["user_id"] == owner_id


@pytest.mark.asyncio
async def test_control_token_issued_after_the_marker_works(redis):
    owner_id = str(uuid.uuid4())
    device_id, token, iat = _token(owner_id)
    await set_password_epoch("alice", now=iat - 10)
    db, _ = _database(device_id, _owner())
    with db:
        assert (await validate_device_jwt(token))["device_id"] == device_id


@pytest.mark.asyncio
async def test_hard_deleted_owner_is_refused_without_any_marker(redis):
    device_id, token, _ = _token(str(uuid.uuid4()))
    db, _ = _database(device_id, None)
    with db, pytest.raises(JWTDecodeError, match="owner does not exist"):
        await validate_device_jwt(token)


@pytest.mark.asyncio
async def test_soft_deleted_owner_is_refused(redis):
    device_id, token, _ = _token(str(uuid.uuid4()))
    db, _ = _database(device_id, _owner(deleted_at=datetime.now(timezone.utc)))
    with db, pytest.raises(JWTDecodeError, match="owner does not exist"):
        await validate_device_jwt(token)


@pytest.mark.asyncio
async def test_username_owner_is_checked_by_name_with_no_user_read(redis):
    device_id, token, iat = _token("admin")  # the config-based account's id is its username
    await set_password_epoch("admin", now=iat + 10)
    db, session = _database(device_id)
    with db, pytest.raises(JWTDecodeError, match="revoked"):
        await validate_device_jwt(token)
    assert len(session.statements) == 1  # the device row only


@pytest.mark.asyncio
async def test_empty_user_id_claim_is_refused(redis):
    device_id, token, _ = _token("")
    db, _ = _database(device_id)
    with db, pytest.raises(JWTDecodeError, match="owner does not exist"):
        await validate_device_jwt(token)


@pytest.mark.asyncio
async def test_marker_store_down_is_the_shared_503(redis):
    device_id, token, _ = _token("admin")
    redis.marker_down = True
    db, _ = _database(device_id)
    with db, pytest.raises(HTTPException) as caught:
        await validate_device_jwt(token)
    assert caught.value.status_code == 503 and caught.value.detail == REVOCATION_UNAVAILABLE_DETAIL


@pytest.mark.asyncio
async def test_owner_read_failing_is_the_shared_503(redis):
    device_id, token, _ = _token(str(uuid.uuid4()))
    session = FakeAsyncSession(results=[FakeResult([SimpleNamespace(id=device_id, revoked_at=None)])], strict=True)

    async def _factory():
        yield session

    with patch("user_management.database.get_async_session", _factory), pytest.raises(HTTPException) as caught:
        await validate_device_jwt(token)  # the strict fake has no second answer: the owner read raises
    assert caught.value.status_code == 503


@pytest.mark.asyncio
async def test_owner_verdict_is_cached_so_repeat_requests_read_nothing_new(redis):
    device_id, token, _ = _token(str(uuid.uuid4()))
    db, session = _database(device_id, _owner())
    with db:
        await validate_device_jwt(token)
        await validate_device_jwt(token)
    assert len(session.statements) == 2  # device + owner once; the second request is cache-only


@pytest.mark.asyncio
async def test_a_503_survives_the_middleware_instead_of_becoming_a_401():
    from tests.conftest import load_real_auth_middleware  # noqa: PLC0415

    real = load_real_auth_middleware()
    request = SimpleNamespace(headers={"Authorization": "Bearer x"})
    err = HTTPException(status_code=503, detail=REVOCATION_UNAVAILABLE_DETAIL)

    async def _unavailable(_token):
        raise err

    with patch("services.device_jwt.validate_device_jwt", _unavailable), pytest.raises(HTTPException) as caught:
        await real.get_auth_middleware()._extract_user_from_device_jwt(request)
    assert caught.value is err
