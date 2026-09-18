# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-type orphan repair: each type judged and repaired through its own service (#16927).

``knowledge_fact`` is gated by ``KnowledgeOwnership.check_access``: its grant source
is ``SHARED`` scope with a ``shared_with`` list, and the owner is written through
``KnowledgeBase.update_fact``, which also re-files the fact's ownership indexes.

``secret`` means an envelope secret. It is gated by vault grants, not by a scope
rule: a caller reaches it by holding a ``SecretGrant`` for one of their vaults. It is
orphaned when every grant names a vault no live principal holds. The repair re-wraps
the data key for the new owner's user vault through ``EnvelopeSecretsService.share``;
the plaintext is never decrypted, returned or logged.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.scoping.scope_level import ScopeLevel
from autobot_shared.scoping.visibility import ResourceDescriptor, is_unreachable
from autobot_shared.secrets_vault import VaultKind, VaultRef
from services.orphan_repair import (
    Assessment,
    OrphanRepairer,
    RepairWriteFailed,
    ResourceNotFound,
    owner_blocks_repair,
    user_state,
)

_OPEN_ACCESS_LEVELS = ("general", "autobot")  # knowledge AccessLevel values that reach anyone signed in


def _scope_condition(resource: ResourceDescriptor) -> str:
    """Why the scope key does, or does not, reach a principal."""
    if resource.scope is ScopeLevel.ORGANIZATION:
        return "organization_reachable" if resource.company_id else "organization_without_company"
    if resource.scope is ScopeLevel.GROUP:
        return "group_reachable" if resource.effective_group_ids() else "group_without_groups"
    if resource.scope in (ScopeLevel.SYSTEM, ScopeLevel.PUBLIC):
        return f"open:{resource.scope.value}"
    return f"owner_only:{resource.scope.value}"


class KnowledgeFactRepairer:
    """``knowledge_fact``: judged exactly as ``KnowledgeOwnership.check_access`` reads the metadata."""

    def __init__(self, kb_factory: Callable[[], Awaitable[Any]] | None = None) -> None:
        self._kb_factory = kb_factory

    async def _kb(self) -> Any:
        if self._kb_factory is not None:
            return await self._kb_factory()
        from knowledge_factory import get_or_create_knowledge_base

        return await get_or_create_knowledge_base()

    async def _metadata(self, fact_id: str) -> Tuple[Any, Dict[str, Any]]:
        kb = await self._kb()
        fact = await asyncio.to_thread(kb.get_fact, fact_id)  # get_fact is synchronous (#16670)
        if not fact:
            raise ResourceNotFound(f"knowledge fact {fact_id!r} not found")
        return kb, dict(fact.get("metadata") or {})

    @staticmethod
    def _descriptor(metadata: Dict[str, Any]) -> ResourceDescriptor:
        from knowledge.utils import decode_id_list

        try:
            scope = ScopeLevel(metadata.get("visibility", "private"))
        except ValueError:
            scope = ScopeLevel.PRIVATE  # check_access fails an unknown visibility closed the same way
        return ResourceDescriptor(
            owner_id=metadata.get("owner_id") or None,
            company_id=metadata.get("organization_id") or None,
            scope=scope,
            group_ids=frozenset(decode_id_list(metadata.get("group_ids"))),
        )

    @staticmethod
    async def _share_held(session: AsyncSession, metadata: Dict[str, Any]) -> bool:
        """The fact's own grant source: SHARED scope and a listed user who is not proven dead."""
        from knowledge.utils import decode_id_list

        if metadata.get("visibility") != ScopeLevel.SHARED.value:
            return False
        states = [await user_state(session, uid) for uid in decode_id_list(metadata.get("shared_with"))]
        return any(state in ("live", "unresolvable") for state in states)

    async def assess(self, session: AsyncSession, resource_id: str) -> Assessment:
        _, metadata = await self._metadata(resource_id)
        return await self._assess_metadata(session, metadata)

    async def find_orphans(self, session: AsyncSession, limit: int) -> List[Dict[str, Any]]:
        """Orphans among the first *limit* facts (#15779 AC4), judged exactly as ``assess`` judges one."""
        kb = await self._kb()
        found = []
        for fact in await kb.get_all_facts(limit=limit):
            verdict = await self._assess_metadata(session, dict(fact.get("metadata") or {}))
            if verdict.orphaned:
                found.append({"resource_id": fact.get("fact_id"), "conditions": verdict.conditions})
        return found

    async def _assess_metadata(self, session: AsyncSession, metadata: Dict[str, Any]) -> Assessment:
        level = metadata.get("access_level", "user")
        if level in _OPEN_ACCESS_LEVELS:
            return Assessment(False, {"access_level": level})
        owner_blocks, owner = await owner_blocks_repair(session, metadata.get("owner_id"))
        shared = await self._share_held(session, metadata)
        resource = self._descriptor(metadata)
        conditions = {"owner": owner, "grant": "shared_with" if shared else "none", "scope": _scope_condition(resource)}
        return Assessment(is_unreachable(resource, shared, owner_is_live=owner_blocks), conditions)

    async def repair(
        self, session: AsyncSession, resource_id: str, new_owner_id: str, assessment: Assessment
    ) -> Dict[str, Any]:
        kb, metadata = await self._metadata(resource_id)
        # Unconditional: update_fact has no compare-and-set to hold the judgment to the write (#16984).
        result = await kb.update_fact(fact_id=resource_id, metadata={"owner_id": new_owner_id})
        if result.get("status") != "success":
            raise RepairWriteFailed("the knowledge store did not accept the new owner")
        return {"before": {"owner_id": metadata.get("owner_id")}, "after": {"owner_id": new_owner_id}}


