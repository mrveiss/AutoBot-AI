# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The superadmin reads every knowledge fact through one audited bypass (#19860)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.scoping import Principal, ResourceDescriptor, ScopeLevel, is_visible
from autobot_shared.user_management.base_service import TenantContext
from knowledge.ownership import KnowledgeOwnership
from knowledge.root_read import is_superadmin_role
from knowledge.search_filters import (
    filter_for_caller,
    filter_for_principal,
    filter_for_user_id,
    kb_principal,
    kb_principal_from_tenant,
    principal_for_identity,
    scoped_reader,
)
from services.rag_visibility import scope_key

AUDIT = "services.audit_logger.audit_log"
PRIVATE_OF_B = {"id": "f-b", "metadata": {"owner_id": "B", "visibility": "private"}}
TEAM_OF_B = {"id": "f-t", "metadata": {"owner_id": "B", "visibility": "group", "group_ids": ["team-x"]}}
OWN = {"id": "f-a", "metadata": {"owner_id": "A", "visibility": "private"}}
ALL_FACTS = [PRIVATE_OF_B, TEAM_OF_B, OWN]

SUPERADMIN = {"user_id": "A", "role": "superadmin", "auth_method": "jwt"}
ADMIN = {"user_id": "A", "role": "admin", "auth_method": "jwt"}
USER = {"user_id": "A", "role": "user", "auth_method": "jwt"}
STORE = "services.audit.store.insert_event"


def _kb():
    return SimpleNamespace(ownership_manager=KnowledgeOwnership(MagicMock()))


def _ids(results):
    return [r["id"] for r in results]


@pytest.mark.asyncio
@pytest.mark.parametrize("org", [None, "org-1"])
async def test_a_superadmin_reads_another_users_private_and_team_fact_with_or_without_an_org(org):
    principal = kb_principal({**SUPERADMIN, "org_id": org})
    with patch(AUDIT, new=AsyncMock(return_value=True)):
        kept = await filter_for_principal(ALL_FACTS, principal, _kb().ownership_manager)
    assert _ids(kept) == ["f-b", "f-t", "f-a"]


@pytest.mark.asyncio
@pytest.mark.parametrize("claims", [ADMIN, USER, {**ADMIN, "org_id": "org-1", "is_org_admin": True}])
async def test_an_admin_an_org_admin_and_a_user_still_cannot_read_anothers_private_fact(claims):
    audit = AsyncMock(return_value=True)
    with patch(AUDIT, new=audit):
        kept = await filter_for_principal(ALL_FACTS, kb_principal(claims), _kb().ownership_manager)
    assert _ids(kept) == ["f-a"]
    audit.assert_not_awaited()


@pytest.mark.parametrize(
    "claims",
    [
        {**USER, "is_superadmin": True},
        {**USER, "superadmin": True, "metadata": {"role": "superadmin"}},
        {**ADMIN, "is_platform_admin": True, "context": {"role": "superadmin"}},
        # the development header (debug only) and the auth-disabled / service / run-token / bare-dict identities
        {"username": "dev_superadmin", "role": "superadmin", "auth_method": "development"},
        {**SUPERADMIN, "auth_disabled": True},
        {**SUPERADMIN, "service": True},
        {**SUPERADMIN, "auth_method": "run_jwt"},
        {"user_id": "A", "role": "superadmin"},
    ],
)
def test_a_claim_of_superadmin_in_the_context_or_body_gets_nothing_extra(claims):
    assert kb_principal(claims).is_superadmin is False


def test_session_identity_and_a_platform_admin_tenant_flag_are_not_superadmin():
    assert principal_for_identity("A", "org-1").is_superadmin is False
    assert not is_superadmin_role("admin") and not is_superadmin_role(None)
    assert is_superadmin_role("SuperAdmin")


@pytest.mark.asyncio
async def test_the_tenant_path_takes_superadmin_only_from_the_verified_argument_not_the_platform_flag():
    tenant = TenantContext(org_id=uuid.uuid4(), user_id=uuid.uuid4(), is_platform_admin=True)
    with patch("knowledge.tenant_groups.tenant_group_ids", new=AsyncMock(return_value=[])):
        assert (await kb_principal_from_tenant(tenant, MagicMock())).is_superadmin is False
        assert (await kb_principal_from_tenant(tenant, MagicMock(), is_superadmin=True)).is_superadmin is True


