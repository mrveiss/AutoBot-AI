# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Plugin Capability System

Capability-based security for plugins: declaration, enforcement, and audit logging.

Issue #9049 - Plugin capability manifest system.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)


class Capability(str, Enum):
    """Plugin capabilities that must be declared in the manifest.

    Each capability grants access to a specific AutoBot subsystem or resource.
    Plugins must declare all required capabilities in plugin.json.
    """

    # Knowledge Base access
    KB_READ = "kb:read"
    KB_WRITE = "kb:write"
    KB_ADMIN = "kb:admin"

    # LLM/AI access
    LLM_CALL = "llm:call"
    LLM_EMBEDDING = "llm:embedding"
    LLM_FINE_TUNE = "llm:fine_tune"

    # Filesystem access
    FS_READ = "filesystem:read"
    FS_WRITE = "filesystem:write"
    FS_DELETE = "filesystem:delete"

    # Network access
    NETWORK_OUTBOUND = "network:outbound"
    NETWORK_INBOUND = "network:inbound"

    # Database access
    DB_READ = "database:read"
    DB_WRITE = "database:write"
    DB_ADMIN = "database:admin"

    # Agent/task access
    AGENT_READ = "agent:read"
    AGENT_EXECUTE = "agent:execute"
    AGENT_ADMIN = "agent:admin"

    # System access
    SYSTEM_ENV = "system:env"
    SYSTEM_PROCESS = "system:process"
    SYSTEM_ADMIN = "system:admin"

    # Redis access
    REDIS_READ = "redis:read"
    REDIS_WRITE = "redis:write"

    # Workflow access
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_EXECUTE = "workflow:execute"


class TrustTier(str, Enum):
    """Plugin trust tiers for community marketplace.

    Determines default capability permissions and operator warnings.
    """

    OFFICIAL = "official"  # Built by AutoBot core team
    VERIFIED = "verified"  # Reviewed and approved by AutoBot team
    COMMUNITY = "community"  # Community-submitted, unverified
    UNVERIFIED = "unverified"  # Newly uploaded, not yet reviewed


class CapabilityError(Exception):
    """Raised when a plugin attempts an undeclared capability."""

    def __init__(self, plugin_name: str, capability: Capability, message: str = ""):
        self.plugin_name = plugin_name
        self.capability = capability
        self.message = message or f"Plugin '{plugin_name}' lacks capability '{capability.value}'"
        super().__init__(self.message)


@dataclass
class CapabilityContext:
    """Context for capability usage (passed to audit log)."""

    plugin_name: str
    capability: Capability
    granted: bool
    timestamp: datetime
    operation: str  # e.g. "kb_query", "http_get", "llm_chat"
    metadata: Dict[str, Any]  # operation-specific details


class CapabilityChecker:
    """Enforces capability declarations and logs usage.

    Singleton service that validates plugin capability usage at runtime
    and records every capability invocation to an audit log.

    Issue #9049.
    """

    _instance: Optional[CapabilityChecker] = None

    def __new__(cls) -> CapabilityChecker:
        """Ensure singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._granted_capabilities: Dict[str, List[Capability]] = {}
            cls._logger = get_logger(__name__)
        return cls._instance

    def grant_capabilities(
        self,
        plugin_name: str,
        capabilities: List[Capability],
    ) -> None:
        """Grant capabilities to a plugin after operator approval.

        Args:
            plugin_name: Plugin identifier
            capabilities: List of capabilities to grant
        """
        self._granted_capabilities[plugin_name] = capabilities
        self._logger.info(
            "Granted capabilities to plugin '%s': %s",
            plugin_name,
            [cap.value for cap in capabilities],
        )

    def revoke_capabilities(self, plugin_name: str) -> None:
        """Revoke all capabilities for a plugin (on unload/uninstall).

        Args:
            plugin_name: Plugin identifier
        """
        if plugin_name in self._granted_capabilities:
            del self._granted_capabilities[plugin_name]
            self._logger.info("Revoked all capabilities for plugin '%s'", plugin_name)

    async def check(
        self,
        plugin_name: str,
        capability: Capability,
        operation: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Check if a plugin has a required capability and log the usage.

        Args:
            plugin_name: Plugin identifier
            capability: Required capability
            operation: Operation being performed (for audit log)
            metadata: Additional context for audit log

        Raises:
            CapabilityError: If the plugin lacks the required capability
        """
        granted_caps = self._granted_capabilities.get(plugin_name, [])
        granted = capability in granted_caps

        # Record audit log entry
        context = CapabilityContext(
            plugin_name=plugin_name,
            capability=capability,
            granted=granted,
            timestamp=datetime.now(timezone.utc),
            operation=operation,
            metadata=metadata or {},
        )
        await self._log_capability_use(context)

        # Enforce capability requirement
        if not granted:
            raise CapabilityError(plugin_name, capability)

    async def _log_capability_use(self, context: CapabilityContext) -> None:
        """Write capability usage to Redis-backed audit log.

        Audit log format: Redis stream at `plugin:capability:audit`
        Each entry includes: timestamp, plugin, capability, granted, operation, metadata.

        Args:
            context: Capability usage context
        """
        try:
            redis = await get_async_redis_client(database="main")
            if redis is None:
                self._logger.warning("Redis unavailable for capability audit log")
                return

            audit_entry = {
                "timestamp": context.timestamp.isoformat(),
                "plugin_name": context.plugin_name,
                "capability": context.capability.value,
                "granted": str(context.granted),
                "operation": context.operation,
                "metadata": str(context.metadata),
            }

            await redis.xadd(
                "plugin:capability:audit",
                audit_entry,  # type: ignore[arg-type]
                maxlen=10000,  # Keep last 10k audit entries
            )

            if not context.granted:
                self._logger.warning(
                    "Capability violation: plugin '%s' attempted '%s' without permission",
                    context.plugin_name,
                    context.capability.value,
                )
        except Exception as exc:
            self._logger.error(
                "Failed to log capability usage: %s",
                exc,
                exc_info=True,
            )

    def get_granted_capabilities(self, plugin_name: str) -> List[Capability]:
        """Get all capabilities granted to a plugin.

        Args:
            plugin_name: Plugin identifier

        Returns:
            List of granted capabilities
        """
        return self._granted_capabilities.get(plugin_name, [])

    def clear(self) -> None:
        """Clear all granted capabilities (for testing)."""
        self._granted_capabilities.clear()
