# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bridge an MCPServerConfig's stored credential to MCPClient's extra_headers (#11542).

Reuses ConnectorCredentialStore (ADR-007) — the same encrypted-credential
store connectors use — rather than a second credential path. A credential is
decrypted only at connection time, in resolve_extra_headers_for_server();
MCPServerConfig itself never carries plaintext secrets.
"""

from __future__ import annotations

import base64

import autobot_shared.auth.connector_auth as connector_auth
from autobot_shared.logging_manager import get_logger
from services.mcp_external_servers import MCPServerConfig

logger = get_logger(__name__)

#: Auth types this module knows how to turn into headers directly from
#: decrypted fields. OAuthRefreshAuth is deliberately absent — it needs a
#: token-refresh round trip (ConnectorCredentialStore.get_access_token), not
#: a static header built from its stored fields.
_HEADER_AUTH_TYPES = frozenset({"BearerAuth", "ApiKeyAuth", "BasicAuth"})


def resolve_auth_class(auth_type: str) -> type | None:
    """Resolve an auth_type name (e.g. "BearerAuth") to its dataclass, or None.

    Looks up autobot_shared.auth.connector_auth's public dataclasses by name.
    Once #16444 merges, autobot_shared.auth.connector_auth.resolve_auth_type()
    is the canonical home for this lookup and this function should delegate
    to it instead of duplicating the resolution.
    """
    cls = getattr(connector_auth, auth_type, None)
    if isinstance(cls, type) and hasattr(cls, "__sensitive_fields__"):
        return cls
    return None


def build_auth_headers(auth_type: str, full_config: dict) -> dict[str, str]:
    """Build the HTTP headers implied by a resolved, decrypted auth config.

    ``full_config`` is the merge of a credential's non-sensitive fields and
    its decrypted sensitive fields — i.e. ConnectorCredentialStore.load()'s
    return value.
    """
    if auth_type == "BearerAuth":
        return {"Authorization": f"Bearer {full_config['token']}"}
    if auth_type == "ApiKeyAuth":
        header = full_config.get("header", "X-Api-Key")
        return {header: full_config["key"]}
    if auth_type == "BasicAuth":
        raw = f"{full_config['username']}:{full_config['password']}".encode("utf-8")
        return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}
    raise ValueError(f"build_auth_headers does not support auth_type: {auth_type!r}")


async def resolve_extra_headers_for_server(cfg: MCPServerConfig) -> dict[str, str]:
    """Return the headers to send when connecting to *cfg*'s server (#11542).

    Returns {} for a server with no configured credential. Decrypts the
    stored credential fresh on every call — nothing here caches plaintext.
    """
    if not cfg.secret_id or not cfg.auth_type:
        return {}

    from knowledge.connectors.credential_store import get_credential_store  # noqa: PLC0415

    store = get_credential_store()

    if cfg.auth_type == "OAuthRefreshAuth":
        access_token = await store.get_access_token(cfg.secret_id, cfg.owner_id)
        return {"Authorization": f"Bearer {access_token}"}

    if cfg.auth_type not in _HEADER_AUTH_TYPES:
        raise ValueError(f"unsupported auth_type: {cfg.auth_type!r}")

    auth_cls = resolve_auth_class(cfg.auth_type)
    if auth_cls is None:
        raise ValueError(f"could not resolve auth_type: {cfg.auth_type!r}")

    full_config = await store.load(cfg.secret_id, cfg.auth_config, auth_cls, cfg.owner_id)
    return build_auth_headers(cfg.auth_type, full_config)
