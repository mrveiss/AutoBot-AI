# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Runtime credential loader for per-user/per-run LLM provider credentials (GH#9037).

Provides utilities to load user-stored provider credentials and inject them
into the request context for use by the provider registry.
"""

import json
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from models.secret import Secret, SecretScope
from services.secrets_service import SecretsService

from .provider_registry import RunCredentialContext, set_run_credentials

logger = get_logger(__name__)


async def load_user_provider_credentials(
    user_id: UUID,
    db: AsyncSession,
    provider_names: list[str] | None = None,
) -> RunCredentialContext:
    """Load user's provider credentials from the database.

    Args:
        user_id: User whose credentials to load.
        db: Database session.
        provider_names: Optional list of provider names to load.
                        If None, loads all user's provider credentials.

    Returns:
        RunCredentialContext with decrypted provider credentials.
    """
    # Query user's provider credentials
    stmt = select(Secret).where(
        Secret.owner_id == user_id,
        Secret.name.like("provider_credential_%"),
        Secret.scope == SecretScope.USER.value,
        Secret.is_active == True,  # noqa: E712
    )

    if provider_names:
        # Filter by specific provider names
        name_filters = [Secret.name == f"provider_credential_{name}" for name in provider_names]
        from sqlalchemy import or_

        stmt = stmt.where(or_(*name_filters))

    result = await db.execute(stmt)
    secrets = result.scalars().all()

    # Decrypt and build credential context
    secrets_service = SecretsService()
    provider_credentials: Dict[str, Dict[str, Any]] = {}

    for secret in secrets:
        provider_name = secret.name.replace("provider_credential_", "")
        try:
            decrypted = secrets_service.cipher.decrypt(secret.encrypted_value.encode()).decode()
            credential_data = json.loads(decrypted)
            provider_credentials[provider_name] = credential_data
            logger.debug(
                "Loaded credentials for provider %s (user %s)",
                provider_name,
                user_id,
            )
        except Exception as exc:
            logger.warning(
                "Failed to decrypt credential for provider %s (user %s): %s",
                provider_name,
                user_id,
                exc,
            )

    return RunCredentialContext(provider_credentials=provider_credentials)


async def inject_user_credentials(
    user_id: UUID,
    db: AsyncSession,
    provider_names: list[str] | None = None,
) -> None:
    """Load and inject user's provider credentials into the current request context.

    This should be called at the start of a request handler that will make
    LLM calls. The credentials will be scoped to the current async task and
    will not leak to concurrent requests.

    Args:
        user_id: User whose credentials to inject.
        db: Database session.
        provider_names: Optional list of provider names to load.
    """
    context = await load_user_provider_credentials(user_id, db, provider_names)
    set_run_credentials(context)
    logger.debug(
        "Injected provider credentials for user %s (providers: %s)",
        user_id,
        list(context.provider_credentials.keys()),
    )


def inject_runtime_credentials(provider_credentials: Dict[str, Dict[str, Any]]) -> None:
    """Directly inject runtime credentials into the current request context.

    Use this when you already have the credentials dict (e.g., from a
    workflow invocation payload) and don't need to load from the database.

    Args:
        provider_credentials: Dict mapping provider name → settings.
    """
    context = RunCredentialContext(provider_credentials=provider_credentials)
    set_run_credentials(context)
    logger.debug(
        "Injected runtime credentials (providers: %s)",
        list(provider_credentials.keys()),
    )


__all__ = [
    "load_user_provider_credentials",
    "inject_user_credentials",
    "inject_runtime_credentials",
]
