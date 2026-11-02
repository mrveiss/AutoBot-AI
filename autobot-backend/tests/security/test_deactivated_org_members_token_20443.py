# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Deactivating or deleting an organisation voids its members' earlier tokens (#20443, organisations).

A real signed login token goes through the real ``get_current_user`` and the shared epoch check; the
organisation is deactivated or deleted through the REAL backend ``OrganizationService``. The fake session
answers the service's two queries from a small table of users in two organisations, reading the
``org_id`` the statement was compiled with, so a query that did not filter by the organisation would
mark the other organisation's member and fail the test. Only storage is stood in for.
"""

import uuid
from types import SimpleNamespace

import pytest

from autobot_shared.db_session import POST_COMMIT_CALLBACKS, PostCommitCallbackError, async_session_scope
from autobot_shared.user_management import password_epoch
from autobot_shared.user_management.base_service import TenantContext
from testkit.fake_async_session import FakeAsyncSession, FakeResult
from tests.security._revocation_harness import assert_refused, token_request
from user_management.services.organization_service import OrganizationService

ORG = uuid.uuid4()
OTHER_ORG = uuid.uuid4()
#: username -> organisation; "frozen" is soft-deleted and inactive, "visitor" is in OTHER_ORG with a team here.
USERS = {"alice": ORG, "bob": ORG, "frozen": ORG, "carol": OTHER_ORG, "visitor": OTHER_ORG}


def _table(org):
    """Answer the two statements the service issues: the organisation row, then its members' names."""

    def answer(stmt):
        text = " ".join(str(stmt).split())
        if "FROM organizations" in text:
            return FakeResult([org])
        wanted = [v for v in stmt.compile().params.values() if isinstance(v, uuid.UUID)]
        assert text.startswith("SELECT users.username FROM users"), text
        return FakeResult([name for name, org_id in USERS.items() if org_id in wanted])

    return answer


def _org():
    return SimpleNamespace(id=ORG, name="Acme", is_active=True, deleted_at=None, updated_at=None)


def _service(org=None, **session_kwargs):
    session = FakeAsyncSession(default_result=_table(org or _org()), **session_kwargs)
    session.info = {POST_COMMIT_CALLBACKS: []}
    return OrganizationService(session, TenantContext(is_platform_admin=True))


async def _run_scoped(act, **session_kwargs):
    """Run *act(service)* inside the real session scope: commit, then the queued callbacks."""
    org = _org()
    session = FakeAsyncSession(default_result=_table(org), **session_kwargs)
    session.info = {}
    async with async_session_scope(lambda: session) as scoped:
        await act(OrganizationService(scoped, TenantContext(is_platform_admin=True)))
    return org


@pytest.mark.asyncio
async def test_the_control_a_members_token_is_admitted_while_the_organisation_is_live(get_current_user, epochs):
    assert (await get_current_user(token_request(username="alice")))["username"] == "alice"


@pytest.mark.asyncio
@pytest.mark.parametrize("how", ["deactivate", "soft_delete", "hard_delete"])
async def test_a_members_token_is_refused_and_another_organisations_member_is_untouched(get_current_user, epochs, how):
    alice, bob, carol, visitor = (token_request(username=n) for n in ("alice", "bob", "carol", "visitor"))
    acts = {
        "deactivate": lambda svc: svc.deactivate_organization(ORG),
        "soft_delete": lambda svc: svc.delete_organization(ORG, hard_delete=False),
        "hard_delete": lambda svc: svc.delete_organization(ORG, hard_delete=True),
    }
    await _run_scoped(acts[how])

    await assert_refused(get_current_user, alice)
    await assert_refused(get_current_user, bob)
    assert (await get_current_user(carol))["username"] == "carol"
    assert (await get_current_user(visitor))["username"] == "visitor", "a team here does not make it a member"


@pytest.mark.asyncio
async def test_every_member_is_marked_once_even_when_inactive_or_deleted_and_nothing_before_the_commit(epochs):
    service = _service()
    await service.deactivate_organization(ORG)
    assert epochs == {}, "nothing is written before the commit"

    await _run_scoped(lambda svc: svc.deactivate_organization(ORG))
    assert set(epochs) == {"alice", "bob", "frozen"}


