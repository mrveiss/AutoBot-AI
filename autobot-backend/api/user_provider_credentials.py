# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
User Provider Credentials API (GH#9037)

Allows users to store their own API keys for LLM providers.
Credentials are stored with USER scope and used for per-run overrides.
"""

import json
from typing import Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_middleware import get_current_user_id, get_db_session
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from models.secret import Secret, SecretScope, SecretType
from services.secrets_service import SecretsService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/user/provider-credentials", tags=["user-provider-credentials"])


class ProviderCredentialCreate(BaseModel):
    """Request to create/update user provider credential."""

    provider_name: str = Field(..., description="Provider name (anthropic, openai, etc)")
    api_key: str = Field(..., description="API key for the provider")
    base_url: str | None = Field(None, description="Optional base URL (for custom_openai, ollama)")
    additional_settings: Dict[str, str] | None = Field(None, description="Additional provider settings")


class ProviderCredentialResponse(BaseModel):
    """Response with provider credential info (redacted)."""

    id: UUID
    provider_name: str
    has_api_key: bool
    has_base_url: bool
    created_at: str
    updated_at: str


class ProviderCredentialsListResponse(BaseModel):
    """List of user's provider credentials."""

    credentials: List[ProviderCredentialResponse]


def _redact_api_key(api_key: str) -> str:
    """Redact API key for logging/display."""
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:4]}...{api_key[-4:]}"


@router.post(
    "",
    response_model=ProviderCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
@with_error_handling(
    category=ErrorCategory.SECRETS,
    operation="create_user_provider_credential",
)
async def create_or_update_credential(
    request: ProviderCredentialCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
) -> ProviderCredentialResponse:
    """Create or update a user's provider credential.

    The credential is stored encrypted with USER scope, accessible only by
    the owner. If a credential for the provider already exists, it is updated.
    """
    # Build encrypted value as JSON
    credential_data = {
        "api_key": request.api_key,
    }
    if request.base_url:
        credential_data["base_url"] = request.base_url
    if request.additional_settings:
        credential_data.update(request.additional_settings)

    # Encrypt the credential data (stored as JSON)
    secrets_service = SecretsService()
    encrypted_value = secrets_service.cipher.encrypt(
        json.dumps(credential_data).encode()
    ).decode()

    # Check if credential already exists
    secret_name = f"provider_credential_{request.provider_name}"
    stmt = select(Secret).where(
        Secret.owner_id == user_id,
        Secret.name == secret_name,
        Secret.scope == SecretScope.USER.value,
        Secret.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        # Update existing credential
        existing.encrypted_value = encrypted_value
        existing.type = SecretType.API_KEY.value
        logger.info(
            "Updated provider credential for user %s, provider %s",
            user_id,
            request.provider_name,
        )
    else:
        # Create new credential
        secret = Secret(
            owner_id=user_id,
            name=secret_name,
            type=SecretType.API_KEY.value,
            scope=SecretScope.USER.value,
            encrypted_value=encrypted_value,
            description=f"API credentials for {request.provider_name}",
        )
        db.add(secret)
        logger.info(
            "Created provider credential for user %s, provider %s",
            user_id,
            request.provider_name,
        )

    await db.commit()

    if existing:
        final_secret = existing
    else:
        await db.refresh(secret)
        final_secret = secret

    return ProviderCredentialResponse(
        id=final_secret.id,
        provider_name=request.provider_name,
        has_api_key=True,
        has_base_url=request.base_url is not None,
        created_at=final_secret.created_at.isoformat() if hasattr(final_secret, "created_at") else "",
        updated_at=final_secret.updated_at.isoformat() if hasattr(final_secret, "updated_at") else "",
    )


@router.get(
    "",
    response_model=ProviderCredentialsListResponse,
)
@with_error_handling(
    category=ErrorCategory.SECRETS,
    operation="list_user_provider_credentials",
)
async def list_credentials(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
) -> ProviderCredentialsListResponse:
    """List all provider credentials for the current user.

    Returns redacted credential info (no actual API keys).
    """
    stmt = select(Secret).where(
        Secret.owner_id == user_id,
        Secret.name.like("provider_credential_%"),
        Secret.scope == SecretScope.USER.value,
        Secret.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    secrets = result.scalars().all()

    credentials = []
    for secret in secrets:
        # Extract provider name from secret name
        provider_name = secret.name.replace("provider_credential_", "")

        # Decrypt to check what settings are present
        secrets_service = SecretsService()
        try:
            decrypted = secrets_service.cipher.decrypt(secret.encrypted_value.encode()).decode()
            credential_data = json.loads(decrypted)
            has_base_url = "base_url" in credential_data
        except Exception:
            has_base_url = False

        credentials.append(
            ProviderCredentialResponse(
                id=secret.id,
                provider_name=provider_name,
                has_api_key=True,
                has_base_url=has_base_url,
                created_at=secret.created_at.isoformat() if hasattr(secret, "created_at") else "",
                updated_at=secret.updated_at.isoformat() if hasattr(secret, "updated_at") else "",
            )
        )

    return ProviderCredentialsListResponse(credentials=credentials)


@router.delete(
    "/{provider_name}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@with_error_handling(
    category=ErrorCategory.SECRETS,
    operation="delete_user_provider_credential",
)
async def delete_credential(
    provider_name: str,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a user's provider credential.

    Soft-delete by setting is_active = False.
    """
    secret_name = f"provider_credential_{provider_name}"
    stmt = select(Secret).where(
        Secret.owner_id == user_id,
        Secret.name == secret_name,
        Secret.scope == SecretScope.USER.value,
        Secret.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    secret = result.scalar_one_or_none()

    if not secret:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider credential for {provider_name} not found",
        )

    secret.deactivate()
    await db.commit()

    logger.info(
        "Deleted provider credential for user %s, provider %s",
        user_id,
        provider_name,
    )


__all__ = ["router"]
