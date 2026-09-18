# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Orphan repair, judged and applied through each type's own service (#15779, #16927).

The knowledge half runs the **real** ``KnowledgeOwnership.check_access`` before and
after a repair: the test #16927 was missing, since its grant row was read by no
access check. Envelope secrets need Postgres for the real service, so their end-to-end
test is in ``tests/migrations/test_orphan_secret_repair.py``; here their judgment is
tested against a stand-in session.
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.ownership import KnowledgeOwnership
from services.orphan_repair import (
    InvalidNewOwner,
    NotAnOrphan,
    UnknownResourceType,
    find_orphans,
    repair_orphan,
    user_state,
)
from services.orphan_repair_types import EnvelopeSecretRepairer, KnowledgeFactRepairer

LIVE, NEW_OWNER = str(uuid.uuid4()), str(uuid.uuid4())
DELETED, HARD_DELETED = str(uuid.uuid4()), str(uuid.uuid4())


class _Users:
    """A session that knows four users: two live, one soft-deleted, one hard-deleted (no row)."""

    def __init__(self, secret=None, grantees=()) -> None:
        self.secret, self.grantees = secret, list(grantees)

    async def get(self, model, key):
        if model.__name__ == "Secret":
            return self.secret
        key = str(key)
        if key in (LIVE, NEW_OWNER):
            return SimpleNamespace(deleted_at=None)
        if key == DELETED:
            return SimpleNamespace(deleted_at=datetime.now(tz=timezone.utc))
        return None

    async def execute(self, _statement):
        return SimpleNamespace(scalars=lambda: iter(self.grantees))


class _KB:
    """The knowledge base surface the repairer uses: get_fact, update_fact, get_all_facts."""

    def __init__(self, **facts) -> None:
        self.facts = facts

    def get_fact(self, fact_id):
        return {"fact_id": fact_id, "metadata": dict(self.facts[fact_id])} if fact_id in self.facts else None

    async def update_fact(self, fact_id, metadata):
        self.facts[fact_id].update(metadata)
        return {"status": "success"}

    async def get_all_facts(self, limit=None):
        return [{"fact_id": k, "metadata": dict(v)} for k, v in list(self.facts.items())[:limit]]


def _repairers(kb):
    async def _factory():
        return kb

    return {"knowledge_fact": KnowledgeFactRepairer(kb_factory=_factory)}


@pytest.fixture
def audit():
    with patch("services.orphan_repair.audit_log", new=AsyncMock(return_value=True)) as audit_log:
        yield audit_log


class TestUserState:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("user_id", "state"),
        [(LIVE, "live"), (DELETED, "deleted"), (HARD_DELETED, "deleted"), ("admin", "unresolvable"), (None, "none")],
    )
    async def test_each_state(self, user_id, state):
        assert await user_state(_Users(), user_id) == state


class TestKnowledgeFacts:
    ORPHAN = {"owner_id": DELETED, "visibility": "organization", "organization_id": None}

    @pytest.mark.asyncio
    async def test_a_deleted_users_fact_is_repaired_and_the_new_owner_passes_the_real_access_check(self, audit):
        """#15779's deleted-user case, end to end through KnowledgeOwnership.check_access."""
        kb, ownership = _KB(f1=dict(self.ORPHAN)), KnowledgeOwnership(MagicMock())
        assert not await ownership.check_access("f1", NEW_OWNER, kb.facts["f1"])

        result = await repair_orphan(_Users(), _repairers(kb), "knowledge_fact", "f1", NEW_OWNER, actor_user_id="a")

        assert await ownership.check_access("f1", NEW_OWNER, kb.facts["f1"])
        assert result["conditions"] == {"owner": "deleted", "grant": "none", "scope": "organization_without_company"}
        assert audit.await_args.kwargs["details"]["conditions"]["owner"] == "deleted"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "metadata",
        [
            {"owner_id": LIVE, "visibility": "organization"},
            {"owner_id": "admin", "visibility": "private"},
            {"owner_id": DELETED, "visibility": "organization", "organization_id": "org-1"},
            {"owner_id": DELETED, "visibility": "shared", "shared_with": [LIVE]},
            {"owner_id": DELETED, "visibility": "private", "access_level": "general"},
        ],
        ids=["live owner", "unresolvable owner", "company reaches it", "shared with a live user", "open access level"],
    )
    async def test_the_negative_controls_a_reachable_fact_is_refused_and_untouched(self, audit, metadata):
        kb = _KB(f1=dict(metadata))

        with pytest.raises(NotAnOrphan):
            await repair_orphan(_Users(), _repairers(kb), "knowledge_fact", "f1", NEW_OWNER, actor_user_id="a")

        assert kb.facts["f1"] == metadata
        assert audit.await_args.kwargs["result"] == "denied"

    @pytest.mark.asyncio
    async def test_a_null_owner_private_fact_is_an_orphan(self):
        kb = _KB(f1={"owner_id": "", "visibility": "private"})

        assert (await KnowledgeFactRepairer(kb_factory=AsyncMock(return_value=kb)).assess(_Users(), "f1")).orphaned

    @pytest.mark.asyncio
    async def test_orphans_are_found_by_the_same_judgment(self):
        kb = _KB(f1=dict(self.ORPHAN), f2={"owner_id": LIVE, "visibility": "private"})

        found = await find_orphans(_Users(), _repairers(kb), "knowledge_fact", limit=10)

        assert [row["resource_id"] for row in found] == ["f1"]