@pytest.mark.asyncio
@pytest.mark.parametrize("role,expected", [("superadmin", True), ("admin", False), ("user", False)])
async def test_the_graph_rag_route_derives_the_flag_from_the_authenticated_users_role(role, expected):
    from api.graph_rag import graph_rag_search

    seen = {}

    async def fake_principal(tenant, session, *, is_superadmin=False):
        seen["flag"] = is_superadmin
        return Principal("A", None, frozenset(), True, is_superadmin)

    service = MagicMock()
    service.graph_aware_search = AsyncMock(return_value=([], MagicMock(total_time=0.0, to_response_dict=dict)))
    request = SimpleNamespace(
        query="q", start_entity=None, max_depth=1, max_results=5, enable_reranking=False, timeout=None
    )
    with patch("api.graph_rag.kb_principal_from_tenant", new=fake_principal):
        await graph_rag_search(
            search_request=request,
            service=service,
            tenant=TenantContext(org_id=uuid.uuid4(), user_id=uuid.uuid4(), is_platform_admin=True),
            session=MagicMock(),
            current_user={"role": role, "auth_method": "jwt"},
        )
    assert seen["flag"] is expected


@pytest.mark.asyncio
async def test_a_bypassing_read_writes_an_audit_record_naming_only_the_bypassed_facts():
    audit = AsyncMock(return_value=True)
    with patch(AUDIT, new=audit):
        await filter_for_principal(ALL_FACTS, kb_principal(SUPERADMIN), _kb().ownership_manager)
    audit.assert_awaited_once()
    assert audit.await_args.args[0] == "kb.admin_read"
    assert audit.await_args.kwargs["user_id"] == "A"
    details = audit.await_args.kwargs["details"]
    assert details["fact_ids"] == ["f-b", "f-t"] and details["bypass"] == "superadmin" and details["count"] == 2


@pytest.mark.asyncio
async def test_a_read_that_needed_no_bypass_writes_no_audit_record():
    audit = AsyncMock(return_value=True)
    with patch(AUDIT, new=audit):
        kept = await filter_for_principal([OWN], kb_principal(SUPERADMIN), _kb().ownership_manager)
    assert _ids(kept) == ["f-a"]
    audit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [{"side_effect": RuntimeError("down")}, {"return_value": False}])
async def test_when_the_audit_cannot_be_written_the_bypassed_facts_are_withheld(failure):
    with patch(AUDIT, new=AsyncMock(**failure)):
        kept = await filter_for_principal(ALL_FACTS, kb_principal(SUPERADMIN), _kb().ownership_manager)
    assert _ids(kept) == ["f-a"]


@pytest.mark.asyncio
async def test_the_scoped_reader_and_the_user_id_path_carry_the_bypass_but_a_bare_id_does_not():
    kb = _kb()
    with patch(AUDIT, new=AsyncMock(return_value=True)):
        assert _ids(await filter_for_user_id(ALL_FACTS, kb, scoped_reader(SUPERADMIN))) == ["f-b", "f-t", "f-a"]
        assert _ids(await filter_for_user_id(ALL_FACTS, kb, scoped_reader(ADMIN))) == ["f-a"]
    assert _ids(await filter_for_user_id(ALL_FACTS, kb, "A")) == ["f-a"]


@pytest.mark.asyncio
async def test_the_explicit_read_api_still_reads_everything_for_admin_and_superadmin_audited():
    kb = _kb()
    with patch(AUDIT, new=AsyncMock(return_value=True)) as audit:
        assert _ids(await filter_for_caller(ALL_FACTS, kb, ADMIN)) == ["f-b", "f-t", "f-a"]
        assert _ids(await filter_for_caller(ALL_FACTS, kb, SUPERADMIN)) == ["f-b", "f-t", "f-a"]
    assert audit.await_count == 2
    assert _ids(await filter_for_caller(ALL_FACTS, kb, USER)) == ["f-a"]


