# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A team-membership change reaches every worker's cached memberships through the ACL epoch (#19630).

The membership epoch lives in one fake Redis shared by every simulated worker; each worker owns its own
``tenant_groups._cache``. The team service is the real one, driven over a fake session.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cachetools import TTLCache

from autobot_shared import membership_epoch
from autobot_shared.db_session import POST_COMMIT_CALLBACKS, NoCommitScopeError, run_after_commit
from autobot_shared.user_management.base_service import TenantContext
from autobot_shared.user_management.team_service import TeamService
from knowledge import acl_epoch, tenant_groups

TEAM_T = uuid.UUID("77777777-7777-7777-7777-777777777777")
USER_U = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ORG_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
ORG_2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
_GET_USER_TEAMS = "autobot_shared.user_management.team_service.TeamService.get_user_teams"


class _FakeRedis:
    """The knowledge-database client: one token per key, shared by every worker."""

    def __init__(self) -> None:
        self.counters: dict[str, str] = {}
        self.fail_set = 0  # this many set calls fail first

    async def set(self, key: str, value: str, nx: bool = False):
        if self.fail_set:
            self.fail_set -= 1
            raise ConnectionError("redis down")
        if nx and key in self.counters:
            return None
        self.counters[key] = value
        return True

    async def get(self, key: str):
        return None if key not in self.counters else self.counters[key].encode()

    def evict(self, key: str) -> None:
        """allkeys-lru dropped the key."""
        self.counters.pop(key, None)

    def epoch(self, org) -> str | None:
        return self.counters.get(membership_epoch.membership_epoch_key(org))


@pytest.fixture
def redis_db():
    db = _FakeRedis()
    with (
        patch.object(membership_epoch, "get_async_redis_client", AsyncMock(return_value=db)),
        patch.object(membership_epoch, "MEMBERSHIP_EPOCH_BUMP_BACKOFF_SECONDS", 0.0),
    ):
        yield db


def _worker() -> TTLCache:
    return TTLCache(maxsize=16, ttl=3600)


def _tenant(org_id=ORG_1, user_id=USER_U) -> TenantContext:
    return TenantContext(org_id=org_id, user_id=user_id)


async def _groups_as(worker: TTLCache, memberships: dict, org_id=ORG_1) -> list[str]:
    """Resolve U's groups on *worker* against the live *memberships* table."""
    teams = AsyncMock(side_effect=lambda uid: [SimpleNamespace(id=t) for t in memberships[uid]])
    with patch.object(tenant_groups, "_cache", worker), patch(_GET_USER_TEAMS, teams):
        return await tenant_groups.tenant_group_ids(_tenant(org_id), MagicMock())


def _service(session) -> TeamService:
    """The real ``TeamService`` over *session*, with the persistence steps it is not testing stubbed."""
    service = TeamService(session, TenantContext(org_id=ORG_1))
    service.get_team = AsyncMock(return_value=SimpleNamespace(name="T", org_id=ORG_1))
    service._get_membership = AsyncMock(return_value=SimpleNamespace(role="member"))
    service._validate_membership_request = AsyncMock()
    service._create_membership_instance = MagicMock(return_value=SimpleNamespace())
    service._audit_log = AsyncMock()
    return service


def _session(with_commit_scope: bool = True) -> MagicMock:
    session = MagicMock()
    session.info = {POST_COMMIT_CALLBACKS: []} if with_commit_scope else {}
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    return session


async def _commit(session) -> None:
    from autobot_shared.db_session import (  # noqa: PLC0415 -- the scope's own post-commit step
        _run_post_commit_callbacks,
    )

    await _run_post_commit_callbacks(session)


@pytest.mark.asyncio
async def test_removing_a_member_drops_the_cached_team_in_every_worker(redis_db):
    memberships = {USER_U: [TEAM_T]}
    worker_a, worker_b = _worker(), _worker()
    assert await _groups_as(worker_a, memberships) == [str(TEAM_T)]
    assert await _groups_as(worker_b, memberships) == [str(TEAM_T)]

    memberships[USER_U] = []
    session = _session()
    await _service(session).remove_member(TEAM_T, USER_U)
    await _commit(session)

    assert await _groups_as(worker_a, memberships) == []
    assert await _groups_as(worker_b, memberships) == []