class TestEnvelopeSecretJudgment:
    """The real envelope service needs Postgres; its end-to-end repair is in the migration-gate suite."""

    @staticmethod
    def _secret(owner):
        return SimpleNamespace(
            id=uuid.uuid4(), owner_id=uuid.UUID(owner), sealed_value={"x": 1}, owner_vault=f"user:{owner}"
        )

    @pytest.mark.asyncio
    async def test_a_secret_whose_only_vault_is_a_deleted_users_is_an_orphan(self):
        session = _Users(self._secret(DELETED), [f"user:{DELETED}"])

        verdict = await EnvelopeSecretRepairer().assess(session, str(session.secret.id))

        assert verdict.orphaned and verdict.conditions["dead_vaults"] == [f"user:{DELETED}"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "grantees",
        [[f"user:{DELETED}", f"user:{LIVE}"], [f"user:{DELETED}", "system"], [f"user:{DELETED}", "team:t1"], []],
        ids=["a live user holds it", "the system vault holds it", "a team vault cannot be proven dead", "no grant"],
    )
    async def test_the_negative_controls_a_secret_any_live_vault_holds_is_not_an_orphan(self, grantees):
        session = _Users(self._secret(DELETED), grantees)

        assert not (await EnvelopeSecretRepairer().assess(session, str(session.secret.id))).orphaned

    @pytest.mark.asyncio
    async def test_a_live_owner_blocks_it(self):
        session = _Users(self._secret(LIVE), [f"user:{DELETED}"])

        assert not (await EnvelopeSecretRepairer().assess(session, str(session.secret.id))).orphaned


class TestTheBreakGlassRules:
    @pytest.mark.asyncio
    async def test_an_unknown_type_is_refused_and_audited(self, audit):
        with pytest.raises(UnknownResourceType):
            await repair_orphan(_Users(), {}, "widget", "w1", NEW_OWNER, actor_user_id="a")

        assert audit.await_args.kwargs["result"] == "denied"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "new_owner", [DELETED, HARD_DELETED, "admin"], ids=["soft-deleted", "no row", "not a uuid"]
    )
    async def test_the_new_owner_must_be_proven_live(self, audit, new_owner):
        kb = _KB(f1=dict(TestKnowledgeFacts.ORPHAN))

        with pytest.raises(InvalidNewOwner):
            await repair_orphan(_Users(), _repairers(kb), "knowledge_fact", "f1", new_owner, actor_user_id="a")

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_is_audited_too(self, audit):
        """#16940: a break-glass that failed must leave a trace, not only one that was refused."""
        broken = MagicMock(assess=AsyncMock(side_effect=RuntimeError("store down")))

        with pytest.raises(RuntimeError):
            await repair_orphan(_Users(), {"x": broken}, "x", "r1", NEW_OWNER, actor_user_id="a")

        assert audit.await_args.kwargs["result"] == "error"
