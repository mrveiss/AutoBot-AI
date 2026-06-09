# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
MCP Resource Subscription Manager - MVA-2166

Manages subscriptions to MCP resources and publishes change notifications
via the LiveEventManager WebSocket infrastructure.

Architecture:
- Subscription registry: tracks which sessions are subscribed to which resource URIs
- File watchers: monitors filesystem changes
- Git watchers: detects commits and branch updates
- Knowledge watchers: detects document changes in ChromaDB
- Event publishing: sends notifications via WebSocket channels

Channel naming: mcp:resource:{uri_hash}
Example: mcp:resource:file_2f_home_2f_user_2f_project_2f_file_2e_txt
"""

import asyncio
import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Dict, Set

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from live_event_manager import publish_live_event

logger = get_logger(__name__)


def _uri_to_channel(uri: str) -> str:
    """Convert a resource URI to a channel name.

    Uses SHA256 hash to create a stable, collision-resistant channel name.

    Args:
        uri: Resource URI (e.g., file:///path/to/file, git://repo/commit/sha)

    Returns:
        Channel name for LiveEventManager (e.g., mcp:resource:abc123...)
    """
    uri_hash = hashlib.sha256(uri.encode()).hexdigest()[:16]
    return f"mcp:resource:{uri_hash}"


class MCPSubscriptionManager:
    """Manages subscriptions to MCP resources and publishes change events."""

    def __init__(self) -> None:
        self._subscriptions: Dict[str, Set[str]] = defaultdict(set)  # uri -> set of session_ids
        self._session_subscriptions: Dict[str, Set[str]] = defaultdict(set)  # session_id -> set of uris
        self._lock = asyncio.Lock()
        self._file_watchers: Dict[str, asyncio.Task] = {}  # uri -> watcher task

    async def subscribe(self, session_id: str, uri: str) -> bool:
        """Subscribe a session to a resource URI.

        Args:
            session_id: Unique session identifier
            uri: Resource URI to subscribe to

        Returns:
            True if subscription was successful, False otherwise
        """
        if not uri:
            logger.warning("Cannot subscribe to empty URI")
            return False

        async with self._lock:
            self._subscriptions[uri].add(session_id)
            self._session_subscriptions[session_id].add(uri)
            logger.info("Session %s subscribed to resource: %s", session_id[:8], uri)

        # Start file watcher if this is a file:// URI
        if uri.startswith("file://"):
            await self._ensure_file_watcher(uri)

        return True

    async def unsubscribe(self, session_id: str, uri: str) -> bool:
        """Unsubscribe a session from a resource URI.

        Args:
            session_id: Session identifier
            uri: Resource URI to unsubscribe from

        Returns:
            True if unsubscription was successful
        """
        async with self._lock:
            if uri in self._subscriptions:
                self._subscriptions[uri].discard(session_id)
                if not self._subscriptions[uri]:
                    # No more subscribers for this URI
                    del self._subscriptions[uri]
                    # Stop file watcher if it exists
                    if uri in self._file_watchers:
                        self._file_watchers[uri].cancel()
                        del self._file_watchers[uri]
                        logger.debug("Stopped file watcher for: %s", uri)

            if session_id in self._session_subscriptions:
                self._session_subscriptions[session_id].discard(uri)

        logger.info("Session %s unsubscribed from resource: %s", session_id[:8], uri)
        return True

    async def unsubscribe_session(self, session_id: str) -> int:
        """Unsubscribe a session from all resources.

        Args:
            session_id: Session identifier to remove

        Returns:
            Number of subscriptions removed
        """
        async with self._lock:
            uris = self._session_subscriptions.pop(session_id, set())
            for uri in uris:
                if uri in self._subscriptions:
                    self._subscriptions[uri].discard(session_id)
                    if not self._subscriptions[uri]:
                        del self._subscriptions[uri]
                        # Stop file watcher if no more subscribers
                        if uri in self._file_watchers:
                            self._file_watchers[uri].cancel()
                            del self._file_watchers[uri]

        logger.info("Session %s unsubscribed from %d resources", session_id[:8], len(uris))
        return len(uris)

    async def publish_change(self, uri: str, change_type: str, payload: dict) -> int:
        """Publish a resource change event to all subscribers.

        Args:
            uri: Resource URI that changed
            change_type: Type of change (modified, created, deleted, etc.)
            payload: Additional change information

        Returns:
            Number of notifications sent
        """
        async with self._lock:
            session_ids = self._subscriptions.get(uri, set()).copy()

        if not session_ids:
            logger.debug("No subscribers for resource change: %s", uri)
            return 0

        channel = _uri_to_channel(uri)
        event_payload = {"uri": uri, "change_type": change_type, **payload}

        sent = await publish_live_event(channel, "mcp_resource_changed", event_payload)
        logger.info(
            "Published resource change for %s (type=%s, subscribers=%d, sent=%d)",
            uri,
            change_type,
            len(session_ids),
            sent,
        )
        return sent

    async def _ensure_file_watcher(self, uri: str) -> None:
        """Ensure a file watcher exists for a file:// URI.

        Args:
            uri: File URI to watch
        """
        if uri in self._file_watchers:
            # Watcher already exists
            return

        if not uri.startswith("file://"):
            return

        # Extract file path from URI
        file_path = uri[7:]  # Remove "file://"
        path = Path(file_path)

        if not path.exists():
            logger.warning("Cannot watch non-existent file: %s", file_path)
            return

        # Create watcher task
        task = asyncio.create_task(self._watch_file(uri, path))
        self._file_watchers[uri] = task
        logger.info("Started file watcher for: %s", uri)

    async def _watch_file(self, uri: str, path: Path) -> None:
        """Watch a file for changes and publish events.

        Args:
            uri: Resource URI
            path: File path to watch
        """
        try:
            last_mtime = path.stat().st_mtime if path.exists() else None

            while True:
                await asyncio.sleep(1.0)  # Poll interval

                # Check if file still has subscribers
                async with self._lock:
                    if uri not in self._subscriptions:
                        logger.debug("File watcher stopping (no subscribers): %s", uri)
                        break

                # Check for changes
                try:
                    if not path.exists():
                        if last_mtime is not None:
                            # File was deleted
                            await self.publish_change(uri, "deleted", {})
                            last_mtime = None
                    else:
                        current_mtime = path.stat().st_mtime
                        if last_mtime is None:
                            # File was created
                            await self.publish_change(uri, "created", {"size": path.stat().st_size})
                            last_mtime = current_mtime
                        elif current_mtime != last_mtime:
                            # File was modified
                            await self.publish_change(uri, "modified", {"size": path.stat().st_size})
                            last_mtime = current_mtime
                except Exception as e:
                    logger.error("Error checking file %s: %s", path, e)

        except asyncio.CancelledError:
            logger.debug("File watcher cancelled: %s", uri)
        except Exception as e:
            logger.error("File watcher error for %s: %s", uri, e)

    def get_subscription_stats(self) -> dict:
        """Get subscription statistics.

        Returns:
            Dictionary with subscription counts
        """
        return {
            "total_subscriptions": sum(len(sessions) for sessions in self._subscriptions.values()),
            "unique_resources": len(self._subscriptions),
            "active_sessions": len(self._session_subscriptions),
            "active_file_watchers": len(self._file_watchers),
        }


get_mcp_subscription_manager = lazy_singleton(MCPSubscriptionManager)
