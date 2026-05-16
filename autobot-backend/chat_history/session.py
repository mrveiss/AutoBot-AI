# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat History Session Mixin - Session CRUD operations.

Provides session management for chat history:
- Session creation with metadata
- Session loading with caching
- Session saving with atomic writes
- Session deletion with cleanup
- Session listing and updates
"""

import json
import os
import time
import uuid
from typing import Any, Dict, List

import aiofiles

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import validate_relative_path
from chat_history.cache import _CHAT_RECENT_MAX_ENTRIES
from chat_history.file_io import run_in_chat_io_executor
from constants.redis_constants import REDIS_KEY

logger = get_logger(__name__)


class SessionMixin:
    """
    Mixin providing session CRUD operations for chat history.

    Requires base class to have:
    - self.redis_client: Redis client or None
    - self.max_messages: int
    - self.max_session_files: int
    - self._counter_lock: threading.Lock
    - self._session_save_counter: int
    - self.memory_graph: MemoryGraph or None
    - self.memory_graph_enabled: bool
    - self._get_chats_directory(): method
    - self._encrypt_data(): method
    - self._decrypt_data(): method
    - self._dedupe_streaming_messages(): method
    - self._async_cache_session(): method
    - self._atomic_write(): method
    - self._cleanup_old_session_files(): method
    - self._init_memory_graph(): method
    - self._extract_conversation_metadata(): method
    """

    @staticmethod
    def _sanitize_session_id(session_id: str) -> None:
        """
        Validate session_id to prevent path traversal attacks. Issue #1825.

        Accepts UUID-like strings and alphanumeric strings with hyphens/underscores.
        Rejects any ID containing '..', '/', '\\', or null bytes.

        Args:
            session_id: The session identifier to validate.

        Raises:
            ValueError: If session_id contains path traversal characters.
        """
        if not session_id:
            raise ValueError("session_id must not be empty")
        if "\x00" in session_id:
            raise ValueError("session_id must not contain null bytes")
        if ".." in session_id or "/" in session_id or "\\" in session_id:
            raise ValueError(
                "session_id must not contain path traversal characters " f"('..', '/', '\\'): {session_id!r}"
            )

    def _try_get_from_cache(self, session_id: str) -> List[Dict[str, Any]] | None:
        """Try to get session from Redis cache. (Issue #315 - extracted)"""
        if not self.redis_client:
            return None
        try:
            cache_key = f"chat:session:{session_id}"
            cached_data = self.redis_client.get(cache_key)
            if not cached_data:
                return None
            if isinstance(cached_data, bytes):
                cached_data = cached_data.decode("utf-8")
            chat_data = json.loads(cached_data)
            logger.debug("Cache HIT for session %s", session_id)
            return chat_data.get("messages", [])
        except Exception as e:
            logger.error("Failed to read from Redis cache: %s", e)
            return None

    async def _resolve_session_file_path(self, session_id: str, chats_directory: str) -> str | None:
        """Resolve session file path with backward compatibility.

        Issue #315 - extracted.  Issue #1721 - uses shared path validator.
        """
        # Validate paths against chats directory (#1721)
        chat_file = str(validate_relative_path(f"{session_id}_chat.json", chats_directory))
        file_exists = await run_in_chat_io_executor(os.path.exists, chat_file)
        if file_exists:
            return chat_file

        # Backward compatibility: try old naming convention
        chat_file_old = str(validate_relative_path(f"chat_{session_id}.json", chats_directory))
        old_file_exists = await run_in_chat_io_executor(os.path.exists, chat_file_old)
        if old_file_exists:
            logger.debug("Using legacy file format for session %s", session_id)
            return chat_file_old

        logger.warning("Chat session %s not found", session_id)
        return None

    async def _load_existing_chat_data(self, session_id: str, chat_file: str, chats_directory: str) -> Dict[str, Any]:
        """Load existing chat data with backward compatibility. (Issue #315 - extracted)"""
        file_exists = await run_in_chat_io_executor(os.path.exists, chat_file)
        if file_exists:
            try:
                async with aiofiles.open(chat_file, "r", encoding="utf-8") as f:
                    file_content = await f.read()
                return self._decrypt_data(file_content)
            except Exception as e:
                logger.warning("Could not load existing chat data for %s: %s", session_id, e)
                return {}

        # Try old format for backward compatibility
        chat_file_old = str(validate_relative_path(f"chat_{session_id}.json", chats_directory))
        old_file_exists = await run_in_chat_io_executor(os.path.exists, chat_file_old)
        if old_file_exists:
            try:
                async with aiofiles.open(chat_file_old, "r", encoding="utf-8") as f:
                    file_content = await f.read()
                logger.debug("Migrating session %s from old format", session_id)
                return self._decrypt_data(file_content)
            except Exception as e:
                logger.warning("Could not load old format data: %s", e)
        return {}

    def _build_session_data(
        self,
        session_id: str,
        session_title: str,
        current_time: str,
        metadata: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        """
        Build the session data dictionary.

        (Issue #398: extracted helper)
        """
        return {
            "id": session_id,
            "chatId": session_id,  # Backward compatibility
            "title": session_title,
            "name": session_title,  # Backward compatibility
            "messages": [],
            "createdAt": current_time,
            "createdTime": current_time,  # Backward compatibility
            "updatedAt": current_time,
            "lastModified": current_time,  # Backward compatibility
            "isActive": True,
            "metadata": metadata or {},
        }

    async def _create_memory_graph_entity(
        self,
        session_id: str,
        session_title: str,
        current_time: str,
        metadata: Dict[str, Any] | None,
    ) -> None:
        """
        Create conversation entity in Memory Graph.

        (Issue #398: extracted helper)
        """
        if not (self.memory_graph_enabled and self.memory_graph):
            return

        try:
            entity_metadata = {
                "session_id": session_id,
                "title": session_title,
                "created_at": current_time,
                "status": "active",
                "priority": "medium",
            }

            if metadata:
                entity_metadata.update(metadata)

            await self.memory_graph.create_conversation_entity(session_id=session_id, metadata=entity_metadata)

            logger.info("Created Memory Graph entity for session: %s", session_id)

        except Exception as e:
            logger.warning("Failed to create Memory Graph entity (continuing): %s", e)

    async def create_session(
        self,
        session_id: str | None = None,
        title: str | None = None,
        session_name: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Create a new chat session.

        (Issue #398: refactored to use extracted helpers)

        Args:
            session_id: Optional session ID (auto-generated if not provided)
            title: Optional title for the session
            session_name: Optional name for the session (backward compatibility)
            metadata: Optional metadata for the session

        Returns:
            Session data including session_id, title, etc.
        """
        await self._init_memory_graph()

        if not session_id:
            session_id = f"chat-{int(time.time() * 1000)}-{str(uuid.uuid4())[:8]}"
        else:
            self._sanitize_session_id(session_id)

        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        session_title = title or session_name or f"Chat {session_id[:13]}"

        session_data = self._build_session_data(session_id, session_title, current_time, metadata)

        await self.save_session(session_id=session_id, messages=[], name=session_title)
        await self._create_memory_graph_entity(session_id, session_title, current_time, metadata)

        logger.info("Created new chat session: %s", session_id)
        return session_data

    async def _load_session_from_file(self, session_id: str) -> Dict[str, Any] | None:
        """Load and decrypt session data from file. Issue #620."""
        chats_directory = self._get_chats_directory()
        chat_file = await self._resolve_session_file_path(session_id, chats_directory)
        if not chat_file:
            return None

        async with aiofiles.open(chat_file, "r", encoding="utf-8") as f:
            file_content = await f.read()

        return self._decrypt_data(file_content)

    async def _process_loaded_messages(self, session_id: str, chat_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Deduplicate messages and save cleaned version if needed. Issue #620."""
        messages = chat_data.get("messages", [])
        cleaned_messages = self._dedupe_streaming_messages(messages)

        if len(cleaned_messages) < len(messages):
            logger.info(
                "Cleaned %d duplicate streaming messages from session %s",
                len(messages) - len(cleaned_messages),
                session_id,
            )
            chat_data["messages"] = cleaned_messages
            try:
                await self.save_session(session_id, messages=cleaned_messages)
            except Exception as save_err:
                logger.warning("Could not save cleaned session: %s", save_err)

        return cleaned_messages

    async def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Load a specific chat session with Redis cache-first strategy.

        Raises:
            PermissionError: If access to the session file is denied.
            ValueError: If the session data is corrupted or cannot be decoded.

        Issue #1906: Propagate specific exceptions instead of silently returning [].

        Args:
            session_id: The session identifier

        Returns:
            List of messages in the session, or [] if the session does not exist.
        """
        self._sanitize_session_id(session_id)

        # Try Redis cache first (Issue #315 - uses helper)
        cached_messages = self._try_get_from_cache(session_id)
        if cached_messages is not None:
            return cached_messages

        logger.debug("Cache MISS for session %s", session_id)

        # Load from file (Issue #620 - uses helper).
        # FileNotFoundError and PermissionError propagate to caller.
        # ValueError (corrupted data) propagates to caller.
        chat_data = await self._load_session_from_file(session_id)
        if chat_data is None:
            # Session file not found — not an error, just an empty result.
            return []

        # Process messages (Issue #620 - uses helper)
        cleaned_messages = await self._process_loaded_messages(session_id, chat_data)

        # Warm up Redis cache with cleaned data
        await self._warm_cache_safe(session_id, chat_data)

        return cleaned_messages

    async def _warm_cache_safe(self, session_id: str, chat_data: Dict[str, Any]) -> None:
        """Warm up Redis cache safely. (Issue #315 - extracted)"""
        if not self.redis_client:
            return
        try:
            cache_key = f"chat:session:{session_id}"
            await self._async_cache_session(cache_key, chat_data)
            logger.debug("Warmed cache for session %s", session_id)
        except Exception as e:
            logger.error("Failed to warm cache: %s", e)

    async def _update_redis_cache_on_save(self, session_id: str, chat_data: Dict[str, Any]) -> None:
        """Update Redis cache on session save. (Issue #315 - extracted)"""
        if not self.redis_client:
            return
        try:
            cache_key = f"chat:session:{session_id}"
            await self._async_cache_session(cache_key, chat_data)
            # Update recent chats sorted set for fast listing
            # Issue #361 - avoid blocking
            # #7570: trim after insert so the set stays bounded
            await run_in_chat_io_executor(self.redis_client.zadd, REDIS_KEY.CHAT_RECENT, {session_id: time.time()})
            await run_in_chat_io_executor(
                self.redis_client.zremrangebyrank,
                REDIS_KEY.CHAT_RECENT,
                0,
                -(_CHAT_RECENT_MAX_ENTRIES + 1),
            )
            # Phase 4 (#7590): emit cardinality gauge for SSOT observability.
            # Structured JSON so Loki can parse: {"event": "chat_recent_cardinality", "value": N}
            # Alert fires when value > AUTOBOT_CHAT_SSOT_CARDINALITY_THRESHOLD (default 200).
            try:
                cardinality = await run_in_chat_io_executor(self.redis_client.zcard, REDIS_KEY.CHAT_RECENT)
                logger.info(json.dumps({"event": "chat_recent_cardinality", "value": cardinality}))
                try:
                    from monitoring.prometheus_metrics import get_metrics_manager

                    get_metrics_manager().set_chat_recent_cardinality(cardinality)
                except Exception as e:
                    logger.warning("chat:recent Prometheus cardinality update failed: %s", e)
            except Exception as card_err:
                logger.warning("chat:recent cardinality read failed: %s", card_err)
            logger.debug("Cached session %s in Redis", session_id)
        except Exception as e:
            logger.error("Failed to cache session in Redis: %s", e)

    def _prepare_session_messages(
        self,
        session_id: str,
        messages: List[Dict[str, Any]] | None,
    ) -> List[Dict[str, Any]]:
        """
        Prepare and validate session messages for saving.

        Handles message list initialization and truncation to prevent
        excessive file sizes.

        Args:
            session_id: The session identifier for logging.
            messages: The messages to prepare, or None for empty list.

        Returns:
            List of prepared messages, truncated if necessary.

        Issue #665: Extracted from save_session for single responsibility.
        """
        session_messages = messages if messages is not None else []

        if len(session_messages) > self.max_messages:
            logger.warning(
                f"Session {session_id} has {len(session_messages)} messages, "
                f"truncating to {self.max_messages} most recent"
            )
            session_messages = session_messages[-self.max_messages :]

        return session_messages

    async def _write_session_to_storage(
        self,
        chat_file: str,
        chat_data: Dict[str, Any],
    ) -> None:
        """
        Write session data to storage with atomic write and fallback.

        Attempts atomic write first for data integrity, falls back to
        direct write if atomic operation fails.

        Args:
            chat_file: Path to the chat session file.
            chat_data: The session data dictionary to save.

        Issue #665: Extracted from save_session for single responsibility.
        """
        encrypted_data = self._encrypt_data(chat_data)
        try:
            await self._atomic_write(chat_file, encrypted_data)
        except Exception as atomic_error:
            logger.warning(f"Atomic write failed, falling back to direct write: {atomic_error}")
            async with aiofiles.open(chat_file, "w", encoding="utf-8") as f:
                await f.write(encrypted_data)

    async def _handle_periodic_cleanup(self) -> None:
        """
        Handle periodic cleanup of old session files.

        Triggers cleanup every 10th save operation using thread-safe
        counter management.

        Issue #665: Extracted from save_session for single responsibility.
        """
        with self._counter_lock:
            self._session_save_counter += 1
            should_cleanup = self._session_save_counter % 10 == 0

        if should_cleanup:
            await self._cleanup_old_session_files()

    async def _ensure_chats_directory_exists(self, chats_directory: str) -> None:
        """
        Ensure the chats directory exists, creating it if necessary.

        Args:
            chats_directory: Path to the chats directory.

        Issue #620.
        """
        dir_exists = await run_in_chat_io_executor(os.path.exists, chats_directory)
        if not dir_exists:
            await run_in_chat_io_executor(os.makedirs, chats_directory, exist_ok=True)

    def _build_session_chat_data(
        self,
        chat_data: Dict[str, Any],
        session_id: str,
        name: str,
        session_messages: List[Dict[str, Any]],
        current_time: str,
    ) -> Dict[str, Any]:
        """
        Build updated chat data dictionary for session save.

        Args:
            chat_data: Existing chat data to update.
            session_id: The session identifier.
            name: Optional session name.
            session_messages: Messages to include.
            current_time: Current timestamp string.

        Returns:
            Updated chat data dictionary.

        Issue #620.
        """
        chat_data.update(
            {
                "chatId": session_id,
                "name": name or chat_data.get("name", ""),
                "messages": session_messages,
                "last_modified": current_time,
                "created_time": chat_data.get("created_time", current_time),
            }
        )
        return chat_data

    async def save_session(
        self,
        session_id: str,
        messages: List[Dict[str, Any]] | None = None,
        name: str = "",
    ):
        """
        Save a chat session with messages and metadata.

        Args:
            session_id: The identifier for the session to save.
            messages: The messages to save (defaults to empty list).
            name: Optional name for the chat session.

        Issue #665, #620: Refactored to use extracted helper methods.
        """
        try:
            self._sanitize_session_id(session_id)
            chats_directory = self._get_chats_directory()
            await self._ensure_chats_directory_exists(chats_directory)

            chat_file = str(validate_relative_path(f"{session_id}_chat.json", chats_directory))
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            session_messages = self._prepare_session_messages(session_id, messages)

            chat_data = await self._load_existing_chat_data(session_id, chat_file, chats_directory)
            chat_data = self._build_session_chat_data(chat_data, session_id, name, session_messages, current_time)

            await self._write_session_to_storage(chat_file, chat_data)
            await self._update_redis_cache_on_save(session_id, chat_data)
            logger.info("Chat session '%s' saved successfully", session_id)

            if self.memory_graph_enabled and self.memory_graph:
                await self._update_memory_graph_entity(session_id, session_messages, name, current_time)

            await self._handle_periodic_cleanup()

        except Exception as e:
            logger.error("Error saving chat session %s: %s", session_id, e)

    def _build_memory_graph_observations(
        self,
        metadata: Dict[str, Any],
        current_time: str,
    ) -> List[str]:
        """
        Build observation strings from conversation metadata.

        Args:
            metadata: Extracted conversation metadata with summary, topics, etc.
            current_time: Timestamp for the last updated observation.

        Returns:
            List of formatted observation strings for Memory Graph.

        Issue #620.
        """
        observations = [
            f"Summary: {metadata['summary']}",
            f"Topics: {', '.join(metadata['topics'])}",
            f"Message count: {metadata['message_count']}",
            f"Last updated: {current_time}",
        ]

        if metadata["entity_mentions"]:
            observations.append(f"Mentions: {', '.join(metadata['entity_mentions'])}")

        return observations

    async def _create_memory_graph_entity_on_missing(
        self,
        session_id: str,
        name: str,
        metadata: Dict[str, Any],
        observations: List[str],
    ) -> None:
        """
        Create a new Memory Graph entity when one does not exist.

        Args:
            session_id: The session identifier.
            name: Session name or title.
            metadata: Extracted conversation metadata.
            observations: Pre-built observation strings.

        Issue #620.
        """
        entity_metadata = {
            "session_id": session_id,
            "title": name or session_id,
            "status": "active",
            "priority": "medium",
            "topics": metadata["topics"],
            "entity_mentions": metadata["entity_mentions"],
        }

        await self.memory_graph.create_conversation_entity(
            session_id=session_id,
            metadata=entity_metadata,
            observations=observations,
        )

        logger.info("Created Memory Graph entity for session: %s", session_id)

    async def _update_memory_graph_entity(
        self,
        session_id: str,
        session_messages: List[Dict[str, Any]],
        name: str,
        current_time: str,
    ):
        """Update Memory Graph entity with conversation observations. Issue #620."""
        try:
            metadata = self._extract_conversation_metadata(session_messages)
            entity_name = f"Conversation {session_id[:8]}"
            observations = self._build_memory_graph_observations(metadata, current_time)

            try:
                await self.memory_graph.add_observations(entity_name=entity_name, observations=observations)
                logger.debug("Updated Memory Graph entity for session: %s", session_id)

            except (ValueError, RuntimeError) as e:
                if "Entity not found" in str(e):
                    logger.debug(
                        "Entity not found, creating new entity for session: %s",
                        session_id,
                    )
                    await self._create_memory_graph_entity_on_missing(session_id, name, metadata, observations)
                else:
                    raise

        except Exception as mg_error:
            logger.warning("Failed to update Memory Graph entity (continuing): %s", mg_error)

    async def _delete_session_files(self, session_id: str, chats_directory: str) -> bool:
        """
        Delete main session files (new and old format).

        Args:
            session_id: The session identifier.
            chats_directory: Path to the chats directory.

        Returns:
            True if at least one session file was deleted.

        Issue #620.  Issue #1721 - uses shared path validator.
        """
        deleted = False

        # Delete new format file
        chat_file_new = str(validate_relative_path(f"{session_id}_chat.json", chats_directory))
        new_exists = await run_in_chat_io_executor(os.path.exists, chat_file_new)
        if new_exists:
            await run_in_chat_io_executor(os.remove, chat_file_new)
            deleted = True

        # Delete old format file if exists
        chat_file_old = str(validate_relative_path(f"chat_{session_id}.json", chats_directory))
        old_exists = await run_in_chat_io_executor(os.path.exists, chat_file_old)
        if old_exists:
            await run_in_chat_io_executor(os.remove, chat_file_old)
            deleted = True

        return deleted

    async def _delete_companion_files(self, session_id: str, chats_directory: str) -> None:
        """
        Delete companion files (terminal logs, transcripts, etc.).

        Args:
            session_id: The session identifier.
            chats_directory: Path to the chats directory.

        Issue #620.
        """
        # Delete terminal log file
        terminal_log = str(validate_relative_path(f"{session_id}_terminal.log", chats_directory))
        log_exists = await run_in_chat_io_executor(os.path.exists, terminal_log)
        if log_exists:
            await run_in_chat_io_executor(os.remove, terminal_log)
            logger.debug("Deleted terminal log for session %s", session_id)

        # Delete terminal transcript file
        terminal_transcript = str(validate_relative_path(f"{session_id}_terminal_transcript.txt", chats_directory))
        transcript_exists = await run_in_chat_io_executor(os.path.exists, terminal_transcript)
        if transcript_exists:
            await run_in_chat_io_executor(os.remove, terminal_transcript)
            logger.debug("Deleted terminal transcript for session %s", session_id)

    async def _clear_session_redis_cache(self, session_id: str) -> None:
        """
        Clear Redis cache entries for the session.

        Args:
            session_id: The session identifier.

        Issue #620.
        """
        if not self.redis_client:
            return

        try:
            cache_key = f"chat:session:{session_id}"
            # Issue #361 - avoid blocking
            await run_in_chat_io_executor(self.redis_client.delete, cache_key)
            await run_in_chat_io_executor(self.redis_client.zrem, REDIS_KEY.CHAT_RECENT, session_id)
            logger.debug("Cleared Redis cache for session %s", session_id)
        except Exception as e:
            logger.error("Failed to clear Redis cache: %s", e)

    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a chat session and its companion files.

        Args:
            session_id: The identifier for the session to delete

        Returns:
            True if deletion was successful, False otherwise

        Issue #620: Refactored to use extracted helper methods.
        """
        try:
            self._sanitize_session_id(session_id)
            chats_directory = self._get_chats_directory()

            deleted = await self._delete_session_files(session_id, chats_directory)
            await self._delete_companion_files(session_id, chats_directory)
            await self._clear_session_redis_cache(session_id)

            if not deleted:
                logger.warning("Chat session %s not found for deletion", session_id)
                return False

            logger.info("Chat session '%s' deleted successfully", session_id)
            return True

        except Exception as e:
            logger.error("Error deleting chat session %s: %s", session_id, e)
            return False

    async def _update_redis_session_cache(self, session_id: str, chat_data: Dict[str, Any]) -> None:
        """
        Update the Redis cache for a session.

        Silently handles Redis errors to avoid failing the update. Issue #620.
        """
        if self.redis_client:
            try:
                cache_key = f"chat:session:{session_id}"
                await self._async_cache_session(cache_key, chat_data)
            except Exception as e:
                logger.error("Failed to update Redis cache: %s", e)

    async def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update session metadata (name, etc).

        Args:
            session_id: The session identifier
            updates: Dictionary of fields to update

        Returns:
            True if update successful, False otherwise
        """
        try:
            self._sanitize_session_id(session_id)
            chats_directory = self._get_chats_directory()
            chat_file = await self._resolve_session_file_path(session_id, chats_directory)
            if not chat_file:
                logger.warning("Session %s not found for update", session_id)
                return False

            # Load existing data
            async with aiofiles.open(chat_file, "r", encoding="utf-8") as f:
                file_content = await f.read()
            chat_data = self._decrypt_data(file_content)

            # Update fields
            chat_data.update(updates)
            chat_data["last_modified"] = time.strftime("%Y-%m-%d %H:%M:%S")

            # Save updated data (always use new format)
            chat_file_new = str(validate_relative_path(f"{session_id}_chat.json", chats_directory))
            encrypted_data = self._encrypt_data(chat_data)
            async with aiofiles.open(chat_file_new, "w", encoding="utf-8") as f:
                await f.write(encrypted_data)

            await self._update_redis_session_cache(session_id, chat_data)
            logger.info("Session %s updated successfully", session_id)
            return True

        except OSError as e:
            logger.error("Failed to read/write session file for %s: %s", session_id, e)
            return False
        except Exception as e:
            logger.error("Error updating session %s: %s", session_id, e)
            return False

    async def update_session_name(self, session_id: str, name: str) -> bool:
        """
        Update the name of a chat session.

        Args:
            session_id: The identifier for the session to update
            name: The new name for the session

        Returns:
            True if update was successful, False otherwise.
            Issue #620: Refactored to use existing helpers.
        """
        try:
            self._sanitize_session_id(session_id)
            chats_directory = self._get_chats_directory()

            # Resolve file path using existing helper
            chat_file = await self._resolve_session_file_path(session_id, chats_directory)
            if not chat_file:
                logger.warning("Chat session %s not found for name update", session_id)
                return False

            # Load and update session data (Issue #620: extracted helper)
            chat_data = await self._load_and_update_session_name(chat_file, name)

            # Save and cache updated data (Issue #620: extracted helper)
            await self._save_session_name_update(session_id, chats_directory, chat_data, name)

            return True

        except Exception as e:
            logger.error("Error updating chat session %s name: %s", session_id, e)
            return False

    async def _load_and_update_session_name(self, chat_file: str, name: str) -> Dict[str, Any]:
        """
        Load session data and update the name field.

        Args:
            chat_file: Path to the chat session file
            name: New name for the session

        Returns:
            Updated chat data dictionary. Issue #620.
        """
        async with aiofiles.open(chat_file, "r", encoding="utf-8") as f:
            file_content = await f.read()
        chat_data = json.loads(file_content)

        chat_data["name"] = name
        chat_data["last_modified"] = time.strftime("%Y-%m-%d %H:%M:%S")

        return chat_data

    async def _save_session_name_update(
        self,
        session_id: str,
        chats_directory: str,
        chat_data: Dict[str, Any],
        name: str,
    ) -> None:
        """
        Save updated session data and update Redis cache.

        Args:
            session_id: Session identifier
            chats_directory: Directory containing chat files
            chat_data: Updated chat data to save
            name: New session name (for logging). Issue #620.
        """
        # Save updated data (always use new format, #1721)
        chat_file_new = str(validate_relative_path(f"{session_id}_chat.json", chats_directory))
        async with aiofiles.open(chat_file_new, "w", encoding="utf-8") as f:
            await f.write(json.dumps(chat_data, indent=2, ensure_ascii=False))

        # Update Redis cache using existing helper
        await self._update_redis_session_cache(session_id, chat_data)

        logger.info("Chat session '%s' name updated to '%s'", session_id, name)

    async def load_full_session(self, session_id: str) -> Dict[str, Any] | None:
        """
        Load the complete session data dictionary for a given session.

        Returns the full raw data dict (messages, metadata, name, timestamps),
        or None when the session does not exist.

        This is the public API for callers that need more than just the messages
        list returned by :meth:`load_session`.  Issue #3189.

        Args:
            session_id: The session identifier.

        Returns:
            Full session data dict, or None if the session does not exist.
        """
        self._sanitize_session_id(session_id)
        return await self._load_session_from_file(session_id)

    async def get_session_owner(self, session_id: str) -> str | None:
        """
        Get the owner/creator of a specific session.

        Args:
            session_id: The session identifier

        Returns:
            Username of session owner, or None if not found/set
        """
        try:
            self._sanitize_session_id(session_id)
            chats_directory = self._get_chats_directory()
            chat_file = str(validate_relative_path(f"{session_id}_chat.json", chats_directory))

            # Try new format first
            file_exists = await run_in_chat_io_executor(os.path.exists, chat_file)
            if file_exists:
                async with aiofiles.open(chat_file, "r", encoding="utf-8") as f:
                    file_content = await f.read()
                chat_data = self._decrypt_data(file_content)

                # Check metadata for owner field
                metadata = chat_data.get("metadata", {})
                return metadata.get("owner") or metadata.get("username")

        except OSError as e:
            logger.warning("Failed to read session file %s: %s", chat_file, e)
        except Exception as e:
            logger.warning("Failed to get session owner for %s: %s", session_id, e)

        return None
