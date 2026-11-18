# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every fact route hides a fact's existence from a non-reader and denies on non-object metadata (#18220)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import knowledge_audit as audit
from api import knowledge_collaboration as collab
from api import knowledge_ownership as own
from knowledge.ownership import KnowledgeOwnership

ALICE = {"user_id": "alice", "role": "user"}
ADMIN = {"user_id": "root", "role": "admin"}
PRIVATE = '{"owner_id": "bob", "visibility": "private"}'
PUBLIC = '{"owner_id": "bob", "visibility": "public"}'
SHAPES = ["[1, 2]", '"owner"', "42", "null", "{not json"]


def _kb(raw):
    kb = MagicMock()
    kb.ownership_manager = KnowledgeOwnership(redis_client=object())
    kb.redis.return_value.hget = AsyncMock(return_value=raw)
    kb.get_fact = MagicMock(return_value=None if raw is None else {"fact_id": "f1", "metadata": _decode(raw)})
    return kb


def _decode(raw):
    """What the KB's synchronous ``get_fact`` hands back for a stored metadata value."""
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _share_req():
    return SimpleNamespace(user_ids=["u2"], group_ids=[])


def _perm_req():
    return SimpleNamespace(visibility="private", organization_id=None, group_ids=[])


async def _share(kb):
    with patch.object(collab, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
        return await collab.share_knowledge("f1", _share_req(), MagicMock(), ALICE)


async def _unshare(kb):
    with patch.object(collab, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
        return await collab.unshare_knowledge("f1", "u2", MagicMock(), ALICE, entity_type="user")


async def _permissions(kb):
    with patch.object(collab, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
        return await collab.update_knowledge_permissions("f1", _perm_req(), MagicMock(), ALICE)


async def _access_log(kb):
    with patch.object(audit, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
        return await audit.get_fact_access_log("f1", MagicMock(), ALICE, limit=10)


_ROUTES = [_share, _unshare, _permissions, _access_log]


async def _err(route, kb):
    with pytest.raises(HTTPException) as exc:
        await route(kb)
    return exc.value


@pytest.mark.asyncio
@pytest.mark.parametrize("route", _ROUTES)
async def test_a_non_reader_gets_the_response_for_a_missing_fact(route):
    existing = await _err(route, _kb(PRIVATE))
    missing = await _err(route, _kb(None))
    assert (existing.status_code, existing.detail) == (missing.status_code, missing.detail) == (404, "Fact not found")


@pytest.mark.asyncio
@pytest.mark.parametrize("route", _ROUTES)
async def test_a_reader_who_is_not_the_owner_keeps_403(route):
    err = await _err(route, _kb(PUBLIC))
    assert err.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize("raw", SHAPES)
async def test_non_object_metadata_is_the_404_never_a_500(route, raw):
    err = await _err(route, _kb(raw))
    assert (err.status_code, err.detail) == (404, "Fact not found")


# --- admin routes (share/unshare on the canonical route, visibility on the ownership one): an admin passes the read check on non-object metadata ---


def _own_kb(metadata):
    kb = MagicMock()
    kb.get_fact = MagicMock(return_value={"fact_id": "f1", "content": "c", "metadata": metadata})
    kb.ownership_manager.check_access = AsyncMock(return_value=True)
    kb.ownership_manager.share_fact = AsyncMock(return_value={"shared_with": ["u2"], "visibility": "shared"})
    kb.ownership_manager.unshare_fact = AsyncMock(return_value={"shared_with": [], "visibility": "private"})
    kb.update_fact = AsyncMock(return_value={"status": "success"})
    return kb


def _own_request():
    request = MagicMock()
    request.state.user = {"user_id": "root"}
    return request


async def _own_call(name, kb):
    if name in ("share", "unshare"):  # canonical collaboration routes since #18795
        with patch.object(collab, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
            if name == "share":
                return await collab.share_knowledge("f1", _share_req(), MagicMock(), ADMIN)
            return await collab.unshare_knowledge("f1", "u2", MagicMock(), ADMIN, entity_type="user")
    request = _own_request()
    with patch.object(own, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
        return await own.update_fact_visibility("f1", SimpleNamespace(visibility="private"), request, ADMIN)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["share", "unshare", "visibility"])
@pytest.mark.parametrize("shape", [["a"], "owner", 42, None])
async def test_ownership_routes_never_500_on_non_object_metadata(name, shape):
    result = await _own_call(name, _own_kb(shape))
    assert result  # reached the response: no AttributeError, no 500


# --- a degraded KB (no ownership manager) answers a missing and an existing fact alike ---


@pytest.mark.asyncio
async def test_the_audit_access_log_gives_503_for_missing_and_existing_alike_without_a_manager():
    missing, existing = _kb(None), _kb(PRIVATE)
    missing.ownership_manager = existing.ownership_manager = None
    a, b = await _err(_access_log, missing), await _err(_access_log, existing)
    assert (a.status_code, a.detail) == (b.status_code, b.detail) == (503, "Knowledge base not available")


@pytest.mark.asyncio
async def test_the_ownership_admin_routes_give_503_for_missing_and_existing_alike_without_a_manager():
    codes = []
    for fact in (None, {"fact_id": "f1", "content": "c", "metadata": {"owner_id": "bob"}}):
        kb = _own_kb({})
        kb.get_fact = MagicMock(return_value=fact)
        kb.ownership_manager = None
        with patch.object(own, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
            with pytest.raises(HTTPException) as exc:
                await own._get_fact_with_ownership(kb, "f1", "root")
        codes.append((exc.value.status_code, exc.value.detail))
    assert codes[0] == codes[1] == (503, "Ownership management not available")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["share", "unshare", "visibility"])
async def test_a_bad_fact_logs_one_warning_per_ownership_route(name, caplog):
    with caplog.at_level("WARNING"):
        await _own_call(name, _own_kb(["a"]))
    assert len([r for r in caplog.records if "non-object metadata" in r.getMessage()]) == 1
