# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Find same-name envelope secrets and verify each copy against its target (#17850, #17038).

Owner ruling (2026-11-20): duplicate credentials are always resolved by verification, and the copy that works
wins. Age, id and lookup order never decide. This module only READS and PROBES; it deletes nothing. What to do
with the result is a proposal a human approves (``services/secret_duplicate_proposals.py``).

Reads go through ``SecretsCoordinator.maintenance_read`` (admin-only, attributable, audited first; #17773).

Verifier per secret type: an LLM provider key named by its env-var label is probed with the provider's own health check
(``services.provider_health.providers``), which sends one authenticated read through the guarded fetch under the
egress policy. A name with no verifier is ``NO_VERIFIER`` -- never "verified", never "failed" -- and the group
goes to a person with no recommendation. That includes the vault's canonical ``llm:provider:<name>:api_key``
names (the SLM's LLM-provider producer): a provider's target is its own configured endpoint, which a name alone
does not give, so those groups are MANUAL-ONLY (#17850) -- never guessed against a default endpoint, never ordered
or aged, never rotated to make a copy verifiable. Nothing here logs or returns a name or a value: groups are ids.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from models.secret import Secret
from services.envelope_secrets_service import SecretAccessError
from services.secrets_coordinator import SecretsCoordinator
from services.secrets_maintenance import MaintenanceActor, MaintenanceAuditError

logger = get_logger(__name__)


class Verdict(str, enum.Enum):
    """What probing one copy against its target showed."""

    VERIFIED = "verified"  # the target accepted it
    NOT_VERIFIED = "not_verified"  # rejected, unreachable, rate limited or unreadable: it did not work
    NO_VERIFIER = "no_verifier"  # no probe exists for this secret


@dataclass(frozen=True)
class SecretDuplicateGroup:
    """Rows sharing one ``(owner_vault, name)``. The name is held for probing only and is never rendered."""

    owner_vault: str
    name: str
    secret_ids: tuple[uuid.UUID, ...]
    versions: tuple[int, ...] = ()  # rotation generation of each copy, aligned with ``secret_ids`` (#17850)


@dataclass(frozen=True)
class GroupVerification:
    """Per-copy verdicts for one group, keyed by secret id."""

    group: SecretDuplicateGroup
    verdicts: dict[uuid.UUID, Verdict]

    @property
    def verified_ids(self) -> list[uuid.UUID]:
        return sorted((i for i, v in self.verdicts.items() if v is Verdict.VERIFIED), key=str)

    @property
    def survivor_id(self) -> uuid.UUID | None:
        """The one verified copy, or ``None`` -- zero, several, or an unverifiable type is a human's call."""
        verified = self.verified_ids
        return verified[0] if len(verified) == 1 and self._all_probed else None

    @property
    def _all_probed(self) -> bool:
        return Verdict.NO_VERIFIER not in self.verdicts.values()


def _probe_classes() -> dict[str, type]:
    """Secret name -> the provider health checker that can probe a candidate key. Loaded lazily (heavy imports)."""
    from services.provider_health.providers import AnthropicHealth, GoogleHealth, OpenAIHealth

    return {"OPENAI_API_KEY": OpenAIHealth, "ANTHROPIC_API_KEY": AnthropicHealth, "GOOGLE_API_KEY": GoogleHealth}


def has_verifier(name: str) -> bool:
    """Whether a copy named *name* can be probed against its target."""
    return name in _probe_classes()


async def find_duplicate_groups(session: AsyncSession) -> list[SecretDuplicateGroup]:
    """Every ``(owner_vault, name)`` with more than one envelope row, ordered by vault then smallest id."""
    dupes = (
        select(Secret.owner_vault, Secret.name)
        .where(Secret.owner_vault.isnot(None))
        .group_by(Secret.owner_vault, Secret.name)
        .having(func.count() > 1)
        .subquery()
    )
    rows = await session.execute(
        select(Secret.owner_vault, Secret.name, Secret.id, Secret.version)
        .join(dupes, (Secret.owner_vault == dupes.c.owner_vault) & (Secret.name == dupes.c.name))
        .order_by(Secret.owner_vault, Secret.name, Secret.id)
    )
    grouped: dict[tuple[str, str], list[tuple[uuid.UUID, int]]] = {}
    for vault, name, secret_id, version in rows:
        grouped.setdefault((vault, name), []).append((secret_id, version))
    return [
        SecretDuplicateGroup(v, n, tuple(i for i, _ in found), tuple(ver for _, ver in found))
        for (v, n), found in grouped.items()
    ]


async def _probe(name: str, value: str) -> Verdict:
    """One authenticated read against the target through the provider's health check (guarded fetch)."""
    from services.provider_health.base import ProviderHealthStatus

    checker = _probe_classes()[name]()
    checker.api_key, checker.key_refusal = value, ""  # the candidate, not the resolved runtime key
    result = await checker.check_health()
    return Verdict.VERIFIED if result.status == ProviderHealthStatus.HEALTHY else Verdict.NOT_VERIFIED


async def _open_copy(
    session: AsyncSession, coordinator: SecretsCoordinator, actor: MaintenanceActor, secret_id: uuid.UUID
) -> str | None:
    """The copy's value through the coordinator's maintenance path, or ``None`` when it cannot be read.

    A REFUSAL (not an administrator, or the audit entry could not be written) is raised, never read as "this copy
    does not work": that would let a missing permission recommend the removal of a working credential.
    """
    try:
        return (await coordinator.maintenance_read(session, actor=actor, secret_id=secret_id)).decode("utf-8")
    except (SecretAccessError, MaintenanceAuditError):
        raise
    except Exception as exc:  # unreadable or undecodable: it did not verify
        logger.warning("A duplicate secret copy could not be read (%s)", type(exc).__name__)
        return None


async def verify_copy(
    session: AsyncSession,
    coordinator: SecretsCoordinator,
    actor: MaintenanceActor,
    group: SecretDuplicateGroup,
    secret_id: uuid.UUID,
) -> Verdict:
    """Open one copy and probe it. Failures are verdicts; nothing is logged but the exception class."""
    if not has_verifier(group.name):
        return Verdict.NO_VERIFIER
    value = await _open_copy(session, coordinator, actor, secret_id)
    if value is None:
        return Verdict.NOT_VERIFIED
    try:
        return await _probe(group.name, value)
    except Exception as exc:  # the probe itself failed: it did not verify
        logger.warning("A duplicate secret copy could not be probed (%s)", type(exc).__name__)
        return Verdict.NOT_VERIFIED


async def verify_group(
    session: AsyncSession,
    group: SecretDuplicateGroup,
    actor: MaintenanceActor,
    coordinator: SecretsCoordinator | None = None,
) -> GroupVerification:
    """Verify every copy of *group* independently of order."""
    coordinator = coordinator or SecretsCoordinator()
    verdicts = {sid: await verify_copy(session, coordinator, actor, group, sid) for sid in group.secret_ids}
    return GroupVerification(group, verdicts)
