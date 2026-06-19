# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Access-transparency for unified secrets — "who can access this secret" (#10088 / Task 4).

Answers the PRD's tree-level audit requirement: given a secret, return its owner vault plus
every grantee vault, each resolved to the **member users** behind it (the reverse of
``services.secrets_principal_resolver``, which goes user → vaults). Pure read path over the
``secret_grants`` rows + the membership tables — no decryption, no mutation.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class VaultAccess:
    """One vault that can reach a secret, resolved to the users behind it."""

    vault: str  # canonical "kind:id" (or "system")
    kind: str  # VaultKind value
    id: str | None
    members: list[str]  # member user ids ([the id] for a user vault; [] for system/agent/etc.)


@dataclass
class SecretAccessReport:
    secret_id: str
    owner_vault: str
    grants: list[VaultAccess] = field(default_factory=list)
    effective_users: list[str] = field(default_factory=list)  # union of all member users


async def _members_of(session, ref) -> list[str]:
    """Member user ids behind a vault. Group vaults reverse the membership tables."""
    from sqlalchemy import select

    from autobot_shared.secrets_vault import VaultKind

    if ref.kind == VaultKind.USER:
        return [ref.id]
    if ref.kind == VaultKind.TEAM:
        from user_management.models.team import TeamMembership

        tid = _as_uuid(ref.id)
        if tid is None:
            return []
        rows = await session.execute(select(TeamMembership.user_id).where(TeamMembership.team_id == tid))
        return [str(u) for u in rows.scalars()]
    if ref.kind == VaultKind.ROLE:
        from user_management.models.role import Role, UserRole

        rows = await session.execute(
            select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.name == ref.id)
        )
        return [str(u) for u in rows.scalars()]
    if ref.kind == VaultKind.COMPANY:
        from llc.models.membership import LLCCompanyMembership

        cid = _as_uuid(ref.id)
        if cid is None:
            return []
        rows = await session.execute(select(LLCCompanyMembership.user_id).where(LLCCompanyMembership.company_id == cid))
        return [str(u) for u in rows.scalars()]
    return []  # system / agent / service / node — not expanded to member users here


def _as_uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


async def describe_secret_access(session, secret_id) -> SecretAccessReport | None:
    """Who can access *secret_id*: owner + every grantee vault, each resolved to its members.

    Returns ``None`` when the secret does not exist.
    """
    from sqlalchemy import select

    from autobot_shared.secrets_vault import VaultRef
    from models.secret import Secret
    from models.secret_grant import SecretGrant

    secret = (await session.execute(select(Secret).where(Secret.id == secret_id))).scalars().first()
    if secret is None:
        return None

    grants = (await session.execute(select(SecretGrant).where(SecretGrant.secret_id == secret_id))).scalars().all()
    report = SecretAccessReport(secret_id=str(secret_id), owner_vault=secret.owner_vault or "")
    effective: set[str] = set()
    for grant in grants:
        try:
            ref = VaultRef.parse(grant.grantee)
        except ValueError:
            logger.warning("Skipping unparseable grantee %r on secret %s", grant.grantee, secret_id)
            continue
        members = await _members_of(session, ref)
        report.grants.append(VaultAccess(vault=grant.grantee, kind=ref.kind.value, id=ref.id, members=members))
        effective.update(members)
    report.grants.sort(key=lambda v: v.vault)
    report.effective_users = sorted(effective)
    return report
