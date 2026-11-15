# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Batch jobs, templates and schedules are owner-scoped (#21650).

Before this change every ``/api/batch-jobs`` route checked only that the caller was
signed in, so any user could list, read, run, read the logs of and delete every other
user's job, template and schedule. Each test below takes one route and asserts the three
callers that matter: the owner may, another user gets the same 404 as a missing record,
and an administrator may. Records created before #21650 have no owner and stay
administrators-only; nothing assigns them one.

Uses the same stub-then-real-load setup as ``batch_jobs_schedules_test.py``.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import api.batch_jobs as _bj  # noqa: E402
from api.batch_jobs_run_route_test import _seed_job  # noqa: E402
from api.batch_jobs_schedules_test import _FakeRedis  # noqa: F401  (sets up the stubs first)
from api.schemas_workflows import BatchJobCreate, BatchJobType  # noqa: E402
from services import batch_job_ownership as ownership  # noqa: E402

ALICE = {"user_id": "alice", "role": "user"}
BOB = {"user_id": "bob", "role": "user"}
ADMIN = {"user_id": "root", "role": "admin"}
SERVICE = {"role": "service"}  # an internal service principal: authenticated, no user identity
PAGE = SimpleNamespace(offset=0, limit=50)


@pytest.fixture
def redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(_bj, "get_redis_client", lambda database: fake)
    return fake


async def _expect_404(call):
    with pytest.raises(HTTPException) as exc_info:
        await call
    assert exc_info.value.status_code == 404
    return exc_info.value


async def _list_job_ids(user):
    listing = await _bj.list_batch_jobs(status=None, job_type=None, pagination=PAGE, current_user=user)
    return sorted(job.job_id for job in listing.jobs)


# --- the rule itself ------------------------------------------------------------------


def test_owner_and_admin_may_access_and_another_user_may_not():
    assert ownership.may_access("alice", ALICE)
    assert ownership.may_access("alice", ADMIN)
    assert not ownership.may_access("alice", BOB)


def test_an_ownerless_record_is_for_administrators_only():
    assert ownership.may_access(None, ADMIN)
    assert not ownership.may_access(None, ALICE)
    assert not ownership.may_access(None, SERVICE)


def test_a_caller_with_no_user_identity_records_no_owner(redis):
    ownership.create_record(redis, ownership.JOBS, "job-1", "batch:job:job-1", "{}", SERVICE)
    assert ownership.owner_of(redis, ownership.JOBS, "job-1") is None
    assert redis.exists("batch:job:job-1")
    assert "job-1" in redis.smembers("batch:jobs:all")


# --- jobs -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_records_the_caller_as_owner(redis):
    job = await _bj.create_batch_job(BatchJobCreate(name="n", job_type=BatchJobType.custom), current_user=ALICE)
    assert ownership.owner_of(redis, ownership.JOBS, job.job_id) == "alice"


@pytest.mark.asyncio
async def test_list_shows_the_callers_own_jobs_and_admin_sees_all(redis):
    _seed_job(redis, "a-1", owner="alice")
    _seed_job(redis, "b-1", owner="bob")
    _seed_job(redis, "legacy", owner=None)
    assert await _list_job_ids(ALICE) == ["a-1"]
    assert await _list_job_ids(BOB) == ["b-1"]
    assert await _list_job_ids(ADMIN) == ["a-1", "b-1", "legacy"]


@pytest.mark.asyncio
async def test_get_job_owner_and_admin_yes_other_user_404(redis):
    _seed_job(redis, "a-1", owner="alice")
    assert (await _bj.get_batch_job("a-1", current_user=ALICE)).job_id == "a-1"
    assert (await _bj.get_batch_job("a-1", current_user=ADMIN)).job_id == "a-1"
    refused = await _expect_404(_bj.get_batch_job("a-1", current_user=BOB))
    missing = await _expect_404(_bj.get_batch_job("nope", current_user=BOB))
    assert refused.detail == "Job a-1 not found" and missing.detail == "Job nope not found"


@pytest.mark.asyncio
async def test_an_ownerless_job_is_404_for_a_user_and_readable_by_admin(redis):
    _seed_job(redis, "legacy", owner=None)
    await _expect_404(_bj.get_batch_job("legacy", current_user=ALICE))
    assert (await _bj.get_batch_job("legacy", current_user=ADMIN)).job_id == "legacy"


@pytest.mark.asyncio
async def test_run_job_other_user_404(redis, monkeypatch):
    import tasks.batch_job_tasks as bjt

    queued = []
    monkeypatch.setattr(bjt.run_batch_job, "delay", queued.append)
    _seed_job(redis, "a-1", owner="alice")
    await _expect_404(_bj.run_batch_job_now("a-1", current_user=BOB))
    await _bj.run_batch_job_now("a-1", current_user=ALICE)
    await _bj.run_batch_job_now("a-1", current_user=ADMIN)
    assert queued == ["a-1", "a-1"]


@pytest.mark.asyncio
async def test_job_logs_other_user_404(redis):
    _seed_job(redis, "a-1", owner="alice")
    await _expect_404(_bj.get_job_logs("a-1", current_user=BOB))
    assert await _bj.get_job_logs("a-1", current_user=ALICE) == []
    assert await _bj.get_job_logs("a-1", current_user=ADMIN) == []


