# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared ChromaDB client-auth settings helper.

Issue #12513: ChromaDB (autobot-chromadb / the AI-stack chroma server) has no
server-side auth by default — any internal-network container/host could read
and write every collection. This module centralizes the client-side wiring for
CHROMA_SERVER_AUTHN_* token auth so every HttpClient construction site (sync,
async, CLI doctor) stays in sync instead of re-deriving the same settings.

Backward-compat: when AUTOBOT_CHROMADB_AUTH_TOKEN is unset (dev/local, server
auth disabled), ``chroma_client_auth_kwargs()`` returns an empty dict — callers
merge it into their ``chromadb.config.Settings(...)`` kwargs unchanged, so an
unauthenticated deployment keeps working exactly as before this issue.
"""

from __future__ import annotations

from typing import Any, Dict

from autobot_shared.ssot_config import config as _ssot_config

# Must match the server-side CHROMA_SERVER_AUTHN_PROVIDER (docker-compose.yml /
# Ansible roles/redis templates) — chromadb's token_authn module ships both the
# server and client provider classes (chromadb>=1.5.9, verified against the
# pinned version).
_CLIENT_AUTH_PROVIDER = "chromadb.auth.token_authn.TokenAuthClientProvider"


def chroma_client_auth_kwargs() -> Dict[str, Any]:
    """Return ``chromadb.config.Settings`` kwargs enabling token auth.

    Reads the shared secret from ``ssot_config.misc.chromadb_auth_token``
    (env alias ``AUTOBOT_CHROMADB_AUTH_TOKEN``). Returns an empty dict when
    the token is unset so callers merge this into ``Settings(**base, **kwargs)``
    without needing their own presence check.
    """
    token = _ssot_config.misc.chromadb_auth_token
    if not token:
        return {}
    return {
        "chroma_client_auth_provider": _CLIENT_AUTH_PROVIDER,
        "chroma_client_auth_credentials": token,
    }
