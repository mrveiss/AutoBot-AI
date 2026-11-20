# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A shared chat can be unshared, a share never lapses, and the participant set is durable (#18890)."""

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.coordination.work_claims import ClaimConflictError
from models.session_share import SessionShare, SessionShareAdoption
from security import session_shares
from security.session_ownership import SessionOwnershipValidator

SESSION_ID = "0123456789abcdef0123456789abcdef"
ACTOR = {"user_id": "11111111-1111-1111-1111-111111111111", "username": "alice", "ip": "203.0.113.7"}


class FakeRedis:
    """Just the commands the share code uses; records TTLs so a silent expiry is visible."""

    def __init__(self):
        self.sets, self.ttls, self.kv = {}, {}, {}
        self.claim_held = False  # the adoption work claim, as held by some other worker

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
        return int(key in self.sets or key in self.kv)

    async def expire(self, key, ttl):
        self.ttls[key] = ttl

    async def persist(self, key):
        self.ttls.pop(key, None)

    async def set(self, key, value, nx=False, px=None):
        if nx and key in self.kv:
            return None
        self.kv[key] = value
        return True

    async def eval(self, script, numkeys, key, expected):
        if self.kv.get(key) == expected:
            del self.kv[key]
            return 1
        return 0

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
        await conn.run_sync(SessionShareAdoption.__table__.create)
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        engine, expire_on_commit=False
    )
    monkeypatch.setattr(session_shares, "_factory", lambda: factory)
    redis = FakeRedis()

    @asynccontextmanager
    async def claim(_scope, **_kw):
        if redis.claim_held:
            raise ClaimConflictError(MagicMock())
        redis.claim_held = True
        try:
            yield
        finally:
            redis.claim_held = False

    monkeypatch.setattr(session_shares, "work_claim", claim)
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

    assert await validator.unshare_session(SESSION_ID, "bob", ACTOR) is True

    assert not await validator.is_shared_with_user(SESSION_ID, "bob")
    assert await validator.is_shared_with_user(SESSION_ID, "carol")
    assert SESSION_ID not in await validator.get_shared_sessions("bob")


@pytest.mark.asyncio
async def test_unshare_survives_a_redis_flush(env):
    validator, redis, _ = env
    await validator.share_session(SESSION_ID, ["bob", "carol"], "alice")
    await validator.unshare_session(SESSION_ID, "bob", ACTOR)
    redis.sets.clear()  # nothing reads Redis; the table is the record

    assert not await validator.is_shared_with_user(SESSION_ID, "bob")
    assert await validator.is_shared_with_user(SESSION_ID, "carol")


@pytest.mark.asyncio
async def test_share_never_expires(env):
    validator, redis, _ = env
    redis.sets["session:shared_with:" + SESSION_ID] = {"bob"}
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
    await validator.unshare_session(SESSION_ID, "bob", ACTOR)

    actions = [c.kwargs["action"].value for c in audit.call_args_list]
    assert actions == ["session.share", "session.unshare"]
    assert audit.call_args.kwargs["metadata"]["participants"] == ["bob"]


@pytest.mark.asyncio
async def test_a_participant_is_refused_like_an_outsider_and_nothing_changes(env):
    from api.chat_session_sharing import unshare_session

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
    from api.chat_session_sharing import unshare_session

    validator, _, _ = env
    await validator.share_session(SESSION_ID, ["bob"], "alice")
    request = MagicMock()
    request.method, request.url.path = "DELETE", "/x"

    with patch("api.chat_session_sharing.get_redis_client", AsyncMock(return_value=validator.redis)):
        await unshare_session(SESSION_ID, "bob", request, {"reason": "owner_match", "user_data": {"username": "alice"}})

    assert not await validator.is_shared_with_user(SESSION_ID, "bob")


