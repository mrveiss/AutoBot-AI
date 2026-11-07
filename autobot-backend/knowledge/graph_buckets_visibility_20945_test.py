# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who sees which knowledge-graph bucket record, and what an admin read records (#20945, #16665, #19860)."""

from unittest.mock import AsyncMock, patch

import pytest

from knowledge.graph_bucket_visibility import record_page
from knowledge.graph_buckets import build_bucket_sections
from knowledge.graph_buckets_fakes_20945 import ALICE, TENANT_A, TENANT_B, client_with, manager, viewer

BOB = "bob"
_MINE = {"user_id": ALICE, "tenant_id": TENANT_A}
_THEIRS = {"user_id": BOB, "tenant_id": TENANT_A}


async def _build(records, who, **kw):
    return await build_bucket_sections(await client_with(records), who, manager(), **kw)


def _ids(built, section):
    return sorted(
        n["id"].rsplit(":", 1)[1] for n in built["nodes"] if n.get("section") == section and n["type"] != "section"
    )


def _totals(built):
    return {s["key"]: (s["total"], s["returned"], s["limited"]) for s in built["sections"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("collection,section", [("trajectories", "research"), ("autobot_verbatim", "verbatim")])
async def test_a_non_admin_reads_only_their_own_records_in_per_user_buckets(collection, section):
    records = {collection: [("mine", _MINE), ("theirs", _THEIRS), ("nobody", {"k": "v"})]}
    built = await _build(records, viewer())
    assert _ids(built, section) == ["mine"]
    assert _totals(built)[section] == (1, 1, False), "the total never counts what the caller cannot read"
    assert "theirs" not in repr(built) and "nobody" not in repr(built)


@pytest.mark.asyncio
async def test_a_record_with_no_owner_is_hidden_from_non_admins_but_a_public_one_is_shown():
    records = {
        "autobot_memory": [("a", {}), ("b", {"owner_id": ALICE}), ("c", {"owner_id": BOB, "visibility": "system"})]
    }
    assert _ids(await _build(records, viewer()), "memory") == ["b", "c"]


@pytest.mark.asyncio
async def test_docs_and_code_are_public_by_design_and_shown_without_an_owner():
    records = {"autobot_docs": [("d1", {})], "autobot_code": [("c1", {})]}
    built = await _build(records, viewer())
    assert _ids(built, "docs") == ["d1"] and _ids(built, "code") == ["c1"]


@pytest.mark.asyncio
async def test_an_admin_read_of_buckets_is_recorded_in_the_admin_ledger():
    who = viewer(admin=True)
    records = {
        "trajectories": [("t1", _THEIRS), ("t2", _THEIRS)],
        "company:tenant-a": [("c1", {})],
        "autobot_docs": [("d1", {})],
    }
    built = await _build(records, who, limit=10)
    assert _ids(built, "research") == ["t1", "t2"]
    assert sorted(who.ledger.fact_ids) == [
        "bucket:company:tenant-a:c1",
        "bucket:trajectories:t1",
        "bucket:trajectories:t2",
    ], "public docs are not an admin-gated read; every other record the admin was shown is in the ledger"
    audit = AsyncMock(return_value=True)
    with patch("services.audit_logger.audit_log", new=audit):
        await who.ledger.commit(ALICE, "kb.multi_source_graph")
    assert audit.await_args.kwargs["details"]["count"] == 3


@pytest.mark.asyncio
async def test_the_ledger_records_only_the_returned_page_not_the_whole_scan():
    who = viewer(admin=True)
    await _build({"trajectories": [(f"t{i}", _THEIRS) for i in range(5)]}, who, limit=2, offset=1)
    assert who.ledger.fact_ids == ["bucket:trajectories:t1", "bucket:trajectories:t2"]


def test_record_page_skips_a_non_admin_viewer():
    who = viewer()
    record_page(who, "owner", [("trajectories", "t1", {})])
    assert who.ledger is False


@pytest.mark.asyncio
async def test_an_admin_of_one_tenant_sees_nothing_of_another_tenant():
    records = {
        "company:tenant-a": [("a1", {})],
        "company:tenant-b": [("b1", {})],
        "company:tenant-b:agents": [("b2", {})],
        "project:p-a": [("pa", {"company_id": TENANT_A})],
        "project:p-b": [("pb", {"company_id": TENANT_B})],
        "work_item:w-none": [("wn", {})],
        "trajectories": [
            ("ta", {"user_id": BOB, "tenant_id": TENANT_A}),
            ("tb", {"user_id": BOB, "tenant_id": TENANT_B}),
        ],
    }
    built = await _build(records, viewer("admin-a", TENANT_A, admin=True))
    seen = repr(built)
    for hidden in ("tenant-b", "p-b", "w-none", "'pb'", "'tb'", "b1", "b2"):
        assert hidden not in seen, f"tenant A's admin must not see {hidden}"
    assert _ids(built, "company") == ["a1"] and _ids(built, "project") == ["pa"] and _ids(built, "research") == ["ta"]


@pytest.mark.asyncio
async def test_a_superadmin_crosses_tenants_and_is_audited():
    who = viewer("root", TENANT_A, superadmin=True)
    built = await _build({"company:tenant-b": [("b1", {})], "project:p-b": [("pb", {"company_id": TENANT_B})]}, who)
    assert _totals(built) == {"company": (1, 1, False), "project": (1, 1, False)}
    assert sorted(who.ledger.fact_ids) == ["bucket:company:tenant-b:b1", "bucket:project:p-b:pb"]


@pytest.mark.asyncio
async def test_an_admin_without_a_tenant_sees_no_per_entity_bucket():
    built = await _build({"company:tenant-a": [("a1", {})]}, viewer("admin-x", None, admin=True))
    assert built["sections"] == []


@pytest.mark.asyncio
async def test_a_non_admin_never_reads_per_entity_buckets():
    built = await _build({"company:tenant-a": [("a1", {"owner_id": ALICE})]}, viewer())
    assert built["sections"] == [] and built["nodes"] == []


@pytest.mark.asyncio
async def test_no_ownership_manager_means_no_owner_scoped_records():
    built = await build_bucket_sections(
        await client_with({"autobot_memory": [("a", {"owner_id": ALICE})]}), viewer(), None
    )
    assert built["sections"] == []