@pytest.mark.asyncio
async def test_without_a_bump_the_cache_still_serves_the_removed_team(redis_db):
    """Control: the TTL alone leaves the removed member in the team, so the bump is what drops it."""
    memberships = {USER_U: [TEAM_T]}
    worker = _worker()
    await _groups_as(worker, memberships)
    memberships[USER_U] = []
    assert await _groups_as(worker, memberships) == [str(TEAM_T)]


@pytest.mark.asyncio
async def test_deleting_a_team_drops_the_cached_team_of_all_its_members(redis_db):
    other = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    memberships = {USER_U: [TEAM_T], other: [TEAM_T]}
    worker = _worker()
    for uid in (USER_U, other):
        with (
            patch.object(tenant_groups, "_cache", worker),
            patch(_GET_USER_TEAMS, AsyncMock(return_value=[SimpleNamespace(id=TEAM_T)])),
        ):
            assert await tenant_groups.tenant_group_ids(_tenant(user_id=uid), MagicMock()) == [str(TEAM_T)]

    session = _session()
    await _service(session).delete_team(TEAM_T)
    await _commit(session)

    for uid in (USER_U, other):
        memberships[uid] = []
        with patch.object(tenant_groups, "_cache", worker), patch(_GET_USER_TEAMS, AsyncMock(return_value=[])):
            assert await tenant_groups.tenant_group_ids(_tenant(user_id=uid), MagicMock()) == []


@pytest.mark.asyncio
async def test_adding_a_member_does_not_bump_the_epoch(redis_db):
    """An add is a grant: a stale cache only delays it, so it must not flush anyone's cache."""
    session = _session()
    await _service(session).add_member(TEAM_T, USER_U)
    await _commit(session)
    assert redis_db.counters == {}


@pytest.mark.asyncio
async def test_the_bump_is_per_organisation_and_leaves_the_global_acl_epoch_alone(redis_db):
    session = _session()
    await _service(session).remove_member(TEAM_T, USER_U)
    await _commit(session)
    assert isinstance(redis_db.epoch(ORG_1), str) and redis_db.epoch(ORG_2) is None
    assert acl_epoch.ACL_EPOCH_KEY not in redis_db.counters


def test_the_membership_epoch_lives_in_the_same_database_as_the_acl_epoch():
    assert membership_epoch.MEMBERSHIP_EPOCH_DATABASE == acl_epoch.ACL_EPOCH_DATABASE
    assert acl_epoch.read_membership_epoch is membership_epoch.read_membership_epoch


@pytest.mark.asyncio
async def test_the_bump_runs_after_the_commit_not_before(redis_db):
    session = _session()
    await _service(session).remove_member(TEAM_T, USER_U)
    assert redis_db.epoch(ORG_1) is None  # flushed, not committed: a reader could still re-cache the old teams
    await _commit(session)
    assert isinstance(redis_db.epoch(ORG_1), str)


@pytest.mark.asyncio
async def test_two_revocations_in_one_transaction_queue_one_bump(redis_db):
    session = _session()
    service = _service(session)
    await service.remove_member(TEAM_T, USER_U)
    await service.delete_team(TEAM_T)
    assert len(session.info[POST_COMMIT_CALLBACKS]) == 1


@pytest.mark.asyncio
async def test_a_revocation_with_no_commit_scope_raises_instead_of_bumping_before_the_commit(redis_db):
    with pytest.raises(NoCommitScopeError):
        await _service(_session(with_commit_scope=False)).remove_member(TEAM_T, USER_U)
    assert redis_db.counters == {}


def test_run_after_commit_refuses_a_session_without_a_callback_list():
    with pytest.raises(NoCommitScopeError):
        run_after_commit(_session(with_commit_scope=False), membership_epoch.MembershipEpochBump(ORG_1))


@pytest.mark.asyncio
async def test_a_failed_bump_is_retried_and_logged(redis_db, caplog):
    redis_db.fail_set = 2
    with caplog.at_level("ERROR"):
        token = await membership_epoch.bump_membership_epoch(ORG_1)
    assert token == redis_db.epoch(ORG_1) and token != "1"
    assert caplog.text.count("bump failed") == 2


@pytest.mark.asyncio
async def test_a_bump_that_fails_every_try_raises_after_the_bounded_attempts(redis_db, caplog):
    redis_db.fail_set = 99
    with caplog.at_level("ERROR"), pytest.raises(membership_epoch.MembershipEpochBumpError):
        await membership_epoch.bump_membership_epoch(ORG_1)
    assert caplog.text.count("bump failed") == membership_epoch.MEMBERSHIP_EPOCH_BUMP_ATTEMPTS