@pytest.mark.asyncio
async def test_participant_list_is_owner_only_and_reads_the_table(env):
    from api.chat_session_sharing import list_session_participants

    validator, redis, _ = env
    await validator.share_session(SESSION_ID, ["carol", "bob"], "alice")
    redis.sets.clear()
    request = MagicMock()

    with patch("api.chat_session_sharing.get_redis_client", AsyncMock(return_value=redis)):
        listed = await list_session_participants(SESSION_ID, request, {"reason": "owner_match"})
    assert json.loads(listed.body)["data"]["participants"] == ["bob", "carol"]

    with pytest.raises(HTTPException) as refused:
        await list_session_participants(SESSION_ID, request, {"reason": "shared_access"})
    assert refused.value.status_code == 403


def _request():
    request = MagicMock()
    request.method, request.url.path = "POST", "/x"
    request.client.host = "203.0.113.7"
    return request


async def _rows():
    async with session_shares._factory()() as db:
        result = await db.execute(select(SessionShare.user_id, SessionShare.shared_by))
        return {u: by for u, by in result.all()}


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["log_only_mode", "org_admin", "shared_access", "something_new", None])
async def test_only_an_owner_equivalent_reason_manages_shares(env, reason):
    from api.chat_session_sharing import list_session_participants, share_session, unshare_session
    from api.schemas_chat import SessionShareRequest

    validator, _, _ = env
    await validator.share_session(SESSION_ID, ["bob"], "alice")
    ownership = {"reason": reason, "user_data": {"username": "mallory"}}

    for call in (
        unshare_session(SESSION_ID, "bob", _request(), ownership),
        list_session_participants(SESSION_ID, _request(), ownership),
        share_session(SESSION_ID, SessionShareRequest(share_with=["eve"]), _request(), ownership),
    ):
        with pytest.raises(HTTPException) as refused:
            await call
        assert refused.value.status_code == 403
        assert refused.value.detail == "You do not have permission to access this conversation"
    assert await _rows() == {"bob": "alice"}


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", sorted(session_shares.OWNER_REASONS))
async def test_every_owner_equivalent_reason_may_share(env, reason):
    from api.chat_session_sharing import share_session
    from api.schemas_chat import SessionShareRequest

    validator, _, _ = env
    owner = {"reason": reason, "user_data": {"username": "alice", "user_id": "u-1"}}
    with patch("api.chat_session_sharing.get_redis_client", AsyncMock(return_value=validator.redis)):
        await share_session(SESSION_ID, SessionShareRequest(share_with=["bob"]), _request(), owner)
    assert await _rows() == {"bob": "alice"}


@pytest.mark.asyncio
async def test_a_removed_user_cannot_be_re_shared_by_a_participant(env):
    from api.chat_session_sharing import share_session
    from api.schemas_chat import SessionShareRequest

    validator, _, _ = env
    await validator.share_session(SESSION_ID, ["bob", "carol"], "alice")
    await validator.unshare_session(SESSION_ID, "bob", ACTOR)

    participant = {"reason": "shared_access", "user_data": {"username": "carol"}}
    with pytest.raises(HTTPException):
        await share_session(SESSION_ID, SessionShareRequest(share_with=["bob"]), _request(), participant)

    assert not await validator.is_shared_with_user(SESSION_ID, "bob")


@pytest.mark.asyncio
async def test_adoption_inserts_missing_rows_only_and_keeps_shared_by(env):
    validator, redis, _ = env
    await session_shares.durable_add(SESSION_ID, ["bob"], "alice")
    redis.sets["session:shared_with:" + SESSION_ID] = {"bob", "dave"}

    await session_shares.adopt_redis_shares(redis)

    assert await _rows() == {"bob": "alice", "dave": session_shares.ADOPTED_SHARER}


@pytest.mark.asyncio
async def test_a_reshare_does_not_rewrite_shared_by(env):
    validator, _, _ = env
    await validator.share_session(SESSION_ID, ["bob"], "alice")
    await validator.share_session(SESSION_ID, ["bob"], "someone-else")

    assert await _rows() == {"bob": "alice"}


