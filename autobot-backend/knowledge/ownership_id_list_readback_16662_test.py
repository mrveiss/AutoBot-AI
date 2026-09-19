# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Share, unshare and cleanup read ``shared_with``/``group_ids`` back as lists (#16662).

ChromaDB stores ID lists as comma-joined strings. Read back raw, ``set("bobby,alice")``
is a set of characters: sharing would add one index entry per letter, unsharing
would find no user, and cleanup would strip ``user:kb:shared:b`` instead of
``user:kb:shared:bobby``.
"""

from __future__ import annotations

from collections import defaultdict

import pytest

from knowledge.ownership import KnowledgeOwnership


class _SetStore:
    """The two Redis set commands the sharing indexes use."""

    def __init__(self):
        self.sets: dict[str, set] = defaultdict(set)

    def sadd(self, key, *members):
        self.sets[key].update(members)

    def srem(self, key, *members):
        self.sets[key].difference_update(members)


def _comma_joined(**extra) -> dict:
    return {"owner_id": "o", "visibility": "shared", "shared_with": "bobby,alice", "group_ids": "g1, g2", **extra}


@pytest.mark.asyncio
async def test_sharing_again_keeps_the_stored_users_as_users():
    meta = await KnowledgeOwnership(_SetStore()).share_fact("f", user_ids=["carol"], fact_metadata=_comma_joined())

    assert sorted(meta["shared_with"]) == ["alice", "bobby", "carol"]
    assert sorted(meta["group_ids"]) == ["g1", "g2"]


@pytest.mark.asyncio
async def test_unsharing_finds_a_user_stored_in_a_comma_joined_list():
    store = _SetStore()
    store.sets["user:kb:shared:bobby"].add("f")

    meta = await KnowledgeOwnership(store).unshare_fact("f", user_ids=["bobby"], fact_metadata=_comma_joined())

    assert meta["shared_with"] == ["alice"]
    assert "f" not in store.sets["user:kb:shared:bobby"]


@pytest.mark.asyncio
async def test_cleanup_removes_whole_ids_not_characters():
    store = _SetStore()
    for key in ("user:kb:shared:bobby", "user:kb:shared:alice", "group:kb:facts:g1", "group:kb:facts:g2"):
        store.sets[key].add("f")

    await KnowledgeOwnership(store).cleanup_ownership_indexes("f", _comma_joined())

    assert not any("f" in members for members in store.sets.values())
    assert "user:kb:shared:b" not in store.sets
