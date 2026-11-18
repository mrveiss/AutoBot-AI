# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLM-provider sign-in settings: ``config.llm_oauth`` (#19241).

Operator configuration for "Sign in with {provider}" on the LLM providers.
Every field reads ``AUTOBOT_LLM_OAUTH_<FIELD>`` (e.g.
``AUTOBOT_LLM_OAUTH_HUGGINGFACE_CLIENT_ID``). The OAuth *client secret* is NOT a
setting here: it lives in the System vault under the name
``AUTOBOT_LLM_OAUTH_<PROVIDER>_CLIENT_SECRET`` and is resolved through
``services.provider_key_vault`` (the canonical secrets manager).

Endpoint defaults ship only where they are the provider's documented public
OAuth endpoints. HuggingFace's come from its OpenID discovery document
(https://huggingface.co/.well-known/openid-configuration). No client id ships.
It lives in its own module so ``ssot_config`` does not grow past its size ceiling.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from autobot_shared.paths import project_root
from autobot_shared.secret_redaction import RedactedReprMixin

_HF = "https://huggingface.co/oauth"


class LlmOAuthConfig(RedactedReprMixin, BaseSettings):
    """Per-provider OAuth endpoints, scopes and client id for LLM sign-in (#19241).

    Empty URL → that flow is unavailable. Empty client id → the provider is
    shown as "not configured". Scopes are space-separated. An empty revoke URL
    makes a disconnect local-only (the vault copy is deleted, the grant is not).
    """

    model_config = SettingsConfigDict(
        env_file=str(project_root() / ".env"),
        env_file_encoding="utf-8",
        env_prefix="AUTOBOT_LLM_OAUTH_",
        extra="ignore",
    )

    openai_client_id: str = Field(default="", description="OAuth client id registered with OpenAI")
    openai_authorize_url: str = Field(default="", description="OpenAI authorization endpoint")
    openai_token_url: str = Field(default="", description="OpenAI token endpoint")
    openai_device_url: str = Field(default="", description="OpenAI device-authorization endpoint")
    openai_scopes: str = Field(default="openid", description="OpenAI scopes, space-separated")
    openai_revoke_url: str = Field(default="", description="OpenAI RFC 7009 revocation endpoint (optional)")

    anthropic_client_id: str = Field(default="", description="OAuth client id registered with Anthropic")
    anthropic_authorize_url: str = Field(default="", description="Anthropic authorization endpoint")
    anthropic_token_url: str = Field(default="", description="Anthropic token endpoint")
    anthropic_device_url: str = Field(default="", description="Anthropic device-authorization endpoint")
    anthropic_scopes: str = Field(default="openid", description="Anthropic scopes, space-separated")
    anthropic_revoke_url: str = Field(default="", description="Anthropic RFC 7009 revocation endpoint (optional)")

    huggingface_client_id: str = Field(default="", description="OAuth client id registered with HuggingFace")
    huggingface_authorize_url: str = Field(default=f"{_HF}/authorize", description="HuggingFace authorization endpoint")
    huggingface_token_url: str = Field(default=f"{_HF}/token", description="HuggingFace token endpoint")
    huggingface_device_url: str = Field(default=f"{_HF}/device", description="HuggingFace device endpoint")
    huggingface_scopes: str = Field(default="openid inference-api", description="HuggingFace scopes, space-separated")
    # No default: HuggingFace's discovery document publishes no revocation_endpoint.
    huggingface_revoke_url: str = Field(default="", description="HuggingFace RFC 7009 revocation endpoint")