@pytest.mark.asyncio
async def test_adoption_runs_once_and_never_resurrects_a_removed_user(env):
    validator, redis, _ = env
    redis.sets["session:shared_with:" + SESSION_ID] = {"bob", "carol"}
    await session_shares.adopt_redis_shares(redis)
    await validator.unshare_session(SESSION_ID, "bob", ACTOR)
    redis.sets["session:shared_with:" + SESSION_ID] = {"bob", "carol"}  # a stale copy turns up

    assert await session_shares.adopt_redis_shares(redis) == 0  # the durable marker, not a per-process flag
    assert await _rows() == {"carol": session_shares.ADOPTED_SHARER}


@pytest.mark.asyncio
async def test_adoption_does_not_rerun_when_the_redis_marker_is_lost(env):
    _, redis, _ = env
    await session_shares.adopt_redis_shares(redis)
    assert await session_shares.durable_adopted()
    redis.kv.clear()  # a restore dropped the Redis marker
    redis.sets["session:shared_with:" + SESSION_ID] = {"bob"}  # a legacy key came back

    assert await session_shares.adopt_redis_shares(redis) == 0
    assert await _rows() == {}
    assert redis.kv[session_shares.ADOPTED_KEY] == "1"  # the cache is re-written from the durable row


@pytest.mark.asyncio
async def test_a_share_removed_after_adoption_is_not_resurrected_by_stale_legacy_keys(env):
    validator, redis, _ = env
    redis.sets["session:shared_with:" + SESSION_ID] = {"bob", "carol"}
    await session_shares.adopt_redis_shares(redis)
    await validator.unshare_session(SESSION_ID, "bob", ACTOR)
    redis.kv.clear()
    redis.sets.clear()
    redis.sets["session:shared_with:" + SESSION_ID] = {"bob", "carol"}  # stale legacy keys reappear
    redis.sets["user:shared_sessions:bob"] = {SESSION_ID}

    await session_shares.adopt_redis_shares(redis)

    assert await _rows() == {"carol": session_shares.ADOPTED_SHARER}


@pytest.mark.asyncio
async def test_unshare_before_adoption_adopts_first_then_removes(env):
    validator, redis, _ = env
    redis.sets["session:shared_with:" + SESSION_ID] = {"bob"}  # legacy, never adopted

    await validator.unshare_session(SESSION_ID, "bob", ACTOR)
    redis.sets.clear()

    assert not await validator.is_shared_with_user(SESSION_ID, "bob")


@pytest.mark.asyncio
async def test_a_failed_unshare_is_reported_and_changes_nothing(env, monkeypatch):
    validator, redis, _ = env
    await validator.share_session(SESSION_ID, ["bob"], "alice")

    async def boom(*_a):
        raise ConnectionError("postgres down")

    monkeypatch.setattr(session_shares, "durable_remove", boom)
    with pytest.raises(ConnectionError):
        await validator.unshare_session(SESSION_ID, "bob", ACTOR)

    # Not revoked, and honestly so: the row is untouched, so nothing can flip the outcome later.
    assert await _rows() == {"bob": "alice"}
    redis.sets.clear()
    assert await validator.is_shared_with_user(SESSION_ID, "bob")


@pytest.mark.asyncio
async def test_participant_list_adopts_legacy_shares_first(env):
    from api.chat_session_sharing import list_session_participants

    validator, redis, _ = env
    redis.sets["session:shared_with:" + SESSION_ID] = {"legacy"}
    with patch("api.chat_session_sharing.get_redis_client", AsyncMock(return_value=redis)):
        listed = await list_session_participants(SESSION_ID, MagicMock(), {"reason": "owner_match"})
    assert json.loads(listed.body)["data"]["participants"] == ["legacy"]


@pytest.mark.asyncio
async def test_a_superseded_adopter_cannot_write_after_completion(env):
    _, _, _ = env
    await session_shares.durable_mark_adopted()
    await session_shares.durable_add_unless_adopted(SESSION_ID, ["bob"])
    assert await _rows() == {}


@pytest.mark.asyncio
async def test_adoption_rechecks_completion_after_taking_the_lock(env, monkeypatch):
    _, redis, _ = env
    answers = iter([False, True])  # incomplete at the first look, complete once this worker holds the lock

    async def is_adopted(_r):
        return next(answers)

    async def never(_r):
        raise AssertionError("scanned although adoption had completed")

    monkeypatch.setattr(session_shares, "_is_adopted", is_adopted)
    monkeypatch.setattr(session_shares, "_adopt_from_session_keys", never)
    assert await session_shares.adopt_redis_shares(redis) == 0
    assert not redis.claim_held


