# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""check_access reads list metadata as lists and takes an explicit admin input (#16662).

Search results carry metadata straight from ChromaDB, where ID lists are stored as
comma-joined strings; before #16662 ``user_id in shared_with`` was then a substring
test and ``frozenset(group_ids)`` a set of characters.
"""

import pytest

from knowledge.ownership import KnowledgeOwnership

OWNER = "owner-1"


def _mgr() -> KnowledgeOwnership:
    return KnowledgeOwnership(redis_client=object())


def _meta(visibility: str, **extra) -> dict:
    return {"owner_id": OWNER, "visibility": visibility, "access_level": "user", **extra}


@pytest.mark.asyncio
@pytest.mark.parametrize("shared_with", ["bobby, alice", "bobby,alice", '["bobby", "alice"]'])
async def test_a_substring_of_a_shared_user_is_not_that_user(shared_with):
    mgr = _mgr()
    meta = _meta("shared", shared_with=shared_with)
    assert await mgr.check_access("f", "bob", meta) is False
    assert await mgr.check_access("f", "alice", meta) is True


@pytest.mark.asyncio
async def test_a_group_list_stored_as_a_string_is_matched_by_member_not_character():
    mgr = _mgr()
    meta = _meta("group", group_ids="grp-1, grp-2")
    assert await mgr.check_access("f", "u", meta, user_group_ids=["grp-2"]) is True
    assert await mgr.check_access("f", "u", meta, user_group_ids=["g"]) is False


@pytest.mark.asyncio
async def test_an_explicit_admin_read_sees_another_users_private_fact():
    mgr = _mgr()
    meta = _meta("private")
    assert await mgr.check_access("f", "admin-1", meta, is_admin=True) is True


@pytest.mark.asyncio
async def test_without_the_admin_input_the_same_read_is_denied():
    mgr = _mgr()
    assert await mgr.check_access("f", "admin-1", _meta("private")) is False
