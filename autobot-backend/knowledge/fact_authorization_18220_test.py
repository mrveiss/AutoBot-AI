# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A non-reader cannot tell an existing fact from a missing one, and non-object metadata denies (#18220)."""

import logging
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from knowledge.ownership import KnowledgeOwnership
from knowledge.search_filters import authorize_fact_read, authorize_fact_write

ALICE = {"user_id": "alice", "role": "user"}
ADMIN = {"user_id": "root", "role": "admin"}
CONTENT_MARKER = "private-body-text"


def _kb(fact):
    kb = MagicMock()
    kb.get_fact = MagicMock(return_value=fact)
    kb.ownership_manager = KnowledgeOwnership(redis_client=object())
    return kb


def _fact(metadata):
    return {"fact_id": "f1", "content": CONTENT_MARKER, "metadata": metadata}


async def _err(helper, kb, user=ALICE):
    with pytest.raises(HTTPException) as exc:
        await helper(kb, "f1", user)
    return exc.value


@pytest.mark.asyncio
@pytest.mark.parametrize("helper", [authorize_fact_read, authorize_fact_write])
async def test_a_non_reader_gets_exactly_the_response_for_a_missing_fact(helper):
    existing = await _err(helper, _kb(_fact({"owner_id": "bob", "visibility": "private"})))
    missing = await _err(helper, _kb(None))
    assert (existing.status_code, existing.detail) == (missing.status_code, missing.detail) == (404, "Fact not found")


@pytest.mark.asyncio
async def test_a_reader_without_write_still_gets_403():
    err = await _err(authorize_fact_write, _kb(_fact({"owner_id": "bob", "visibility": "public"})))
    assert (err.status_code, err.detail) == (403, "Access denied")


@pytest.mark.asyncio
async def test_a_reader_reads_and_the_owner_writes():
    fact = _fact({"owner_id": "alice", "visibility": "private"})
    assert await authorize_fact_read(_kb(fact), "f1", ALICE) is fact
    assert await authorize_fact_write(_kb(fact), "f1", ALICE) is fact


_SHAPES = {"list": ["a", "b"], "string": "owner", "number": 42}


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", sorted(_SHAPES))
@pytest.mark.parametrize("helper", [authorize_fact_read, authorize_fact_write])
async def test_non_object_metadata_is_denied_as_not_found_and_warned(shape, helper, caplog):
    kb = _kb(_fact(_SHAPES[shape]))
    with caplog.at_level(logging.WARNING):
        err = await _err(helper, kb)
    assert (err.status_code, err.detail) == (404, "Fact not found")
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "f1" in r.getMessage()]
    assert warnings and not any(CONTENT_MARKER in r.getMessage() or "owner" in r.getMessage() for r in warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize("helper", [authorize_fact_read, authorize_fact_write])
async def test_null_metadata_is_denied_as_not_found(helper):
    err = await _err(helper, _kb(_fact(None)))
    assert (err.status_code, err.detail) == (404, "Fact not found")


@pytest.mark.asyncio
@pytest.mark.parametrize("helper", [authorize_fact_read, authorize_fact_write])
async def test_malformed_metadata_json_is_denied_as_not_found(helper):
    """get_fact degrades unparseable metadata to a missing fact; a bare string stands in for what is left."""
    err = await _err(helper, _kb(_fact("{not json")))
    assert (err.status_code, err.detail) == (404, "Fact not found")


@pytest.mark.asyncio
@pytest.mark.parametrize("helper", [authorize_fact_read, authorize_fact_write])
@pytest.mark.parametrize("shape", [["a"], "x", 3, None])
async def test_an_admin_keeps_the_admin_rule_on_non_object_metadata(helper, shape):
    """An admin reads and writes any fact (#16662), unreadable metadata included; never a 500."""
    fact = _fact(shape)
    assert await helper(_kb(fact), "f1", ADMIN) is fact