@pytest.mark.asyncio
async def test_a_worker_that_loses_the_adoption_lock_waits_then_fails(env, monkeypatch):
    _, redis, _ = env
    redis.claim_held = True
    monkeypatch.setattr(session_shares, "ADOPT_WAIT_SECONDS", 0)

    with pytest.raises(TimeoutError):
        await session_shares.adopt_redis_shares(redis)
    assert redis.claim_held  # not released by the loser


@pytest.mark.asyncio
async def test_a_worker_that_loses_the_lock_returns_once_the_marker_appears(env):
    _, redis, _ = env
    redis.claim_held = True
    redis.kv[session_shares.ADOPTED_KEY] = "1"

    assert await session_shares.adopt_redis_shares(redis) == 0


@pytest.mark.asyncio
async def test_startup_adoption_copies_shares_and_clears_every_ttl(env):
    from initialization.background_workers import adopt_chat_shares

    validator, redis, _ = env
    redis.sets["session:shared_with:s-1"] = {"bob"}
    redis.sets["user:shared_sessions:bob"] = {"s-1", "s-2"}  # s-2's session-side key already expired
    for key in ("session:shared_with:s-1", "user:shared_sessions:bob"):
        redis.ttls[key] = 1000

    with patch("autobot_shared.redis_client.get_redis_client", AsyncMock(return_value=redis)):
        await adopt_chat_shares()

    assert redis.ttls == {}
    redis.sets.clear()
    assert await validator.is_shared_with_user("s-1", "bob")
    assert await validator.is_shared_with_user("s-2", "bob")


@pytest.mark.asyncio
async def test_audit_records_the_uuid_and_client_ip_with_the_username_in_metadata(env):
    validator, _, audit = env
    request = _request()
    actor = session_shares.audit_actor(request, {"user_id": "u-uuid-1", "username": "alice"})

    await validator.share_session(SESSION_ID, ["bob"], "alice", actor)

    kwargs = audit.call_args.kwargs
    assert kwargs["user_id"] == "u-uuid-1"
    assert kwargs["ip_address"] == "203.0.113.7"
    assert kwargs["metadata"]["username"] == "alice"


@pytest.mark.asyncio
async def test_a_user_in_redis_but_absent_from_the_table_is_denied(env):
    """A leftover Redis entry (an old write racing an unshare, a stale key) grants nothing once adopted."""
    validator, redis, _ = env
    await validator.share_session(SESSION_ID, ["bob"], "alice")
    await session_shares.durable_remove(SESSION_ID, "bob")
    redis.sets["session:shared_with:" + SESSION_ID] = {"bob"}  # present in Redis, absent from the table
    redis.sets["user:shared_sessions:bob"] = {SESSION_ID}

    assert not await validator.is_shared_with_user(SESSION_ID, "bob")
    assert SESSION_ID not in await validator.get_shared_sessions("bob")


@pytest.mark.asyncio
async def test_a_legacy_redis_only_share_grants_access_before_adoption_has_run(env):
    validator, redis, _ = env
    redis.sets["session:shared_with:" + SESSION_ID] = {"legacy"}
    redis.sets["user:shared_sessions:legacy"] = {SESSION_ID}

    assert await validator.is_shared_with_user(SESSION_ID, "legacy")
    assert await validator.get_shared_sessions("legacy") == [SESSION_ID]


@pytest.mark.asyncio
async def test_sharing_writes_only_the_table(env):
    validator, redis, _ = env
    await validator.share_session(SESSION_ID, ["bob"], "alice")
    assert redis.sets == {}
    assert await validator.is_shared_with_user(SESSION_ID, "bob")
    await validator.unshare_session(SESSION_ID, "bob", ACTOR)
    assert not await validator.is_shared_with_user(SESSION_ID, "bob")
