# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A shared chat can be unshared, a share never lapses, and the participant set is durable (#18890)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.session_share import SessionShare
from security import session_shares
from security.session_ownership import SessionOwnershipValidator

SESSION_ID = "0123456789abcdef0123456789abcdef"


class FakeRedis:
    """Just the set commands the share code uses; records TTLs so a silent expiry is visible."""

    def __init__(self):
        self.sets, self.ttls = {}, {}

    async def sadd(self, key, *members):
        self.sets.setdefault(key, set()).update(members)

    async def srem(self, key, member):
        self.sets.get(key, set()).discard(member)
        if key in self.sets and not self.sets[key]:
            del self.sets[key]

    async def sismember(self, key, member):
        return member in self.sets.get(key, set())

    async def smembers(self, key):
        key = key.decode() if isinstance(key, bytes) else key
        return {m.encode() for m in self.sets.get(key, set())}

    async def exists(self, key):
        return int(key in self.sets)

    async def expire(self, key, ttl):
        self.ttls[key] = ttl

    async def persist(self, key):
        self.ttls.pop(key, None)

    async def scan_iter(self, match, count=0):
        prefix = match.rstrip("*")
        for key in list(self.sets):
            if key.startswith(prefix):
                yield key.encode()


@pytest.fixture
async def env(monkeypatch):
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    async with engine.begin() as conn:
        await conn.run_sync(SessionShare.__table__.create)
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        engine, expire_on_commit=False
    )
    monkeypatch.setattr(session_shares, "_factory", lambda: factory)
    monkeypatch.setattr(session_shares, "_adopted", False)
    redis = FakeRedis()
    validator = SessionOwnershipValidator.__new__(SessionOwnershipValidator)
    validator.redis = redis
    with patch("services.audit.audit.audit_record") as audit:
        yield validator, redis, audit
    await engine.dispose()


@pytest.mark.asyncio
async def test_removed_user_loses_read_access_immediately(env):
    validator, _, _ = env
    assert await validator.share_session(SESSION_ID, ["bob", "carol"], "alice")
    assert await validator.is_shared_with_user(SESSION_ID, "bob")

    assert await validator.unshare_session(SESSION_ID, "bob", "alice") is True

    assert not await validator.is_shared_with_user(SESSION_ID, "bob")
    assert await validator.is_shared_with_user(SESSION_ID, "carol")
    assert SESSION_ID not in await validator.get_shared_sessions("bob")


@pytest.mark.asyncio
async def test_unshare_survives_a_redis_flush(env):
    validator, redis, _ = env
    await validator.share_session(SESSION_ID, ["bob", "carol"], "alice")
    await validator.unshare_session(SESSION_ID, "bob", "alice")
    redis.sets.clear()  # the projection is gone; the table is the record

    assert not await validator.is_shared_with_user(SESSION_ID, "bob")
    assert await validator.is_shared_with_user(SESSION_ID, "carol")


@pytest.mark.asyncio
async def test_share_never_expires(env):
    validator, redis, _ = env
    redis.ttls["session:shared_with:" + SESSION_ID] = 99  # a legacy key still carrying the old 30-day TTL
    await validator.share_session(SESSION_ID, ["bob"], "alice")

    assert redis.ttls == {}


@pytest.mark.asyncio
async def test_redis_miss_is_rebuilt_from_the_table(env):
    validator, redis, _ = env
    await validator.share_session(SESSION_ID, ["bob"], "alice")
    redis.sets.clear()

    assert await validator.is_shared_with_user(SESSION_ID, "bob")
    assert await validator.get_shared_sessions("bob") == [SESSION_ID]


@pytest.mark.asyncio
async def test_redis_only_shares_on_an_installed_system_are_adopted(env):
    validator, redis, _ = env
    redis.sets["session:shared_with:" + SESSION_ID] = {"bob"}  # written by the pre-table code
    redis.ttls["session:shared_with:" + SESSION_ID] = 1000

    await validator.share_session(SESSION_ID, ["carol"], "alice")
    redis.sets.clear()

    assert await validator.is_shared_with_user(SESSION_ID, "bob")
    assert await validator.is_shared_with_user(SESSION_ID, "carol")


@pytest.mark.asyncio
async def test_share_and_unshare_each_write_an_audit_record(env):
    validator, _, audit = env
    await validator.share_session(SESSION_ID, ["bob"], "alice")
    await validator.unshare_session(SESSION_ID, "bob", "alice")

    actions = [c.kwargs["action"].value for c in audit.call_args_list]
    assert actions == ["session.share", "session.unshare"]
    assert audit.call_args.kwargs["metadata"] == {"participants": ["bob"]}


@pytest.mark.asyncio
async def test_a_participant_is_refused_like_an_outsider_and_nothing_changes(env):
    from api.chat_session_unshare import unshare_session

    validator, _, _ = env
    await validator.share_session(SESSION_ID, ["bob"], "alice")
    request = MagicMock()
    request.method, request.url.path = "DELETE", "/x"

    with pytest.raises(HTTPException) as refused:
        await unshare_session(SESSION_ID, "carol", request, {"reason": "shared_access", "user_data": {}})

    assert refused.value.status_code == 403
    assert refused.value.detail == "You do not have permission to access this conversation"
    assert await validator.is_shared_with_user(SESSION_ID, "bob")


@pytest.mark.asyncio
async def test_owner_unshare_endpoint_removes_the_participant(env):
    from api.chat_session_unshare import unshare_session

    validator, _, _ = env
    await validator.share_session(SESSION_ID, ["bob"], "alice")
    request = MagicMock()
    request.method, request.url.path = "DELETE", "/x"

    with patch("api.chat_session_unshare.get_redis_client", AsyncMock(return_value=validator.redis)):
        await unshare_session(SESSION_ID, "bob", request, {"reason": "owner_match", "user_data": {"username": "alice"}})

    assert not await validator.is_shared_with_user(SESSION_ID, "bob")


@pytest.mark.asyncio
async def test_participant_list_is_owner_only_and_reads_the_table(env):
    from api.chat_session_unshare import list_session_participants

    validator, redis, _ = env
    await validator.share_session(SESSION_ID, ["carol", "bob"], "alice")
    redis.sets.clear()
    request = MagicMock()

    listed = await list_session_participants(SESSION_ID, request, {"reason": "owner_match"})
    assert json.loads(listed.body)["data"]["participants"] == ["bob", "carol"]

    with pytest.raises(HTTPException) as refused:
        await list_session_participants(SESSION_ID, request, {"reason": "shared_access"})
    assert refused.value.status_code == 403