def test_the_rag_cache_partition_of_a_root_read_is_never_shared_with_a_scoped_read():
    scoped = Principal("A", None, frozenset(), True)
    root = Principal("A", None, frozenset(), True, True)
    assert scope_key(scoped, "e1") != scope_key(root, "e1")
    assert scope_key(scoped, "e1") == scope_key(Principal("A", None, frozenset(), True), "e1")


def test_the_shared_visibility_rule_ignores_the_flag_so_no_other_subsystem_widens():
    resource = ResourceDescriptor(owner_id="B", company_id=None, scope=ScopeLevel.USER)
    assert is_visible(Principal("A", None, frozenset(), True, True), resource, False) is False


def test_the_development_header_and_auth_disabled_identities_are_not_superadmin():
    # The exact dicts auth_middleware builds: `_extract_user_from_dev_header` (X-User-Role, development.debug only;
    # no user_id, so the id falls back to the username) and `_get_auth_disabled_user` (the stub in conftest hides
    # the real class here, so the shapes are written out).
    dev_user = {"username": "dev_superadmin", "role": "superadmin", "email": "x@y", "auth_method": "development"}
    disabled = {"user_id": "admin", "username": "admin", "role": "superadmin", "auth_disabled": True}
    for identity in (dev_user, disabled):
        assert kb_principal(identity).is_superadmin is False
    assert kb_principal(dev_user).user_id == "dev_superadmin"


def test_an_orm_user_object_is_judged_by_its_role():
    orm = SimpleNamespace(id=1, org_id=None, team_memberships=[], role="superadmin")
    assert kb_principal(orm).is_superadmin is True
    assert kb_principal(SimpleNamespace(id=1, org_id=None, team_memberships=[], role="admin")).is_superadmin is False


class _NoStore:
    """A real audit write path whose store refuses (or accepts) the row; nothing in ``audit_log`` is patched."""

    def __init__(self, store):
        self.store = store

    def __enter__(self):
        self._p = [
            patch(STORE, new=self.store),
            patch("services.audit.audit._analyse_for_threats", new=AsyncMock()),
            patch("services.audit.audit._project", new=AsyncMock()),
        ]
        for p in self._p:
            p.start()
        return self.store

    def __exit__(self, *exc):
        for p in self._p:
            p.stop()


@pytest.mark.asyncio
async def test_a_failing_audit_store_withholds_the_bypassed_facts_of_a_superadmin():
    with _NoStore(AsyncMock(side_effect=RuntimeError("db down"))):
        kept = await filter_for_principal(ALL_FACTS, kb_principal(SUPERADMIN), _kb().ownership_manager)
    assert _ids(kept) == ["f-a"]


@pytest.mark.asyncio
async def test_a_committed_audit_row_is_awaited_before_the_bypassed_facts_are_returned():
    with _NoStore(AsyncMock()) as store:
        kept = await filter_for_principal(ALL_FACTS, kb_principal(SUPERADMIN), _kb().ownership_manager)
    assert _ids(kept) == ["f-b", "f-t", "f-a"]
    store.assert_awaited_once()
    assert store.await_args.args[0].action == "kb.admin_read"


@pytest.mark.asyncio
async def test_a_failing_audit_store_withholds_a_plain_admins_explicit_read_too():
    with _NoStore(AsyncMock(side_effect=RuntimeError("db down"))):
        assert await filter_for_caller(ALL_FACTS, _kb(), ADMIN) == []
    with _NoStore(AsyncMock()):
        assert _ids(await filter_for_caller(ALL_FACTS, _kb(), ADMIN)) == ["f-b", "f-t", "f-a"]


@pytest.mark.asyncio
async def test_a_superadmin_with_no_ownership_manager_reads_nothing_extra_and_it_is_logged(caplog):
    with caplog.at_level("WARNING"):
        kept = await filter_for_principal(ALL_FACTS, kb_principal(SUPERADMIN), None)
    assert kept == [] and "without an ownership manager" in caplog.text


@pytest.mark.asyncio
async def test_a_withheld_root_read_is_logged_with_the_user_and_the_count(caplog):
    with _NoStore(AsyncMock(side_effect=RuntimeError("db down"))), caplog.at_level("ERROR"):
        await filter_for_principal(ALL_FACTS, kb_principal(SUPERADMIN), _kb().ownership_manager)
    assert "root read WITHHELD" in caplog.text and "2 bypassed" in caplog.text
