# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Secrets Integration Service

Provides automatic secret retrieval and injection for agents based on their type
and requirements. Supports both general and chat-scoped secrets with proper
access control.

Related Issues:
- #211 - Secrets Management System - Missing Features
"""

import threading
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Set

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.status_enums import SecretType
from services.secrets_service import SecretsService, get_secrets_service

logger = get_logger(__name__)


# #13846: ``SecretRequirement`` used to be declared here — six members copied
# verbatim from ``SecretType``, down to the identical ``# nosec B105`` and
# ``# nosemgrep`` comments, plus ``ANY``. It had no ``OAUTH_REFRESH_TOKEN``, so
# an agent that authenticates by OAuth could only be described as ``ANY``: the
# blanket "every available secret" grant standing in for the most specific
# requirement there is. The requirement vocabulary is now the canonical
# ``SecretType`` itself, wildcard included, so a mapping can name the exact
# kind it needs.


@dataclass
class AgentSecretMapping:
    """Defines which secret types an agent needs.

    ``required_types`` / ``optional_types`` hold :class:`SecretType` members —
    not bare strings. A typo used to produce a set that matched no secret and
    reported success; an unknown member is now impossible to construct.
    ``SecretType.ANY`` is legal here and means "any available secret"; it is
    resolved by :meth:`SecretType.expand` before any lookup.
    """

    agent_type: str
    required_types: Set[SecretType] = field(default_factory=set)
    optional_types: Set[SecretType] = field(default_factory=set)
    auto_inject: bool = True  # Whether to automatically inject secrets
    description: str = ""


# Agent-to-secret-type mappings (Issue #211)
# Define which agents need which secret types
AGENT_SECRET_MAPPINGS: Dict[str, AgentSecretMapping] = {
    # SSH/Terminal agents need SSH keys
    "interactive_terminal": AgentSecretMapping(
        agent_type="interactive_terminal",
        required_types=set(),
        optional_types={SecretType.SSH_KEY, SecretType.PASSWORD},
        auto_inject=True,
        description="Terminal agent may use SSH keys for remote connections",
    ),
    "system_command": AgentSecretMapping(
        agent_type="system_command",
        required_types=set(),
        optional_types={SecretType.SSH_KEY, SecretType.PASSWORD, SecretType.API_KEY},
        auto_inject=True,
        description="System command agent for remote command execution",
    ),
    # Research/API agents need API keys
    "research": AgentSecretMapping(
        agent_type="research",
        required_types=set(),
        optional_types={SecretType.API_KEY, SecretType.TOKEN},
        auto_inject=True,
        description="Research agent may need API keys for external services",
    ),
    "web_research": AgentSecretMapping(
        agent_type="web_research",
        required_types=set(),
        optional_types={SecretType.API_KEY, SecretType.TOKEN},
        auto_inject=True,
        description="Web research agent for API-based searches",
    ),
    "advanced_web_research": AgentSecretMapping(
        agent_type="advanced_web_research",
        required_types=set(),
        optional_types={SecretType.API_KEY, SecretType.TOKEN},
        auto_inject=True,
        description="Advanced research with external API support",
    ),
    # Security agents need various credentials
    "security_scanner": AgentSecretMapping(
        agent_type="security_scanner",
        required_types=set(),
        optional_types={SecretType.SSH_KEY, SecretType.PASSWORD, SecretType.API_KEY, SecretType.TOKEN},
        auto_inject=True,
        description="Security scanner may need credentials for authenticated scans",
    ),
    "network_discovery": AgentSecretMapping(
        agent_type="network_discovery",
        required_types=set(),
        optional_types={SecretType.SSH_KEY, SecretType.PASSWORD},
        auto_inject=True,
        description="Network discovery agent for authenticated scanning",
    ),
    # Knowledge/RAG agents may need database credentials
    "rag": AgentSecretMapping(
        agent_type="rag",
        required_types=set(),
        optional_types={SecretType.DATABASE_URL, SecretType.API_KEY},
        auto_inject=True,
        description="RAG agent for knowledge retrieval",
    ),
    "knowledge_retrieval": AgentSecretMapping(
        agent_type="knowledge_retrieval",
        required_types=set(),
        optional_types={SecretType.DATABASE_URL, SecretType.API_KEY},
        auto_inject=True,
        description="Knowledge retrieval agent",
    ),
    # Chat/General agents
    "chat": AgentSecretMapping(
        agent_type="chat",
        required_types=set(),
        optional_types=set(),  # Chat agent doesn't directly use secrets
        auto_inject=False,
        description="Chat agent - secrets accessed on demand",
    ),
    "classification": AgentSecretMapping(
        agent_type="classification",
        required_types=set(),
        optional_types=set(),
        auto_inject=False,
        description="Classification agent - no secrets needed",
    ),
}


class AgentSecretsIntegration:
    """
    Service for integrating secrets with agent workflows.

    Provides automatic secret retrieval based on agent type and chat context,
    with proper access control and caching for performance.
    """

    def __init__(self, secrets_service: SecretsService | None = None) -> None:
        """Initialize agent secrets integration.

        Args:
            secrets_service: Optional SecretsService instance. Uses singleton if not provided.
        """
        self._secrets_service = secrets_service
        self._cache: Dict[str, Dict[str, str]] = {}
        self._cache_lock = threading.Lock()
        self._custom_mappings: Dict[str, AgentSecretMapping] = {}
        logger.info("AgentSecretsIntegration initialized")

    @property
    def secrets_service(self) -> SecretsService:
        """Get secrets service (lazy initialization)."""
        if self._secrets_service is None:
            self._secrets_service = get_secrets_service()
        return self._secrets_service

    def get_agent_mapping(self, agent_type: str) -> AgentSecretMapping | None:
        """Get secret mapping for an agent type.

        Args:
            agent_type: The type of agent to get mapping for

        Returns:
            AgentSecretMapping if found, None otherwise
        """
        # Check custom mappings first
        if agent_type in self._custom_mappings:
            return self._custom_mappings[agent_type]
        return AGENT_SECRET_MAPPINGS.get(agent_type)

    def register_agent_mapping(self, mapping: AgentSecretMapping) -> None:
        """Register a custom agent-to-secret mapping.

        Args:
            mapping: The AgentSecretMapping to register
        """
        self._custom_mappings[mapping.agent_type] = mapping
        logger.info("Registered secret mapping for agent: %s", mapping.agent_type)

    @staticmethod
    def _coerce_types(values: "Iterable[SecretType | str]") -> Set[SecretType]:
        """Accept members or their wire strings; reject anything else loudly.

        #13846: callers outside this module pass raw strings. A string that
        names no kind used to become a filter that matched nothing and
        returned an empty result — a silent miss dressed as "no secrets".
        """
        coerced: Set[SecretType] = set()
        for value in values:
            coerced.add(value if isinstance(value, SecretType) else SecretType(value))
        return coerced

    def _determine_types_to_fetch(
        self,
        mapping: AgentSecretMapping,
        secret_types: "List[SecretType | str] | None",
    ) -> Set[SecretType]:
        """Determine which secret types to fetch based on mapping and overrides (Issue #665: extracted helper).

        #13846: ``SecretType.ANY`` is expanded here into the concrete taxonomy.
        Left unexpanded it would be looked up as the literal type "any", which
        no stored secret carries — so the broadest possible requirement used to
        fetch the narrowest possible result: nothing.
        """
        if secret_types:
            return set(SecretType.expand(self._coerce_types(secret_types)))
        requested = mapping.required_types | mapping.optional_types
        return set(SecretType.expand(requested))

    async def _fetch_and_merge_secrets(
        self,
        types_to_fetch: Set[SecretType],
        agent_type: str,
        chat_id: str | None,
        include_general: bool,
        accessed_by: str | None,
    ) -> Dict[str, str]:
        """Fetch chat and general secrets and merge with priority (Issue #665: extracted helper)."""
        agent_secrets: Dict[str, str] = {}
        accessor = accessed_by or f"agent:{agent_type}"

        # Fetch chat-scoped secrets first (higher priority)
        if chat_id:
            chat_secrets = await self._fetch_secrets_by_types(
                types_to_fetch, scope="chat", chat_id=chat_id, accessed_by=accessor
            )
            agent_secrets.update(chat_secrets)

        # Fetch general secrets
        if include_general:
            general_secrets = await self._fetch_secrets_by_types(
                types_to_fetch, scope="general", chat_id=None, accessed_by=accessor
            )
            # Only add general secrets that don't override chat secrets
            for name, value in general_secrets.items():
                if name not in agent_secrets:
                    agent_secrets[name] = value

        return agent_secrets

    async def get_secrets_for_agent(
        self,
        agent_type: str,
        chat_id: str | None = None,
        include_general: bool = True,
        secret_types: "List[SecretType | str] | None" = None,
        accessed_by: str | None = None,
    ) -> Dict[str, str]:
        """Get relevant secrets for a specific agent type.

        Retrieves secrets based on the agent's declared requirements and the
        current chat context. Supports both chat-scoped and general secrets.

        Args:
            agent_type: Type of agent requesting secrets
            chat_id: Optional chat ID for chat-scoped secrets
            include_general: Whether to include general (non-chat-scoped) secrets
            secret_types: Optional list of specific secret types to retrieve
            accessed_by: Identifier for audit logging

        Returns:
            Dictionary mapping secret names to their decrypted values
        """
        mapping = self.get_agent_mapping(agent_type)
        if mapping is None:
            logger.debug("No secret mapping found for agent type: %s", agent_type)
            return {}

        if not mapping.auto_inject and secret_types is None:
            logger.debug("Agent %s has auto_inject disabled", agent_type)
            return {}

        types_to_fetch = self._determine_types_to_fetch(mapping, secret_types)
        if not types_to_fetch:
            return {}

        agent_secrets = await self._fetch_and_merge_secrets(
            types_to_fetch, agent_type, chat_id, include_general, accessed_by
        )

        logger.info(
            "Retrieved %d secrets for agent %s (chat_id=%s)",
            len(agent_secrets),
            agent_type,
            chat_id[:8] if chat_id else "None",
        )

        return agent_secrets

    async def _fetch_secrets_by_types(
        self,
        secret_types: Set[SecretType],
        scope: str,
        chat_id: str | None,
        accessed_by: str | None,
    ) -> Dict[str, str]:
        """Fetch secrets filtered by types.

        Args:
            secret_types: Set of secret types to fetch
            scope: Secret scope ('general' or 'chat')
            chat_id: Chat ID for chat-scoped secrets
            accessed_by: Identifier for audit logging

        Returns:
            Dictionary mapping secret names to decrypted values
        """
        secrets_dict: Dict[str, str] = {}

        for secret_type in secret_types:
            secrets = self.secrets_service.list_secrets(
                scope=scope,
                chat_id=chat_id,
                # #14944: ``.value``, never the member. ``SecretType`` is a str
                # subclass, but str() of a member is "SecretType.API_KEY" and
                # this value reaches a SQL parameter.
                secret_type=secret_type.value,
                include_expired=False,
            )

            for secret in secrets:
                # Get the full secret with decrypted value
                full_secret = self.secrets_service.get_secret(
                    secret_id=secret["id"],
                    include_value=True,
                    accessed_by=accessed_by,
                )
                if full_secret and "value" in full_secret:
                    secrets_dict[full_secret["name"]] = full_secret["value"]

        return secrets_dict

    def _fetch_ssh_keys_by_scope(
        self,
        scope: str,
        chat_id: str | None = None,
    ) -> List[Dict[str, str]]:
        """Fetch SSH keys from secrets service for a specific scope. Issue #620.

        Args:
            scope: Secret scope ('chat' or 'general')
            chat_id: Chat ID for chat-scoped secrets (required if scope='chat')

        Returns:
            List of SSH key dictionaries with id, name, value, scope, description
        """
        ssh_keys = []
        keys = self.secrets_service.list_secrets(  # nosec B106  # secret type filter
            scope=scope,
            chat_id=chat_id,
            secret_type=SecretType.SSH_KEY.value,
        )
        for key in keys:
            full_key = self.secrets_service.get_secret(
                secret_id=key["id"],
                include_value=True,
                accessed_by="terminal_session",
            )
            if full_key and "value" in full_key:
                ssh_keys.append(
                    {
                        "id": full_key["id"],
                        "name": full_key["name"],
                        "value": full_key["value"],
                        "scope": scope,
                        "description": full_key.get("description", ""),
                    }
                )
        return ssh_keys

    async def get_ssh_keys_for_terminal(
        self,
        chat_id: str | None = None,
        include_general: bool = True,
    ) -> List[Dict[str, str]]:
        """Get SSH keys specifically for terminal sessions.

        Args:
            chat_id: Optional chat ID for chat-scoped keys
            include_general: Whether to include general SSH keys

        Returns:
            List of SSH key dictionaries with 'name' and 'value' keys

        Issue #620: Refactored to use _fetch_ssh_keys_by_scope helper.
        """
        ssh_keys = []

        # Get chat-scoped SSH keys (Issue #620: uses helper)
        if chat_id:
            ssh_keys.extend(self._fetch_ssh_keys_by_scope("chat", chat_id))

        # Get general SSH keys (Issue #620: uses helper)
        if include_general:
            ssh_keys.extend(self._fetch_ssh_keys_by_scope("general"))

        logger.info(
            "Retrieved %d SSH keys for terminal (chat_id=%s)",
            len(ssh_keys),
            chat_id[:8] if chat_id else "None",
        )

        return ssh_keys

    async def get_api_keys_for_service(
        self,
        service_name: str,
        chat_id: str | None = None,
    ) -> str | None:
        """Get API key for a specific service.

        Args:
            service_name: Name of the service (e.g., 'openai', 'anthropic')
            chat_id: Optional chat ID for chat-scoped keys

        Returns:
            API key value if found, None otherwise
        """
        # Try chat-scoped first
        if chat_id:
            secrets = self.secrets_service.list_secrets(  # nosec B106
                scope="chat",
                chat_id=chat_id,
                secret_type=SecretType.API_KEY.value,
            )
            for secret in secrets:
                if service_name.lower() in secret["name"].lower():
                    full_secret = self.secrets_service.get_secret(
                        secret_id=secret["id"],
                        include_value=True,
                        accessed_by=f"service:{service_name}",
                    )
                    if full_secret and "value" in full_secret:
                        return full_secret["value"]

        # Try general scope
        secrets = self.secrets_service.list_secrets(  # nosec B106  # secret type filter
            scope="general",
            secret_type=SecretType.API_KEY.value,
        )
        for secret in secrets:
            if service_name.lower() in secret["name"].lower():
                full_secret = self.secrets_service.get_secret(
                    secret_id=secret["id"],
                    include_value=True,
                    accessed_by=f"service:{service_name}",
                )
                if full_secret and "value" in full_secret:
                    return full_secret["value"]

        return None

    def get_available_secret_types(self, agent_type: str) -> Set[SecretType]:
        """Get the concrete secret kinds available to an agent.

        #13846: returns :class:`SecretType` members, and expands
        ``SecretType.ANY`` to the whole concrete taxonomy so a wildcard
        requirement reports the kinds it actually grants rather than the
        wildcard itself.

        Args:
            agent_type: Type of agent to query

        Returns:
            Set of SecretType members the agent can use
        """
        mapping = self.get_agent_mapping(agent_type)
        if mapping is None:
            return set()
        return set(SecretType.expand(mapping.required_types | mapping.optional_types))

    def is_auto_inject_enabled(self, agent_type: str) -> bool:
        """Check if auto-injection is enabled for an agent type.

        Args:
            agent_type: Type of agent to check

        Returns:
            True if auto_inject is enabled, False otherwise
        """
        mapping = self.get_agent_mapping(agent_type)
        if mapping is None:
            return False
        return mapping.auto_inject


get_agent_secrets_integration = lazy_singleton(AgentSecretsIntegration)
