# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Resolve the credentials an agent run receives through its roles (#20533).

The agent holds roles (``RoleAssignmentService.roles_held_by``); each role
references secrets (``RoleCredentialService.active_secrets_for_role``, which
excludes revoked ones at read time); the plaintext comes only from
``SecretService.get`` -- the canonical secrets manager. A secret whose name is
not an acceptable env var name is refused with an audited reason code: never
renamed, and neither its name nor its value is logged (an unusable name may
itself be a pasted value).
"""

from __future__ import annotations

import uuid
from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger

from ..credential_env import env_name_refusal
from ..models.activity import ActorType
from ..models.enums import RoleHolderType
from .base import LLCServiceBase
from .role_assignment import RoleAssignmentService
from .role_credential import RoleCredentialService
from .secret import SecretNotFound, SecretService

logger = get_logger(__name__)

REFUSED_EVENT = "role_credential.env_refused"


class RoleCredentialEnvResolver(LLCServiceBase):
    """``{env_name: plaintext}`` for the active credentials of an agent's roles."""

    async def _audit_refusal(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        secret_id: uuid.UUID,
        reason: str,
    ) -> None:
        logger.warning("role credential %s refused for env injection: reason=%s", secret_id, reason)
        await self.activity_log.record(
            session=session,
            company_id=str(company_id),
            actor_type=ActorType.SYSTEM,
            actor_id=None,
            event_type=REFUSED_EVENT,
            entity_type="llc_secret",
            entity_id=str(secret_id),
            after={"role_id": str(role_id), "reason": reason},
        )

    async def _value(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        secret_id: uuid.UUID,
        name: str,
    ):
        try:
            return await SecretService().get(session, str(company_id), name)
        except SecretNotFound:
            logger.warning("role credential %s revoked while resolving; not injected", secret_id)
            return None

    async def _resolve_role(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        out: Dict[str, str],
    ) -> None:
        for secret_id, name in await RoleCredentialService().active_secrets_for_role(session, company_id, role_id):
            reason = env_name_refusal(name)
            if reason is not None:
                await self._audit_refusal(session, company_id, role_id, secret_id, reason)
                continue
            value = await self._value(session, company_id, secret_id, name)
            if value is not None:
                out[name] = value

    async def resolve_for_agent(
        self, session: AsyncSession, company_id: uuid.UUID, agent_id: uuid.UUID
    ) -> Dict[str, str]:
        """Active, acceptably-named credentials across every role *agent_id* currently holds."""
        roles = await RoleAssignmentService().roles_held_by(session, company_id, RoleHolderType.AGENT, agent_id)
        resolved: Dict[str, str] = {}
        for role in roles:
            await self._resolve_role(session, company_id, role.id, resolved)
        return resolved
