# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin-configured external MCP server registry (#11542).

Each record describes one third-party MCP server an admin wants AutoBot's
chat tools to reach: how to connect (stdio command, or a remote URL over
SSE/streamable-HTTP), and — for remote servers — how to authenticate. Servers
are Redis-backed (mirrors knowledge.connectors.models.ConnectorConfig's
"connector:{id}" convention, MCPServerConfig's "mcp_external_server:{id}").
Credentials are never stored inline: MCPServerConfig.secret_id references a
secret in ConnectorCredentialStore (ADR-007), the same store connectors use.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.time_utils import now_utc
from services.mcp_launcher_allowlist import validate_stdio_command

logger = get_logger(__name__)

_KEY_PREFIX = "mcp_external_server:"
_INDEX_KEY = "mcp_external_servers:index"

#: Transports an admin may configure. "http" (legacy /rpc JSON-RPC) is
#: deliberately excluded — new servers should speak streamable-HTTP.
TRANSPORTS = frozenset({"stdio", "sse", "streamable_http"})


@dataclass
class MCPServerConfig:
    """One admin-configured external MCP server."""

    server_id: str
    name: str
    transport: str  # one of TRANSPORTS
    owner_id: str
    enabled: bool = True
    created_at: datetime = field(default_factory=now_utc)
    # stdio only:
    command: str | None = None
    # sse / streamable_http only:
    url: str | None = None
    auth_type: str | None = None  # e.g. "BearerAuth" — see autobot_shared.auth.connector_auth
    secret_id: str | None = None  # ConnectorCredentialStore reference; None = no auth
    #: Non-sensitive auth fields (e.g. ApiKeyAuth's "header", BasicAuth's
    #: "username") ConnectorCredentialStore.store() returned alongside
    #: secret_id — merged back in by .load() to rebuild the full auth config.
    auth_config: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Raise ValueError/LauncherNotAllowedError on an internally inconsistent config."""
        if self.transport not in TRANSPORTS:
            raise ValueError(f"transport must be one of {sorted(TRANSPORTS)}, got {self.transport!r}")
        if self.transport == "stdio":
            if not self.command:
                raise ValueError("stdio server requires a command")
            validate_stdio_command(self.command)
        else:
            if not self.url:
                raise ValueError(f"{self.transport} server requires a url")

    def to_server_uri(self) -> str:
        """Return the URI skills.sync.mcp_client.MCPClient/create_transport expects."""
        if self.transport == "stdio":
            return f"stdio://{self.command}"
        if self.transport == "sse":
            return self.url if self.url.startswith("sse://") else "sse://" + self.url.split("://", 1)[-1]
        # streamable_http
        if self.url.startswith(("streamable-http://", "streamable-https://")):
            return self.url
        scheme = "streamable-https" if self.url.startswith("https://") else "streamable-http"
        return f"{scheme}://" + self.url.split("://", 1)[-1]


def _to_redis_dict(cfg: MCPServerConfig) -> dict[str, Any]:
    data = asdict(cfg)
    data["created_at"] = cfg.created_at.isoformat()
    return data


def _from_redis_dict(data: dict[str, Any]) -> MCPServerConfig:
    data = dict(data)
    data["created_at"] = datetime.fromisoformat(data["created_at"])
    return MCPServerConfig(**data)


class MCPExternalServerStore(AsyncRedisClientMixin):
    """Redis-backed CRUD for admin-configured external MCP servers."""

    _redis_database = "main"

    async def create(self, cfg: MCPServerConfig) -> None:
        """Persist a new server config. Raises ValueError if server_id already exists."""
        redis = await self._get_redis()
        existing = await redis.get(_KEY_PREFIX + cfg.server_id)
        if existing is not None:
            raise ValueError(f"server_id {cfg.server_id!r} already exists")
        await redis.set(_KEY_PREFIX + cfg.server_id, json.dumps(_to_redis_dict(cfg), ensure_ascii=False))
        await redis.sadd(_INDEX_KEY, cfg.server_id)

    async def get(self, server_id: str) -> MCPServerConfig | None:
        """Return the server config, or None when it does not exist."""
        redis = await self._get_redis()
        raw = await redis.get(_KEY_PREFIX + server_id)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return _from_redis_dict(json.loads(raw))

    async def list(self) -> list[MCPServerConfig]:
        """Return every configured server, in no particular order."""
        redis = await self._get_redis()
        ids = await redis.smembers(_INDEX_KEY)
        servers: list[MCPServerConfig] = []
        for raw_id in ids:
            server_id = raw_id.decode("utf-8") if isinstance(raw_id, bytes) else raw_id
            cfg = await self.get(server_id)
            if cfg is not None:
                servers.append(cfg)
        return servers

    async def update(self, cfg: MCPServerConfig) -> None:
        """Overwrite an existing server config. Raises LookupError if it does not exist."""
        redis = await self._get_redis()
        existing = await redis.get(_KEY_PREFIX + cfg.server_id)
        if existing is None:
            raise LookupError(f"server_id {cfg.server_id!r} not found")
        await redis.set(_KEY_PREFIX + cfg.server_id, json.dumps(_to_redis_dict(cfg), ensure_ascii=False))

    async def delete(self, server_id: str) -> None:
        """Remove a server config. Idempotent — deleting an absent id is not an error."""
        redis = await self._get_redis()
        await redis.delete(_KEY_PREFIX + server_id)
        await redis.srem(_INDEX_KEY, server_id)


get_mcp_external_server_store = lazy_singleton(MCPExternalServerStore)
