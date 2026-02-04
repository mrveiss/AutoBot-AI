# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Memory Graph - User-Centric Session Tracking Module

This module contains Issue #608 user-centric session tracking operations:
- User entity management
- Chat session management (single/collaborative)
- Activity tracking (terminal, file, browser, desktop)
- Session and activity queries

Part of the modular autobot_memory_graph package (Issue #716).
Secret management is in secrets.py module.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .core import VALID_ACTIVITY_TYPES, AutoBotMemoryGraphCore

logger = logging.getLogger(__name__)


class UserSessionMixin:
    """
    Mixin class providing user-centric session tracking operations.

    Issue #608: This mixin provides functionality for:
    - User entity creation and management
    - Chat session tracking with ownership
    - Activity logging within sessions
    - Session and activity queries

    Note: Secret management is in SecretManagementMixin (secrets.py).
    """

    def _build_user_metadata(
        self: AutoBotMemoryGraphCore,
        user_id: str,
        username: str,
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build metadata dictionary for a user entity. Issue #620."""
        user_metadata = metadata or {}
        user_metadata.update(
            {
                "user_id": user_id,
                "username": username,
                "status": "active",
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        return user_metadata

    async def create_user_entity(
        self: AutoBotMemoryGraphCore,
        user_id: str,
        username: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create or get a user entity. Issue #620."""
        self.ensure_initialized()

        try:
            existing = await self.search_entities(
                query=user_id, entity_type="user", limit=1
            )
            if existing:
                logger.debug("User entity already exists for %s", username)
                return existing[0]

            user_metadata = self._build_user_metadata(user_id, username, metadata)
            entity = await self.create_entity(
                entity_type="user",
                name=f"User: {username}",
                observations=[f"User account created: {username}"],
                metadata=user_metadata,
                tags=["user", "account"],
            )
            logger.info("Created user entity for %s (id: %s)", username, user_id)
            return entity
        except Exception as e:
            logger.error("Failed to create user entity: %s", e)
            raise

    def _build_session_metadata(
        self: AutoBotMemoryGraphCore,
        session_id: str,
        owner_id: str,
        collaborators: Optional[List[str]],
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Issue #665: Build metadata dictionary for a chat session entity."""
        session_metadata = metadata or {}
        session_metadata.update(
            {
                "session_id": session_id,
                "owner_id": owner_id,
                "mode": "collaborative" if collaborators else "single_user",
                "collaborators": collaborators or [],
                "status": "active",
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        return session_metadata

    async def _create_session_owner_relations(
        self: AutoBotMemoryGraphCore,
        owner_id: str,
        entity_id: str,
    ) -> None:
        """Issue #665: Create owner relationships for a chat session entity."""
        await self.create_relation_by_id(
            from_entity_id=owner_id,
            to_entity_id=entity_id,
            relation_type="owns",
            metadata={"role": "owner"},
        )
        await self.create_relation_by_id(
            from_entity_id=owner_id,
            to_entity_id=entity_id,
            relation_type="has_session",
        )

    async def _create_collaborator_relations(
        self: AutoBotMemoryGraphCore,
        entity_id: str,
        collaborators: Optional[List[str]],
    ) -> None:
        """Issue #665: Create collaborator relationships for multi-user sessions."""
        if not collaborators:
            return
        for collaborator_id in collaborators:
            await self.create_relation_by_id(
                from_entity_id=entity_id,
                to_entity_id=collaborator_id,
                relation_type="has_participant",
                metadata={"role": "collaborator"},
            )

    async def create_chat_session_entity(
        self: AutoBotMemoryGraphCore,
        session_id: str,
        owner_id: str,
        title: Optional[str] = None,
        collaborators: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a chat session entity with user ownership tracking.

        Issue #608/#665: Supports single/multi-user modes, activity tracking.

        Args:
            session_id: Unique session identifier
            owner_id: User ID of session owner
            title: Optional session title
            collaborators: Optional list of collaborator user IDs
            metadata: Optional additional metadata

        Returns:
            Created session entity
        """
        self.ensure_initialized()

        try:
            session_metadata = self._build_session_metadata(
                session_id, owner_id, collaborators, metadata
            )
            entity = await self.create_entity(
                entity_type="chat_session",
                name=title or f"Chat Session {session_id[:8]}",
                observations=[f"Session created by user {owner_id}"],
                metadata=session_metadata,
                tags=["session", "chat"],
            )
            await self._create_session_owner_relations(owner_id, entity["id"])
            await self._create_collaborator_relations(entity["id"], collaborators)
            logger.info("Created chat session entity: %s", session_id)
            return entity

        except Exception as e:
            logger.error("Failed to create chat session entity: %s", e)
            raise

    def _validate_activity_type(
        self: AutoBotMemoryGraphCore,
        activity_type: str,
    ) -> None:
        """Issue #665: Validate that the activity type is valid."""
        if activity_type not in VALID_ACTIVITY_TYPES:
            raise ValueError(
                f"Invalid activity_type: {activity_type}. "
                f"Must be one of {VALID_ACTIVITY_TYPES}"
            )

    def _build_activity_metadata(
        self: AutoBotMemoryGraphCore,
        session_id: str,
        user_id: str,
        secrets_used: Optional[List[str]],
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Issue #665: Build metadata dictionary for an activity entity."""
        activity_metadata = metadata or {}
        activity_metadata.update(
            {
                "session_id": session_id,
                "user_id": user_id,
                "secrets_used": secrets_used or [],
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        return activity_metadata

    async def _create_activity_relations(
        self: AutoBotMemoryGraphCore,
        session_id: str,
        entity_id: str,
        user_id: str,
    ) -> None:
        """Issue #665: Create core relationships for an activity entity."""
        await self.create_relation_by_id(
            from_entity_id=session_id,
            to_entity_id=entity_id,
            relation_type="has_activity",
        )
        await self.create_relation_by_id(
            from_entity_id=entity_id,
            to_entity_id=user_id,
            relation_type="performed_by",
        )

    async def _create_secret_usage_relations(
        self: AutoBotMemoryGraphCore,
        entity_id: str,
        user_id: str,
        activity_type: str,
        secrets_used: Optional[List[str]],
    ) -> None:
        """Issue #665: Create secret usage relationships and audit trail."""
        if not secrets_used:
            return
        for secret_id in secrets_used:
            await self.create_relation_by_id(
                from_entity_id=entity_id,
                to_entity_id=secret_id,
                relation_type="uses_secret",
            )
            await self._create_secret_usage_audit(
                secret_id=secret_id,
                user_id=user_id,
                activity_type=activity_type,
                activity_id=entity_id,
            )

    async def create_activity_entity(
        self: AutoBotMemoryGraphCore,
        activity_type: str,
        session_id: str,
        user_id: str,
        content: str,
        secrets_used: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create an activity entity within a chat session.

        Issue #608/#665: Activities tracked with user attribution and secret usage.

        Args:
            activity_type: Type of activity (terminal, file, browser, desktop)
            session_id: Parent chat session ID
            user_id: User who performed the activity
            content: Activity content/description
            secrets_used: Optional list of secret IDs used
            metadata: Optional additional metadata

        Returns:
            Created activity entity
        """
        self.ensure_initialized()
        self._validate_activity_type(activity_type)

        try:
            activity_metadata = self._build_activity_metadata(
                session_id, user_id, secrets_used, metadata
            )
            entity = await self.create_entity(
                entity_type=activity_type,
                name=f"{activity_type.replace('_', ' ').title()} by {user_id[:8]}",
                observations=[content],
                metadata=activity_metadata,
                tags=["activity", activity_type.replace("_activity", "")],
            )
            await self._create_activity_relations(session_id, entity["id"], user_id)
            await self._create_secret_usage_relations(
                entity["id"], user_id, activity_type, secrets_used
            )
            logger.info("Created %s entity for session %s", activity_type, session_id)
            return entity

        except Exception as e:
            logger.error("Failed to create activity entity: %s", e)
            raise

    async def get_user_sessions(
        self: AutoBotMemoryGraphCore,
        user_id: str,
        include_collaborative: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get all sessions for a user.

        Issue #608: Returns both owned sessions and collaborative sessions.

        Args:
            user_id: User ID to query
            include_collaborative: Include sessions where user is collaborator

        Returns:
            List of session entities
        """
        self.ensure_initialized()

        try:
            sessions = []

            owned_relations = await self.get_relations(
                entity_id=user_id,
                relation_types=["owns", "has_session"],
                direction="outgoing",
            )

            for rel in owned_relations.get("relations", []):
                session = await self.get_entity(entity_id=rel["to"])
                if session and session.get("metadata", {}).get("session_id"):
                    sessions.append(session)

            if include_collaborative:
                collab_sessions = await self.search_entities(
                    query=user_id,
                    entity_type="chat_session",
                    limit=100,
                )
                for session in collab_sessions:
                    collaborators = session.get("metadata", {}).get("collaborators", [])
                    if user_id in collaborators and session not in sessions:
                        sessions.append(session)

            return sessions

        except Exception as e:
            logger.error("Failed to get user sessions: %s", e)
            return []

    def _activity_matches_filters(
        self: AutoBotMemoryGraphCore,
        activity: Dict[str, Any],
        activity_types: Optional[List[str]],
        user_id: Optional[str],
    ) -> bool:
        """
        Check if an activity matches the provided filters.

        Issue #620.

        Args:
            activity: Activity entity to check
            activity_types: Filter by activity types (None = any type)
            user_id: Filter by user who performed the activity (None = any user)

        Returns:
            True if activity matches all filters
        """
        if activity_types and activity.get("type") not in activity_types:
            return False

        if user_id and activity.get("metadata", {}).get("user_id") != user_id:
            return False

        return True

    async def _fetch_and_filter_activities(
        self: AutoBotMemoryGraphCore,
        session_id: str,
        activity_types: Optional[List[str]],
        user_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """
        Fetch activities from relations and filter them.

        Issue #620.

        Args:
            session_id: Session ID to query
            activity_types: Filter by activity types
            user_id: Filter by user
            limit: Maximum activities to return

        Returns:
            List of filtered activity entities
        """
        relations = await self.get_relations(
            entity_id=session_id,
            relation_types=["has_activity"],
            direction="outgoing",
        )

        activities = []
        for rel in relations.get("relations", []):
            activity = await self.get_entity(entity_id=rel["to"])
            if not activity:
                continue

            if self._activity_matches_filters(activity, activity_types, user_id):
                activities.append(activity)
                if len(activities) >= limit:
                    break

        return activities

    async def get_session_activities(
        self: AutoBotMemoryGraphCore,
        session_id: str,
        activity_types: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get activities for a session.

        Issue #608: Returns all activities within a session, optionally filtered.
        Issue #620: Refactored using Extract Method pattern.

        Args:
            session_id: Session ID to query
            activity_types: Filter by activity types
            user_id: Filter by user who performed the activity
            limit: Maximum number of activities to return

        Returns:
            List of activity entities sorted by timestamp (newest first)
        """
        self.ensure_initialized()

        try:
            activities = await self._fetch_and_filter_activities(
                session_id, activity_types, user_id, limit
            )

            activities.sort(
                key=lambda x: x.get("metadata", {}).get("timestamp", ""),
                reverse=True,
            )

            return activities

        except Exception as e:
            logger.error("Failed to get session activities: %s", e)
            return []
