# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Parity tests for KnowledgeOwnership.check_access (#11290).

Pin the full principal x visibility x access-level decision table BEFORE the
visibility-scope enum consolidation, so the refactor onto the canonical
``autobot_shared.scoping.ScopeLevel`` is provably behavior-preserving.
"""

import pytest

from knowledge.ownership import KnowledgeOwnership

OWNER = "owner-1"
STRANGER = "stranger-9"
ORG = "org-1"
GROUP = "grp-1"


def _mgr() -> KnowledgeOwnership:
    return KnowledgeOwnership(redis_client=object())


def _meta(
    visibility: str = "private",
    access_level: str = "user",
    owner_id: str | None = OWNER,
    shared_with: list | None = None,
    organization_id: str | None = None,
    group_ids: list | None = None,
) -> dict:
    return {
        "owner_id": owner_id,
        "visibility": visibility,
        "access_level": access_level,
        "shared_with": shared_with or [],
        "organization_id": organization_id,
        "group_ids": group_ids or [],
    }


# (label, metadata, user_id, user_org_id, user_group_ids, is_authenticated, expected)
DECISION_TABLE = [
    # --- owner always wins, any visibility ---
    ("owner_private", _meta("private"), OWNER, None, None, True, True),
    ("owner_shared", _meta("shared"), OWNER, None, None, True, True),
    ("owner_group", _meta("group"), OWNER, None, None, True, True),
    ("owner_org", _meta("organization"), OWNER, None, None, True, True),
    # --- private: stranger denied ---
    ("private_stranger", _meta("private"), STRANGER, None, None, True, False),
    # --- shared: only listed users ---
    ("shared_listed", _meta("shared", shared_with=[STRANGER]), STRANGER, None, None, True, True),
    ("shared_unlisted", _meta("shared", shared_with=["other"]), STRANGER, None, None, True, False),
    # --- group: membership intersection ---
    ("group_member", _meta("group", group_ids=[GROUP]), STRANGER, None, [GROUP], True, True),
    ("group_non_member", _meta("group", group_ids=[GROUP]), STRANGER, None, ["other-grp"], True, False),
    ("group_empty_fact_groups", _meta("group"), STRANGER, None, [GROUP], True, False),
    # --- organization: org match, requires user org set ---
    ("org_member", _meta("organization", organization_id=ORG), STRANGER, ORG, None, True, True),
    ("org_other", _meta("organization", organization_id=ORG), STRANGER, "org-2", None, True, False),
    ("org_both_none", _meta("organization", organization_id=None), STRANGER, None, None, True, False),
    # --- system/public: any authenticated user ---
    ("system_authed", _meta("system"), STRANGER, None, None, True, True),
    ("system_anon", _meta("system"), STRANGER, None, None, False, False),
    ("public_authed", _meta("public"), STRANGER, None, None, True, True),
    ("public_anon", _meta("public"), STRANGER, None, None, False, False),
    # --- unknown visibility value: fail closed for non-owner ---
    ("unknown_visibility", _meta("bogus"), STRANGER, None, None, True, False),
    ("unknown_visibility_owner", _meta("bogus"), OWNER, None, None, True, True),
    # --- access_level general: public, no auth required ---
    ("general_anon", _meta("private", access_level="general"), STRANGER, None, None, False, True),
    ("general_authed", _meta("private", access_level="general"), STRANGER, None, None, True, True),
    # --- access_level autobot: any authenticated user ---
    ("autobot_authed", _meta("private", access_level="autobot"), STRANGER, None, None, True, True),
    ("autobot_anon_private", _meta("private", access_level="autobot"), STRANGER, None, None, False, False),
    # --- access_level user/system: falls through to visibility rules ---
    ("user_level_private", _meta("private", access_level="user"), STRANGER, None, None, True, False),
    ("system_level_private", _meta("private", access_level="system"), STRANGER, None, None, True, False),
]


@pytest.mark.parametrize(
    "label,meta,user_id,user_org_id,user_group_ids,is_authenticated,expected",
    DECISION_TABLE,
    ids=[row[0] for row in DECISION_TABLE],
)
async def test_check_access_decision_table(
    label, meta, user_id, user_org_id, user_group_ids, is_authenticated, expected
):
    result = await _mgr().check_access(
        "fact-1",
        user_id,
        meta,
        user_org_id=user_org_id,
        user_group_ids=user_group_ids,
        is_authenticated=is_authenticated,
    )
    assert bool(result) is expected, label


async def test_missing_metadata_defaults_to_private_owner_only():
    """No visibility/access_level keys -> private + user level (owner only)."""
    mgr = _mgr()
    assert await mgr.check_access("f", OWNER, {"owner_id": OWNER}) is True
    assert not await mgr.check_access("f", STRANGER, {"owner_id": OWNER})


async def test_share_fact_visibility_transitions():
    """share_fact: private->shared for users; ->group when only groups added."""
    mgr = _mgr()

    class _FakeRedis:
        def sadd(self, *a):
            return 1

        def srem(self, *a):
            return 1

    mgr.redis_client = _FakeRedis()
    meta = await mgr.share_fact("f", user_ids=["u2"], fact_metadata={"visibility": "private"})
    assert meta["visibility"] == "shared"
    meta2 = await mgr.share_fact("f", group_ids=["g1"], fact_metadata={"visibility": "private"})
    assert meta2["visibility"] == "group"


async def test_unshare_fact_reverts_to_private():
    """unshare_fact: shared/group falls back to private when lists empty."""
    mgr = _mgr()

    class _FakeRedis:
        def sadd(self, *a):
            return 1

        def srem(self, *a):
            return 1

    mgr.redis_client = _FakeRedis()
    meta = await mgr.unshare_fact(
        "f", user_ids=["u2"], fact_metadata={"visibility": "shared", "shared_with": ["u2"]}
    )
    assert meta["visibility"] == "private"
