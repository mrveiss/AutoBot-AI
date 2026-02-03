# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Memory Graph - Secret Management Module

This module contains Issue #608 secret management operations:
- Secret entity creation with scoping
- Secret usage audit trail
- Secret access queries

Part of the modular autobot_memory_graph package (Issue #716).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .core import AutoBotMemoryGraphCore

logger = logging.getLogger(__name__)


class SecretManagementMixin:
    """
    Mixin class providing secret management operations.

    Issue #608: This mixin provides functionality for:
    - Secret entity creation with ownership and scoping
    - Secret usage audit trail
    - Secret access queries based on permissions
    """

    def _validate_secret_params(
        self: AutoBotMemoryGraphCore,
        secret_type: str,
        scope: str,
        session_id: Optional[str],
    ) -> None:
        """Issue #665: Validate secret creation parameters."""
        valid_secret_types = {"api_key", "token", "password", "ssh_key", "certificate"}
        valid_scopes = {"user", "session", "shared"}

        if secret_type not in valid_secret_types:
            raise ValueError(
                f"Invalid secret_type: {secret_type}. "
                f"Must be one of {valid_secret_types}"
            )
        if scope not in valid_scopes:
            raise ValueError(
                f"Invalid scope: {scope}. Must be one of {valid_scopes}"
            )
        if scope == "session" and not session_id:
            raise ValueError("session_id is required for session-scoped secrets")

    async def _create_secret_owner_relations(
        self: AutoBotMemoryGraphCore,
        owner_id: str,
        entity_id: str,
    ) -> None:
        """Issue #665: Create owner relationships for a secret entity."""
        await self.create_relation_by_id(
            from_entity_id=owner_id,
            to_entity_id=entity_id,
            relation_type="owns",
        )
        await self.create_relation_by_id(
            from_entity_id=owner_id,
            to_entity_id=entity_id,
            relation_type="has_secret",
        )

    async def _create_secret_scope_relations(
        self: AutoBotMemoryGraphCore,
        entity_id: str,
        scope: str,
        session_id: Optional[str],
        shared_with: Optional[List[str]],
    ) -> None:
        """Issue #665: Create scope-based relationships for a secret entity."""
        if scope == "session" and session_id:
            await self.create_relation_by_id(
                from_entity_id=session_id,
                to_entity_id=entity_id,
                relation_type="has_secret",
                metadata={"scope": "session"},
            )
        if scope == "shared" and shared_with:
            for shared_user_id in shared_with:
                await self.create_relation_by_id(
                    from_entity_id=entity_id,
                    to_entity_id=shared_user_id,
                    relation_type="shared_with",
                )

    async def create_secret_entity(
        self: AutoBotMemoryGraphCore,
        name: str,
        secret_type: str,
        owner_id: str,
        scope: str = "user",
        session_id: Optional[str] = None,
        shared_with: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a secret entity with ownership and scoping.

        Issue #608: Secrets can be user-scoped, session-scoped, or shared.
        Note: This does NOT store the actual secret value.

        Args:
            name: Human-readable secret name
            secret_type: Type of secret (api_key, token, password, ssh_key, certificate)
            owner_id: User ID of secret owner
            scope: Scope level (user, session, shared)
            session_id: Session ID for session-scoped secrets
            shared_with: List of user IDs for shared secrets
            metadata: Optional additional metadata

        Returns:
            Created secret entity (without the actual secret value)
        """
        self.ensure_initialized()
        self._validate_secret_params(secret_type, scope, session_id)

        try:
            secret_metadata = metadata or {}
            secret_metadata.update({
                "owner_id": owner_id,
                "secret_type": secret_type,
                "scope": scope,
                "session_id": session_id,
                "shared_with": shared_with or [],
                "usage_count": 0,
                "created_at": datetime.utcnow().isoformat(),
            })

            entity = await self.create_entity(
                entity_type="secret",
                name=name,
                observations=[f"Secret created: {secret_type} ({scope} scope)"],
                metadata=secret_metadata,
                tags=["secret", secret_type, scope],
            )

            await self._create_secret_owner_relations(owner_id, entity["id"])
            await self._create_secret_scope_relations(
                entity["id"], scope, session_id, shared_with
            )

            logger.info("Created secret entity: %s (scope: %s)", name, scope)
            return entity

        except Exception as e:
            logger.error("Failed to create secret entity: %s", e)
            raise

    async def _create_secret_usage_audit(
        self: AutoBotMemoryGraphCore,
        secret_id: str,
        user_id: str,
        activity_type: str,
        activity_id: str,
    ) -> Dict[str, Any]:
        """
        Create a secret usage audit entity for tracking access.

        Issue #608: All secret usage is logged for audit trail.

        Args:
            secret_id: ID of the secret being used
            user_id: ID of the user using the secret
            activity_type: Type of activity using the secret
            activity_id: ID of the activity entity

        Returns:
            Created secret usage audit entity
        """
        try:
            audit_metadata = {
                "secret_id": secret_id,
                "user_id": user_id,
                "activity_type": activity_type,
                "activity_id": activity_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

            entity = await self.create_entity(
                entity_type="secret_usage",
                name=f"Secret Usage: {secret_id[:8]} by {user_id[:8]}",
                observations=[f"Secret {secret_id} used in {activity_type}"],
                metadata=audit_metadata,
                tags=["audit", "secret_usage"],
            )

            return entity

        except Exception as e:
            logger.error("Failed to create secret usage audit: %s", e)
            raise

    def _secret_matches_filters(
        self: AutoBotMemoryGraphCore,
        secret: Dict[str, Any],
        scope: Optional[str],
        session_id: Optional[str],
    ) -> bool:
        """Issue #665: Check if a secret matches the provided filters."""
        secret_scope = secret.get("metadata", {}).get("scope")

        if scope and secret_scope != scope:
            return False

        if secret_scope == "session" and session_id:
            if secret.get("metadata", {}).get("session_id") != session_id:
                return False

        return True

    async def _get_owned_secrets(
        self: AutoBotMemoryGraphCore,
        user_id: str,
        scope: Optional[str],
        session_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Issue #665: Get secrets owned by a user with optional filtering."""
        secrets = []
        owned_relations = await self.get_relations(
            entity_id=user_id,
            relation_types=["has_secret"],
            direction="outgoing",
        )

        for rel in owned_relations.get("relations", []):
            secret = await self.get_entity(entity_id=rel["to"])
            if secret and self._secret_matches_filters(secret, scope, session_id):
                secrets.append(secret)

        return secrets

    async def _get_shared_secrets(
        self: AutoBotMemoryGraphCore,
        user_id: str,
        scope: Optional[str],
        existing_secrets: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Issue #665: Get secrets shared with a user."""
        secrets = []
        shared_search = await self.search_entities(
            query=user_id,
            entity_type="secret",
            limit=100,
        )

        for secret in shared_search:
            shared_with = secret.get("metadata", {}).get("shared_with", [])
            if user_id in shared_with and secret not in existing_secrets:
                if scope is None or secret.get("metadata", {}).get("scope") == scope:
                    secrets.append(secret)

        return secrets

    async def get_user_secrets(
        self: AutoBotMemoryGraphCore,
        user_id: str,
        scope: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get secrets accessible to a user.

        Issue #608: Returns secrets based on access permissions.

        Args:
            user_id: User ID to query
            scope: Filter by scope (user, session, shared)
            session_id: For session-scoped, which session to check

        Returns:
            List of secret entities (without actual secret values)
        """
        self.ensure_initialized()

        try:
            owned = await self._get_owned_secrets(user_id, scope, session_id)
            shared = await self._get_shared_secrets(user_id, scope, owned)
            return owned + shared

        except Exception as e:
            logger.error("Failed to get user secrets: %s", e)
            return []