@pytest.mark.asyncio
async def test_an_unreadable_epoch_re_resolves_and_caches_nothing():
    worker = _worker()
    teams = AsyncMock(return_value=[SimpleNamespace(id=TEAM_T)])
    with (
        patch.object(tenant_groups, "_cache", worker),
        patch(_GET_USER_TEAMS, teams),
        patch.object(tenant_groups, "read_membership_epoch", AsyncMock(return_value=None)),
    ):
        for _ in range(3):
            assert await tenant_groups.tenant_group_ids(_tenant(), MagicMock()) == [str(TEAM_T)]
    assert teams.await_count == 3 and len(worker) == 0


@pytest.mark.asyncio
async def test_an_unreadable_epoch_never_serves_an_entry_cached_under_a_readable_one(redis_db):
    memberships = {USER_U: [TEAM_T]}
    worker = _worker()
    await _groups_as(worker, memberships)
    memberships[USER_U] = []
    with patch.object(tenant_groups, "read_membership_epoch", AsyncMock(return_value=None)):
        assert await _groups_as(worker, memberships) == []


@pytest.mark.asyncio
async def test_the_team_lookup_is_scoped_to_the_active_organisation():
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result)
    await tenant_groups._lookup_team_ids(session, USER_U, ORG_1)
    statement = session.execute.await_args.args[0]
    assert ORG_1 in statement.compile().params.values()


@pytest.mark.asyncio
async def test_a_tenant_with_no_organisation_gets_no_groups_and_no_lookup(redis_db):
    teams = AsyncMock(return_value=[SimpleNamespace(id=TEAM_T)])
    with patch.object(tenant_groups, "_cache", _worker()), patch(_GET_USER_TEAMS, teams):
        assert await tenant_groups.tenant_group_ids(_tenant(org_id=None), MagicMock()) == []
    teams.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_cache_key_carries_the_organisation(redis_db):
    worker = _worker()
    in_org_1 = AsyncMock(return_value=[SimpleNamespace(id=TEAM_T)])
    in_org_2 = AsyncMock(return_value=[])
    with patch.object(tenant_groups, "_cache", worker):
        with patch(_GET_USER_TEAMS, in_org_1):
            first = await tenant_groups.tenant_group_ids(_tenant(ORG_1), MagicMock())
        with patch(_GET_USER_TEAMS, in_org_2):
            second = await tenant_groups.tenant_group_ids(_tenant(ORG_2), MagicMock())
    assert first == [str(TEAM_T)] and second == []
    assert in_org_2.await_count == 1


@pytest.mark.asyncio
async def test_an_evicted_epoch_never_revalidates_an_entry_cached_before_the_eviction(redis_db):
    """allkeys-lru can drop the epoch key; a counter would restart and match an old entry again (#19630)."""
    memberships = {USER_U: [TEAM_T]}
    worker = _worker()
    seen = []
    await _groups_as(worker, memberships)
    seen.append(redis_db.epoch(ORG_1))
    await membership_epoch.bump_membership_epoch(ORG_1)
    seen.append(redis_db.epoch(ORG_1))
    await _groups_as(worker, memberships)  # cached under the bumped token
    memberships[USER_U] = []  # the revocation
    redis_db.evict(membership_epoch.membership_epoch_key(ORG_1))

    assert await _groups_as(worker, memberships) == [], "the pre-eviction entry must not be served"
    seen.append(redis_db.epoch(ORG_1))
    assert seen[-1] is not None and seen[-1] not in seen[:-1]


@pytest.mark.asyncio
async def test_a_bump_after_an_eviction_does_not_reproduce_an_earlier_value(redis_db):
    key = membership_epoch.membership_epoch_key(ORG_1)
    earlier = {await membership_epoch.bump_membership_epoch(ORG_1)}
    for _ in range(3):
        redis_db.evict(key)
        earlier.add(await membership_epoch.read_membership_epoch(ORG_1))  # re-minted on read
        redis_db.evict(key)
        bumped = await membership_epoch.bump_membership_epoch(ORG_1)
        assert bumped not in earlier and bumped != "0"
        earlier.add(bumped)
    assert len(earlier) == 7


@pytest.mark.asyncio
async def test_a_missing_epoch_is_minted_once_and_never_reads_as_zero(redis_db):
    first = await membership_epoch.read_membership_epoch(ORG_1)
    assert first not in (None, "0") and await membership_epoch.read_membership_epoch(ORG_1) == first