async def _vault_is_dead(session: AsyncSession, vault: str) -> bool:
    """Only a *proven* dead vault counts. A user vault is dead when its user is deleted.

    ``system`` is always live, and agent, service, team, role, company and node vaults
    cannot be proven dead here, so they count as live and block a repair.
    """
    try:
        ref = VaultRef.parse(vault)
    except ValueError:
        return False
    return ref.kind is VaultKind.USER and await user_state(session, ref.id) == "deleted"


class EnvelopeSecretRepairer:
    """``secret``: an envelope secret, judged by its vault grants and repaired by re-wrapping its key."""

    def __init__(self, service_factory: Callable[[], Any] | None = None) -> None:
        self._service_factory = service_factory

    def _service(self) -> Any:
        if self._service_factory is not None:
            return self._service_factory()
        from services.envelope_secrets_service import EnvelopeSecretsService

        return EnvelopeSecretsService()

    @staticmethod
    async def _load(session: AsyncSession, resource_id: str, *, lock: bool = False) -> Tuple[Any, List[str]]:
        from models.secret import Secret
        from models.secret_grant import SecretGrant

        try:
            secret_id = uuid.UUID(str(resource_id))
        except ValueError:
            raise ResourceNotFound(f"secret {resource_id!r} is not a secret id") from None
        secret = await session.get(Secret, secret_id, with_for_update=lock)
        if secret is None or secret.sealed_value is None:
            raise ResourceNotFound(f"envelope secret {resource_id!r} not found")
        rows = await session.execute(select(SecretGrant.grantee).where(SecretGrant.secret_id == secret_id))
        return secret, list(rows.scalars())

    async def assess(self, session: AsyncSession, resource_id: str) -> Assessment:
        """Judged under a row lock held to the end of the transaction: two break-glass
        repairs of one secret serialize, and the second finds the first's live owner."""
        return await self._judge(session, resource_id, lock=True)

    async def _judge(self, session: AsyncSession, resource_id: str, *, lock: bool) -> Assessment:
        secret, grantees = await self._load(session, resource_id, lock=lock)
        owner_blocks, owner = await owner_blocks_repair(session, str(secret.owner_id) if secret.owner_id else None)
        dead = [vault for vault in grantees if await _vault_is_dead(session, vault)]
        live = [vault for vault in grantees if vault not in dead]
        conditions = {"owner": owner, "dead_vaults": dead, "live_vaults": live}
        # A secret with no grant at all cannot be re-wrapped: nothing holds its key.
        return Assessment(not owner_blocks and not live and bool(dead), conditions)

    async def find_orphans(self, session: AsyncSession, limit: int) -> List[Dict[str, Any]]:
        """Orphans among the first *limit* envelope secrets (#15779 AC4), judged exactly as ``assess`` is."""
        from models.secret import Secret

        rows = await session.execute(select(Secret.id).where(Secret.sealed_value.isnot(None)).limit(limit))
        found = []
        for secret_id in rows.scalars():
            verdict = await self._judge(session, str(secret_id), lock=False)  # a listing locks nothing
            if verdict.orphaned:
                found.append({"resource_id": str(secret_id), "conditions": verdict.conditions})
        return found

    async def repair(
        self, session: AsyncSession, resource_id: str, new_owner_id: str, assessment: Assessment
    ) -> Dict[str, Any]:
        secret, _ = await self._load(session, resource_id)
        before = {"owner_id": str(secret.owner_id), "owner_vault": secret.owner_vault}
        new_vault = VaultRef(VaultKind.USER, str(new_owner_id))
        dead = [VaultRef.parse(vault) for vault in assessment.conditions["dead_vaults"]]
        await self._service().share(
            session, secret_id=secret.id, actor_vaults=dead, grantee=new_vault, created_by=None
        )  # re-wraps the data key for the new vault; the value is never decrypted
        secret.owner_id = uuid.UUID(str(new_owner_id))
        secret.owner_vault = new_vault.to_str()
        await session.flush()
        return {"before": before, "after": {"owner_id": str(secret.owner_id), "owner_vault": secret.owner_vault}}


#: The resource types a break-glass can repair. Any other type is refused.
REPAIRERS: Dict[str, OrphanRepairer] = {
    "knowledge_fact": KnowledgeFactRepairer(),
    "secret": EnvelopeSecretRepairer(),
}
