# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat History Messages Mixin - Message operations.

Provides message management functionality:
- Add messages to sessions or default history
- Get session messages with model-aware limits
- Update message metadata
- Add tool markers to messages

Note: Message deduplication is handled at the source level via
SKIP_WEBSOCKET_PERSISTENCE_TYPES in backend/type_defs/common.py
(Issue #350 root cause fix).
"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MessagesMixin:
    """
    Mixin providing message operations for chat history.

    Requires base class to have:
    - self.history: list
    - self.context_manager: ContextWindowManager
    - self.load_session(): method
    - self.save_session(): method
    - self._save_history(): method
    - self._periodic_memory_check(): method
    """

    def _build_message_dict(
        self,
        sender: str,
        text: str,
        message_type: str,
        raw_data: Any,
        tool_markers: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """
        Build a message dictionary with standard fields.

        Args:
            sender: The sender of the message.
            text: The content of the message.
            message_type: The type of message.
            raw_data: Additional raw data (metadata).
            tool_markers: Optional list of tool usage markers.

        Returns:
            Constructed message dictionary.

        Issue #620.
        """
        message = {
            "id": str(uuid.uuid4()),
            "sender": sender,
            "text": text,
            "messageType": message_type,
            "metadata": raw_data,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if tool_markers:
            message["toolMarkers"] = tool_markers
        return message

    async def _add_message_to_session(
        self, session_id: str, message: Dict[str, Any]
    ) -> bool:
        """
        Add a message to a specific session.

        Args:
            session_id: The session identifier.
            message: The message dictionary to add.

        Returns:
            True if successful, False otherwise.

        Issue #620.
        """
        try:
            messages = await self.load_session(session_id)
            messages.append(message)
            await self.save_session(session_id, messages=messages)
            logger.debug("Added message to session %s", session_id)
            return True
        except Exception as e:
            logger.error("Error adding message to session %s: %s", session_id, e)
            return False

    async def add_message(
        self,
        sender: str,
        text: str,
        message_type: str = "default",
        raw_data: Any = None,
        session_id: Optional[str] = None,
        tool_markers: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Adds a new message to the history and saves it to file.

        PERFORMANCE OPTIMIZATION: Includes memory monitoring.

        Args:
            sender (str): The sender of the message (e.g., 'user', 'bot').
            text (str): The content of the message.
            message_type (str): The type of message (default is 'default').
            raw_data (Any): Additional raw data associated with the message.
            session_id (str): Optional session ID to add message to specific session.
            tool_markers (List[Dict[str, Any]]): Optional list of tool usage markers.

        Issue #620: Refactored to use extracted helper methods.
        """
        message = self._build_message_dict(
            sender, text, message_type, raw_data, tool_markers
        )

        # If session_id provided, add to that session
        if session_id:
            if await self._add_message_to_session(session_id, message):
                return
            # Fall through to add to default history on failure

        # Otherwise add to default history
        self.history.append(message)
        self._periodic_memory_check()
        await self._save_history()
        logger.debug("Added message from %s with type %s", sender, message_type)

    def get_all_messages(self) -> List[Dict[str, Any]]:
        """Returns the entire chat history."""
        return self.history

    async def get_session_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        model_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Gets messages for a specific session with model-aware limits.

        Args:
            session_id (str): The session identifier.
            limit (Optional[int]): Maximum number of messages to return.
                If None, uses model-aware default.
            model_name (Optional[str]): LLM model name for context-aware limiting.

        Returns:
            List[Dict[str, Any]]: List of messages in the session.
        """
        messages = await self.load_session(session_id)

        # Use model-aware limit if not explicitly provided
        if limit is None:
            limit = self.context_manager.calculate_retrieval_limit(model_name)
            logger.debug(
                f"Using model-aware limit: {limit} messages for model "
                f"{model_name or 'default'}"
            )

        if limit > 0:
            return messages[-limit:]  # Return last N messages
        return messages

    async def get_session_message_count(self, session_id: str) -> int:
        """
        Gets the message count for a specific session.

        Args:
            session_id (str): The session identifier.

        Returns:
            int: Number of messages in the session.
        """
        messages = await self.load_session(session_id)
        return len(messages)

    def _message_matches_filter(
        self, message: Dict[str, Any], metadata_filter: Dict[str, Any]
    ) -> bool:
        """
        Check if a message matches all filter criteria.

        Args:
            message: Message dictionary to check.
            metadata_filter: Dict of metadata key-value pairs to match.

        Returns:
            True if all filter criteria match, False otherwise.

        Issue #620.
        """
        msg_metadata = message.get("metadata", {})
        return all(
            msg_metadata.get(key) == value for key, value in metadata_filter.items()
        )

    def _apply_metadata_updates(
        self, message: Dict[str, Any], metadata_updates: Dict[str, Any]
    ) -> None:
        """
        Apply metadata updates to a message in-place.

        Args:
            message: Message dictionary to update.
            metadata_updates: Dict of metadata key-value pairs to apply.

        Issue #620.
        """
        if "metadata" not in message:
            message["metadata"] = {}
        message["metadata"].update(metadata_updates)

    async def update_message_metadata(
        self,
        session_id: str,
        metadata_filter: Dict[str, Any],
        metadata_updates: Dict[str, Any],
    ) -> bool:
        """
        Update metadata for a specific message in a session.

        CRITICAL FIX: Allows updating approval_status to persist across frontend polling.

        Args:
            session_id: Session ID containing the message
            metadata_filter: Dict of metadata key-value pairs to match the message
            metadata_updates: Dict of metadata key-value pairs to update

        Returns:
            True if message was found and updated, False otherwise

        Example:
            # Update approval status for a message
            await manager.update_message_metadata(
                session_id="abc123",
                metadata_filter={"terminal_session_id": "xyz789", "requires_approval": True},
                metadata_updates={"approval_status": "approved", "approval_comment": "Looks good"}
            )
        """
        try:
            messages = await self.load_session(session_id)

            for message in messages:
                if self._message_matches_filter(message, metadata_filter):
                    self._apply_metadata_updates(message, metadata_updates)
                    await self.save_session(session_id, messages=messages)
                    logger.info(
                        f"Updated message metadata in session {session_id}: "
                        f"filter={metadata_filter}, updates={metadata_updates}"
                    )
                    return True

            logger.warning(
                f"No message found matching metadata filter in session "
                f"{session_id}: {metadata_filter}"
            )
            return False

        except Exception as e:
            logger.error(
                f"Error updating message metadata in session {session_id}: {e}"
            )
            return False

    async def add_tool_marker_to_last_message(
        self, session_id: str, tool_type: str, tool_action: str, **marker_data: Any
    ) -> bool:
        """
        Add a tool usage marker to the most recent message in a session.

        Args:
            session_id: Chat session ID
            tool_type: Type of tool used (e.g., "terminal", "knowledge_base", "search")
            tool_action: Action performed (e.g., "execute_command", "search_docs")
            **marker_data: Additional marker data (command, run_type, log_file, etc.)

        Returns:
            True if marker was added successfully, False otherwise
        """
        try:
            messages = await self.load_session(session_id)

            if not messages:
                logger.warning("No messages found in session %s", session_id)
                return False

            # Get last message
            last_message = messages[-1]

            # Create tool marker
            tool_marker = {
                "tool_type": tool_type,
                "tool_action": tool_action,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            # Add any additional marker data
            tool_marker.update(marker_data)

            # Add marker to message
            if "toolMarkers" not in last_message:
                last_message["toolMarkers"] = []

            last_message["toolMarkers"].append(tool_marker)

            # Save updated messages
            await self.save_session(session_id, messages=messages)

            logger.debug(
                "Added %s tool marker to last message in session %s",
                tool_type,
                session_id,
            )
            return True

        except Exception as e:
            logger.error("Failed to add tool marker to session %s: %s", session_id, e)
            return False
