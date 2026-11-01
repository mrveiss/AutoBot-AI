# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A hard user or organisation delete reaches every worker's cached team memberships (#19670).

The membership rows go with a database-level cascade, never through ``TeamService``, so the
delete services queue the per-organisation membership-epoch bump themselves, after the commit.
The cache, epoch store and read are the real ones (``tenant_group_ids``); only the Redis client and
the SQL are faked, and the "table" the team lookup reads is changed by the delete itself.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cachetools import TTLCache

from autobot_shared import membership_epoch
from autobot_shared.db_session import POST_COMMIT_CALLBACKS, PostCommitCallbackError, _run_post_commit_callbacks
from autobot_shared.user_management.base_service import TenantContext
from autobot_shared.user_management.organization_service import OrganizationService
from autobot_shared.user_management.user_service import UserService
from knowledge import tenant_groups

TEAM_T = uuid.UUID("77777777-7777-7777-7777-777777777777")
USER_U = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ORG_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
ORG_2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
_GET_USER_TEAMS = "autobot_shared.user_management.team_service.TeamService.get_user_teams"


class _FakeRedis:
    def __init__(self) -> None:
        self.tokens: dict[str, str] = {}
        self.fail_set = 0

    async def set(self, key, value, nx=False):
        if self.fail_set:
            self.fail_set -= 1
            raise ConnectionError("redis down")
        if nx and key in self.tokens:
            return None
        self.tokens[key] = value
        return True

    async def get(self, key):
        return self.tokens[key].encode() if key in self.tokens else None


class _UserSvc(UserService):
    user_model = MagicMock()


class _OrgSvc(OrganizationService):
    organization_model = MagicMock()
    user_model = MagicMock()


@pytest.fixture
def redis_db():
    db = _FakeRedis()
    with (
        patch.object(membership_epoch, "get_async_redis_client", AsyncMock(return_value=db)),
        patch.object(membership_epoch, "MEMBERSHIP_EPOCH_BUMP_BACKOFF_SECONDS", 0.0),
    ):
        yield db


def _session(table: dict, team_orgs=(ORG_1,)) -> MagicMock:
    """A session whose ``delete`` empties *table* (the cascade) and whose team-org query yields *team_orgs*."""
    session = MagicMock()
    session.info = {POST_COMMIT_CALLBACKS: []}
    session.flush = AsyncMock()
    session.delete = AsyncMock(side_effect=lambda _row: table.clear())
    session.execute = AsyncMock(return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: list(team_orgs))))
    return session


async def _read(worker: TTLCache, table: dict) -> list[str]:
    """The removed user's KB group read on *worker*, over the live *table*."""
    teams = AsyncMock(side_effect=lambda uid: [SimpleNamespace(id=t) for t in table.get("teams", [])])
    tenant = TenantContext(org_id=ORG_1, user_id=USER_U)
    with patch.object(tenant_groups, "_cache", worker), patch(_GET_USER_TEAMS, teams):
        return await tenant_groups.tenant_group_ids(tenant, MagicMock())


def _user_service(session) -> _UserSvc:
    svc = _UserSvc(session, TenantContext(org_id=ORG_1))
    svc.get_user = AsyncMock(return_value=SimpleNamespace(id=USER_U, org_id=ORG_1))
    svc._audit_log = AsyncMock()
    return svc


def _org_service(session) -> _OrgSvc:
    svc = _OrgSvc(session, TenantContext(org_id=ORG_1, is_platform_admin=True))
    svc.get_organization = AsyncMock(return_value=SimpleNamespace(id=ORG_1, name="O"))
    svc._audit_log = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_a_hard_deleted_user_loses_the_team_on_every_worker(redis_db):
    table = {"teams": [TEAM_T]}
    workers = [TTLCache(maxsize=16, ttl=3600), TTLCache(maxsize=16, ttl=3600)]
    for worker in workers:
        assert await _read(worker, table) == [str(TEAM_T)]
    session = _session(table)
    await _user_service(session).delete_user(USER_U, hard_delete=True)
    await _run_post_commit_callbacks(session)
    for worker in workers:
        assert await _read(worker, table) == []


@pytest.mark.asyncio
async def test_control_without_the_bump_the_cache_serves_the_deleted_user(redis_db):
    table = {"teams": [TEAM_T]}
    worker = TTLCache(maxsize=16, ttl=3600)
    await _read(worker, table)
    session = _session(table)
    await _user_service(session).delete_user(USER_U, hard_delete=True)  # committed, callbacks not run
    assert await _read(worker, table) == [str(TEAM_T)]


@pytest.mark.asyncio
async def test_the_user_delete_bumps_after_the_commit_for_each_organisation_it_held_a_team_in(redis_db):
    session = _session({}, team_orgs=(ORG_2,))
    await _user_service(session).delete_user(USER_U, hard_delete=True)
    assert redis_db.tokens == {}
    await _run_post_commit_callbacks(session)
    assert set(redis_db.tokens) == {membership_epoch.membership_epoch_key(o) for o in (ORG_1, ORG_2)}


@pytest.mark.asyncio
async def test_the_organisations_are_read_before_the_cascade_removes_the_rows(redis_db):
    order: list[str] = []
    session = _session({})
    session.execute = AsyncMock(
        side_effect=lambda *_: order.append("read") or MagicMock(scalars=lambda: MagicMock(all=lambda: []))
    )
    session.delete = AsyncMock(side_effect=lambda _row: order.append("delete"))
    await _user_service(session).delete_user(USER_U, hard_delete=True)
    assert order == ["read", "delete"]


@pytest.mark.asyncio
async def test_a_failed_bump_after_the_user_delete_is_raised_not_swallowed(redis_db):
    session = _session({})
    await _user_service(session).delete_user(USER_U, hard_delete=True)
    redis_db.fail_set = 99
    with pytest.raises(PostCommitCallbackError):
        await _run_post_commit_callbacks(session)


@pytest.mark.asyncio
async def test_a_hard_deleted_organisation_drops_its_cached_teams_on_every_worker(redis_db):
    table = {"teams": [TEAM_T]}
    workers = [TTLCache(maxsize=16, ttl=3600), TTLCache(maxsize=16, ttl=3600)]
    for worker in workers:
        await _read(worker, table)
    session = _session(table)
    await _org_service(session).delete_organization(ORG_1, hard_delete=True)
    await _run_post_commit_callbacks(session)
    for worker in workers:
        assert await _read(worker, table) == []
    assert set(redis_db.tokens) == {membership_epoch.membership_epoch_key(ORG_1)}