@pytest.mark.asyncio
async def test_delete_job_other_user_404_and_the_job_stays(redis):
    _seed_job(redis, "a-1", owner="alice")
    await _expect_404(_bj.delete_batch_job("a-1", current_user=BOB))
    assert redis.exists(_bj._get_job_key("a-1"))
    await _bj.delete_batch_job("a-1", current_user=ALICE)
    assert not redis.exists(_bj._get_job_key("a-1"))
    assert ownership.owner_of(redis, ownership.JOBS, "a-1") is None


@pytest.mark.asyncio
async def test_admin_may_delete_another_users_job(redis):
    _seed_job(redis, "a-1", owner="alice")
    await _bj.delete_batch_job("a-1", current_user=ADMIN)
    assert not redis.exists(_bj._get_job_key("a-1"))


# --- templates ------------------------------------------------------------------------


async def _alice_template():
    return await _bj.create_batch_template(name="t", job_type=BatchJobType.custom, parameters={}, current_user=ALICE)


@pytest.mark.asyncio
async def test_template_list_and_get_are_owner_scoped(redis):
    template = await _alice_template()
    assert [t.template_id for t in await _bj.list_batch_templates(current_user=ALICE)] == [template.template_id]
    assert await _bj.list_batch_templates(current_user=BOB) == []
    assert len(await _bj.list_batch_templates(current_user=ADMIN)) == 1
    await _expect_404(_bj.get_batch_template(template.template_id, current_user=BOB))
    assert (await _bj.get_batch_template(template.template_id, current_user=ADMIN)).name == "t"


@pytest.mark.asyncio
async def test_template_delete_other_user_404_owner_yes(redis):
    template = await _alice_template()
    await _expect_404(_bj.delete_batch_template(template.template_id, current_user=BOB))
    await _bj.delete_batch_template(template.template_id, current_user=ALICE)
    assert ownership.owner_of(redis, ownership.TEMPLATES, template.template_id) is None


# --- schedules ------------------------------------------------------------------------


async def _alice_schedule(redis):
    _seed_job(redis, "a-1", owner="alice")
    return await _bj.create_batch_schedule(job_id="a-1", cron_expression="0 0 1 1 *", current_user=ALICE)


@pytest.mark.asyncio
async def test_a_user_cannot_schedule_another_users_job(redis):
    _seed_job(redis, "a-1", owner="alice")
    await _expect_404(_bj.create_batch_schedule(job_id="a-1", cron_expression="0 0 1 1 *", current_user=BOB))


@pytest.mark.asyncio
async def test_schedule_list_patch_and_delete_are_owner_scoped(redis):
    from api.schemas_workflows import BatchScheduleUpdate

    schedule = await _alice_schedule(redis)
    sid = schedule.schedule_id
    assert [s.schedule_id for s in await _bj.list_batch_schedules(current_user=ALICE)] == [sid]
    assert await _bj.list_batch_schedules(current_user=BOB) == []
    await _expect_404(_bj.update_batch_schedule(sid, BatchScheduleUpdate(enabled=False), current_user=BOB))
    await _expect_404(_bj.delete_batch_schedule(sid, current_user=BOB))
    assert (
        await _bj.update_batch_schedule(sid, BatchScheduleUpdate(enabled=False), current_user=ADMIN)
    ).enabled is False
    await _bj.delete_batch_schedule(sid, current_user=ALICE)
    assert ownership.owner_of(redis, ownership.SCHEDULES, sid) is None


# --- admin, owner and count rows ---------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_may_delete_another_users_template(redis):
    template = await _alice_template()
    await _bj.delete_batch_template(template.template_id, current_user=ADMIN)
    assert ownership.owner_of(redis, ownership.TEMPLATES, template.template_id) is None
    assert not redis.exists(_bj._get_template_key(template.template_id))


@pytest.mark.asyncio
async def test_admin_may_schedule_and_delete_on_another_users_record(redis):
    _seed_job(redis, "a-1", owner="alice")
    schedule = await _bj.create_batch_schedule(job_id="a-1", cron_expression="0 0 1 1 *", current_user=ADMIN)
    assert ownership.owner_of(redis, ownership.SCHEDULES, schedule.schedule_id) == "root"
    alice_schedule = await _alice_schedule(redis)
    await _bj.delete_batch_schedule(alice_schedule.schedule_id, current_user=ADMIN)
    assert ownership.owner_of(redis, ownership.SCHEDULES, alice_schedule.schedule_id) is None


@pytest.mark.asyncio
async def test_schedule_owner_may_patch_their_schedule(redis):
    from api.schemas_workflows import BatchScheduleUpdate

    schedule = await _alice_schedule(redis)
    patch = BatchScheduleUpdate(enabled=False)
    updated = await _bj.update_batch_schedule(schedule.schedule_id, patch, current_user=ALICE)
    assert updated.enabled is False


@pytest.mark.asyncio
async def test_list_counts_exclude_another_users_records(redis):
    _seed_job(redis, "a-1", owner="alice")
    _seed_job(redis, "b-1", owner="bob")
    _seed_job(redis, "b-2", owner="bob")
    listing = await _bj.list_batch_jobs(status=None, job_type=None, pagination=PAGE, current_user=ALICE)
    assert listing.total_count == 1
    assert sum(listing.status_counts.values()) == 1
    admin_listing = await _bj.list_batch_jobs(status=None, job_type=None, pagination=PAGE, current_user=ADMIN)
    assert admin_listing.total_count == 3
    assert sum(admin_listing.status_counts.values()) == 3
