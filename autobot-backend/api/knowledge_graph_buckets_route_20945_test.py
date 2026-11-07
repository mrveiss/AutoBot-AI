# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""POST/GET /multi-source/graph: buckets filtered by the caller, admin reads audited, typed sections (#20945)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.knowledge_search_aggregator import get_multi_source_graph, get_multi_source_graph_simple
from api.schemas_knowledge import KnowledgeMultiSourceGraphResponse
from api.schemas_knowledge_graph import GraphRequest
from knowledge.graph_buckets_fakes_20945 import ALICE, TENANT_A, ListingKB, client_with, fact

_RECORDS = {
    "trajectories": [
        ("t-mine", {"user_id": ALICE, "tenant_id": TENANT_A}),
        ("t-bob", {"user_id": "bob", "tenant_id": TENANT_A}),
    ],
    "company:tenant-a": [("ca", {})],
    "company:tenant-b": [("cb", {})],
}


def _user(user_id, role="user", org=TENANT_A):
    return {"user_id": user_id, "role": role, "org_id": org, "auth_method": "jwt"}


async def _kb():
    return ListingKB([fact("f-mine", ALICE), fact("f-bob", "bob")], await client_with(_RECORDS))


async def _call(user, body, kb=None):
    kb = kb or await _kb()
    audit = AsyncMock(return_value=True)
    with (
        patch("api.knowledge_search_aggregator.get_or_create_knowledge_base", new=AsyncMock(return_value=kb)),
        patch("services.audit_logger.audit_log", new=audit),
    ):
        return await get_multi_source_graph(MagicMock(), body, user), audit


def _body(**kw):
    return GraphRequest(include_categories=False, include_relations=False, **kw)


@pytest.mark.asyncio
async def test_a_user_gets_their_own_records_and_visible_totals_only():
    result, audit = await _call(_user(ALICE), _body())
    sections = {s["key"]: s for s in result["stats"]["sections"]}
    assert (sections["facts"]["total"], sections["facts"]["returned"]) == (1, 1), "bob's fact is not even counted"
    assert (sections["research"]["total"], sections["research"]["returned"]) == (1, 1)
    assert "company" not in sections and "t-bob" not in repr(result) and "f-bob" not in repr(result)
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_admin_read_of_facts_and_buckets_is_audited_and_bound_to_their_tenant():
    result, audit = await _call(_user("adm", role="admin"), _body())
    ids = audit.await_args.kwargs["details"]["fact_ids"]
    assert "bucket:trajectories:t-bob" in ids and "bucket:company:tenant-a:ca" in ids and "f-bob" in ids
    assert not any("tenant-b" in i for i in ids) and "tenant-b" not in repr(result)
    assert audit.await_args.kwargs["durable"] is True


@pytest.mark.asyncio
async def test_an_unaudited_admin_bucket_read_is_withheld():
    from fastapi import HTTPException

    kb = await _kb()
    with (
        patch("api.knowledge_search_aggregator.get_or_create_knowledge_base", new=AsyncMock(return_value=kb)),
        patch("services.audit_logger.audit_log", new=AsyncMock(return_value=False)),
        pytest.raises(HTTPException) as refused,
    ):
        await get_multi_source_graph(MagicMock(), _body(), _user("adm", role="admin"))
    assert refused.value.status_code == 503


@pytest.mark.asyncio
async def test_sections_are_typed_in_the_response_model():
    result, _ = await _call(_user(ALICE), _body())
    typed = KnowledgeMultiSourceGraphResponse(**result)
    assert {s.key for s in typed.stats.sections} == {"facts", "research"}
    assert all(isinstance(s.limited, bool) and isinstance(s.truncated, bool) for s in typed.stats.sections)


@pytest.mark.asyncio
async def test_post_offset_pages_buckets_and_facts_together():
    result, _ = await _call(_user("adm", role="admin"), _body(offset=1, max_facts=1))
    sections = {s["key"]: s for s in result["stats"]["sections"]}
    assert (sections["facts"]["returned"], sections["facts"]["limited"]) == (1, False)
    assert (sections["research"]["total"], sections["research"]["returned"]) == (2, 1)


@pytest.mark.asyncio
async def test_get_graph_accepts_offset():
    kb = await _kb()
    with (
        patch("api.knowledge_search_aggregator.get_or_create_knowledge_base", new=AsyncMock(return_value=kb)),
        patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)),
    ):
        result = await get_multi_source_graph_simple(
            MagicMock(), max_facts=1, include_categories=False, offset=1, current_user=_user("adm", role="admin")
        )
    sections = {s["key"]: s for s in result["stats"]["sections"]}
    assert sections["facts"]["returned"] == 1 and sections["research"]["returned"] == 1
