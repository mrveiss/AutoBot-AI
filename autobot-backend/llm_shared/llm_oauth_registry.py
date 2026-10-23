# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Server-side registry of the LLM providers that support "Sign in with" (#19241).

Each provider is an ``oauth_flow.OAuthProvider`` built at call time from
``config.llm_oauth`` (endpoints, scopes, client id), so an operator's setting
change applies without a restart. The OAuth client secret is optional (a
public PKCE client has none) and comes only from the System vault via
``services.provider_key_vault.resolve_provider_key`` -- never from the client
and never from an ad-hoc env read. Nothing in here is ever returned to a
browser except setting NAMES.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from autobot_shared.ssot_config import config
from knowledge.connectors.oauth_flow import OAuthProvider

#: Provider name -> display label. The names match ``ProviderType`` values.
LLM_OAUTH_PROVIDER_LABELS: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "huggingface": "HuggingFace",
}

FLOW_REDIRECT = "redirect"
FLOW_DEVICE = "device"
_ENV_PREFIX = "AUTOBOT_LLM_OAUTH_"


class UnknownProviderError(KeyError):
    """The name is not a sign-in-capable LLM provider."""


class ProviderNotConfiguredError(ValueError):
    """The provider exists but the operator has not configured the requested flow."""


@dataclass(frozen=True)
class LlmOAuthClient:
    """A resolved provider: endpoints + the operator's client credentials. Never serialised."""

    provider: OAuthProvider
    client_id: str
    client_secret: str = dataclasses.field(default="", repr=False)


def setting_env_name(provider_name: str, field: str) -> str:
    """The env/setting name an operator fills, e.g. ``AUTOBOT_LLM_OAUTH_OPENAI_CLIENT_ID``."""
    return f"{_ENV_PREFIX}{provider_name.upper()}_{field.upper()}"


def client_secret_vault_name(provider_name: str) -> str:
    """System-vault secret name holding the provider's OAuth client secret."""
    return setting_env_name(provider_name, "client_secret")


def _setting(provider_name: str, field: str) -> str:
    return str(getattr(config.llm_oauth, f"{provider_name}_{field}", "") or "").strip()


def build_provider(provider_name: str) -> OAuthProvider:
    """Return the configured ``OAuthProvider`` for *provider_name*; raises UnknownProviderError."""
    if provider_name not in LLM_OAUTH_PROVIDER_LABELS:
        raise UnknownProviderError(f"unknown sign-in provider: {provider_name!r}")
    return OAuthProvider(
        name=provider_name,
        authorize_url=_setting(provider_name, "authorize_url"),
        token_url=_setting(provider_name, "token_url"),
        client_id_setting=f"{provider_name}_client_id",
        client_secret_setting=client_secret_vault_name(provider_name),
        default_scopes=tuple(_setting(provider_name, "scopes").split()),
        device_authorization_url=_setting(provider_name, "device_url"),
        revocation_url=_setting(provider_name, "revoke_url"),
    )


def available_flows(provider: OAuthProvider) -> list[str]:
    """The flows whose endpoints are configured (redirect first)."""
    flows = []
    if provider.authorize_url and provider.token_url:
        flows.append(FLOW_REDIRECT)
    if provider.device_authorization_url and provider.token_url:
        flows.append(FLOW_DEVICE)
    return flows


def missing_settings(provider: OAuthProvider) -> list[str]:
    """Setting names an operator must still fill before any flow works."""
    missing = []
    if not _setting(provider.name, "client_id"):
        missing.append(setting_env_name(provider.name, "client_id"))
    if not available_flows(provider):
        missing += [setting_env_name(provider.name, f) for f in ("authorize_url", "token_url")]
    return missing


def _resolve_client_secret(provider_name: str) -> str:
    from services.provider_key_vault import resolve_provider_key  # noqa: PLC0415  # heavy import

    # Vault only: "" config value means there is no environment fallback.
    return resolve_provider_key(client_secret_vault_name(provider_name), "")


def resolve_client(provider_name: str, flow: str | None = None) -> LlmOAuthClient:
    """Resolve *provider_name* (and, if given, *flow*) to a usable client.

    Raises UnknownProviderError, or ProviderNotConfiguredError naming the missing
    settings. ``VaultKeyUnavailableError`` propagates when the vault holds the
    secret but cannot be read.
    """
    provider = build_provider(provider_name)
    missing = missing_settings(provider)
    if missing:
        raise ProviderNotConfiguredError(f"{provider_name} sign-in is not configured; set {', '.join(missing)}")
    if flow is not None and flow not in available_flows(provider):
        raise ProviderNotConfiguredError(f"{provider_name} has no {flow} sign-in endpoint configured")
    secret = _resolve_client_secret(provider_name)
    # A public PKCE client authenticates with client_id only (#13630 deviation field).
    method = "client_secret_post" if secret else "none"
    provider = dataclasses.replace(provider, token_endpoint_auth_method=method)
    return LlmOAuthClient(provider=provider, client_id=_setting(provider_name, "client_id"), client_secret=secret)


def describe_providers() -> list[dict]:
    """The public listing for ``GET /api/llm-auth/providers`` -- names, flows, status; no values."""
    listing = []
    for name, label in LLM_OAUTH_PROVIDER_LABELS.items():
        provider = build_provider(name)
        missing = missing_settings(provider)
        flows = available_flows(provider)
        listing.append(
            {"name": name, "label": label, "flows": flows, "configured": not missing, "missing_settings": missing}
        )
    return listing


__all__ = [
    "FLOW_DEVICE",
    "FLOW_REDIRECT",
    "LLM_OAUTH_PROVIDER_LABELS",
    "LlmOAuthClient",
    "ProviderNotConfiguredError",
    "UnknownProviderError",
    "available_flows",
    "build_provider",
    "client_secret_vault_name",
    "describe_providers",
    "missing_settings",
    "resolve_client",
    "setting_env_name",
]