@pytest.mark.asyncio
async def test_the_audit_row_says_how_many_were_queued_not_that_they_are_done(epochs):
    service = _service()
    await service.deactivate_organization(ORG)

    details = service.session.added[-1].details
    assert details == {"action": "deactivated", "sessions_revocation": "queued_after_commit", "members_queued": 3}
    assert epochs == {}


@pytest.mark.asyncio
async def test_an_organisation_with_no_members_queues_nothing(epochs):
    empty = uuid.uuid4()
    service = _service(SimpleNamespace(id=empty, name="E", is_active=True, deleted_at=None, updated_at=None))
    await service.deactivate_organization(empty)

    assert service.session.info == {POST_COMMIT_CALLBACKS: []}


@pytest.mark.asyncio
async def test_one_members_failing_write_still_marks_the_others_and_the_deactivation_stands(monkeypatch):
    monkeypatch.setattr(password_epoch, "MEMBERSHIP_EPOCH_BUMP_BACKOFF_SECONDS", 0.0)
    store, tries = {}, []

    async def set_epoch(subject, *, now=None):
        tries.append(subject)
        if subject == "bob":
            raise ConnectionError("store down")
        store[subject] = now
        return now

    password_epoch.use_epoch_store(get_epoch=lambda _s: None, set_epoch=set_epoch)
    try:
        with pytest.raises(PostCommitCallbackError) as failed:
            await _run_scoped(lambda svc: svc.deactivate_organization(ORG))
    finally:
        password_epoch.reset_epoch_store()

    assert set(store) == {"alice", "frozen"}
    assert tries.count("bob") == password_epoch.MEMBERSHIP_EPOCH_BUMP_ATTEMPTS, "the retry belongs to the member"
    message = str(failed.value.errors[0])
    assert "1 of 3 members" in message and "bob" not in message and "alice" not in message
    assert len(failed.value.errors) == 1, "one error for the whole organisation"


@pytest.mark.asyncio
async def test_the_organisation_is_still_deactivated_when_a_marker_write_fails(monkeypatch):
    monkeypatch.setattr(password_epoch, "MEMBERSHIP_EPOCH_BUMP_BACKOFF_SECONDS", 0.0)
    org = _org()
    session = FakeAsyncSession(default_result=_table(org))
    session.info = {}
    password_epoch.use_epoch_store(get_epoch=lambda _s: None, set_epoch=lambda *_a, **_k: _none())
    try:
        with pytest.raises(PostCommitCallbackError):
            async with async_session_scope(lambda: session) as scoped:
                await OrganizationService(scoped, TenantContext(is_platform_admin=True)).deactivate_organization(ORG)
    finally:
        password_epoch.reset_epoch_store()

    assert org.is_active is False and session.commits == 1 and session.rollbacks == 0


async def _none():
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize("how", ["deactivate", "soft_delete"])
async def test_a_failed_commit_writes_no_markers(epochs, how):
    act = {
        "deactivate": lambda svc: svc.deactivate_organization(ORG),
        "soft_delete": lambda svc: svc.delete_organization(ORG),
    }[how]
    with pytest.raises(RuntimeError):
        await _run_scoped(act, commit_error=RuntimeError("deferred constraint"))

    assert epochs == {}


@pytest.mark.asyncio
async def test_reactivating_writes_nothing_and_the_old_token_stays_void(get_current_user, epochs):
    old = token_request(age_seconds=60, username="alice")
    org = await _run_scoped(lambda svc: svc.deactivate_organization(ORG))
    marked = dict(epochs)
    org.is_active = True  # no service method reactivates an organisation; the flag alone is flipped

    assert epochs == marked
    await assert_refused(get_current_user, old)
    assert (await get_current_user(token_request(age_seconds=-5, username="alice")))["username"] == "alice"


@pytest.mark.asyncio
async def test_members_are_marked_in_batches_of_the_concurrency_bound(monkeypatch):
    monkeypatch.setattr(password_epoch, "MEMBER_EPOCH_WRITE_CONCURRENCY", 2)
    live = peak = 0
    import asyncio  # noqa: PLC0415

    async def set_epoch(subject, *, now=None):
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0)
        live -= 1
        return now

    password_epoch.use_epoch_store(get_epoch=lambda _s: None, set_epoch=set_epoch)
    try:
        recorded = await password_epoch.MembersPasswordEpochMark(tuple(f"m{i}" for i in range(7)))()
    finally:
        password_epoch.reset_epoch_store()

    assert recorded == 7 and peak == 2
