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
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

import aiofiles

from src.chat_history.file_io import run_in_chat_io_executor

logger = logging.getLogger(__name__)


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

    def _try_get_from_cache(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
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

    async def _resolve_session_file_path(
        self, session_id: str, chats_directory: str
    ) -> Optional[str]:
        """Resolve session file path with backward compatibility. (Issue #315 - extracted)"""
        # Try new naming convention first: {uuid}_chat.json
        chat_file = f"{chats_directory}/{session_id}_chat.json"
        file_exists = await run_in_chat_io_executor(os.path.exists, chat_file)
        if file_exists:
            return chat_file

        # Backward compatibility: try old naming convention
        chat_file_old = f"{chats_directory}/chat_{session_id}.json"
        old_file_exists = await run_in_chat_io_executor(os.path.exists, chat_file_old)
        if old_file_exists:
            logger.debug("Using legacy file format for session %s", session_id)
            return chat_file_old

        logger.warning("Chat session %s not found", session_id)
        return None

    async def _load_existing_chat_data(
        self, session_id: str, chat_file: str, chats_directory: str
    ) -> Dict[str, Any]:
        """Load existing chat data with backward compatibility. (Issue #315 - extracted)"""
        file_exists = await run_in_chat_io_executor(os.path.exists, chat_file)
        if file_exists:
            try:
                async with aiofiles.open(chat_file, "r", encoding="utf-8") as f:
                    file_content = await f.read()
                return self._decrypt_data(file_content)
            except Exception as e:
                logger.warning(
                    "Could not load existing chat data for %s: %s", session_id, e
                )
                return {}

        # Try old format for backward compatibility
        chat_file_old = f"{chats_directory}/chat_{session_id}.json"
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
        metadata: Optional[Dict[str, Any]],
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
        metadata: Optional[Dict[str, Any]],
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

            await self.memory_graph.create_conversation_entity(
                session_id=session_id, metadata=entity_metadata
            )

            logger.info("Created Memory Graph entity for session: %s", session_id)

        except Exception as e:
            logger.warning("Failed to create Memory Graph entity (continuing): %s", e)

    async def create_session(
        self,
        session_id: Optional[str] = None,
        title: Optional[str] = None,
        session_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
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

        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        session_title = title or session_name or f"Chat {session_id[:13]}"

        session_data = self._build_session_data(
            session_id, session_title, current_time, metadata
        )

        await self.save_session(session_id=session_id, messages=[], name=session_title)
        await self._create_memory_graph_entity(
            session_id, session_title, current_time, metadata
        )

        logger.info("Created new chat session: %s", session_id)
        return session_data

    async def _load_session_from_file(
        self, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Load and decrypt session data from file. Issue #620."""
        chats_directory = self._get_chats_directory()
        chat_file = await self._resolve_session_file_path(session_id, chats_directory)
        if not chat_file:
            return None

        async with aiofiles.open(chat_file, "r", encoding="utf-8") as f:
            file_content = await f.read()

        return self._decrypt_data(file_content)

    async def _process_loaded_messages(
        self, session_id: str, chat_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
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

        Args:
            session_id: The session identifier

        Returns:
            List of messages in the session
        """
        try:
            # Try Redis cache first (Issue #315 - uses helper)
            cached_messages = self._try_get_from_cache(session_id)
            if cached_messages is not None:
                return cached_messages

            logger.debug("Cache MISS for session %s", session_id)

            # Load from file (Issue #620 - uses helper)
            chat_data = await self._load_session_from_file(session_id)
            if chat_data is None:
                return []

            # Process messages (Issue #620 - uses helper)
            cleaned_messages = await self._process_loaded_messages(
                session_id, chat_data
            )

            # Warm up Redis cache with cleaned data
            await self._warm_cache_safe(session_id, chat_data)

            return cleaned_messages

        except Exception as e:
            logger.error("Error loading chat session %s: %s", session_id, e)
            return []

    async def _warm_cache_safe(
        self, session_id: str, chat_data: Dict[str, Any]
    ) -> None:
        """Warm up Redis cache safely. (Issue #315 - extracted)"""
        if not self.redis_client:
            return
        try:
            cache_key = f"chat:session:{session_id}"
            await self._async_cache_session(cache_key, chat_data)
            logger.debug("Warmed cache for session %s", session_id)
        except Exception as e:
            logger.error("Failed to warm cache: %s", e)

    async def _update_redis_cache_on_save(
        self, session_id: str, chat_data: Dict[str, Any]
    ) -> None:
        """Update Redis cache on session save. (Issue #315 - extracted)"""
        if not self.redis_client:
            return
        try:
            cache_key = f"chat:session:{session_id}"
            await self._async_cache_session(cache_key, chat_data)
            # Update recent chats sorted set for fast listing
            # Issue #361 - avoid blocking
            await run_in_chat_io_executor(
                self.redis_client.zadd, "chat:recent", {session_id: time.time()}
            )
            logger.debug("Cached session %s in Redis", session_id)
        except Exception as e:
            logger.error("Failed to cache session in Redis: %s", e)

    def _prepare_session_messages(
        self,
        session_id: str,
        messages: Optional[List[Dict[str, Any]]],
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
            logger.warning(
                f"Atomic write failed, falling back to direct write: {atomic_error}"
            )
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

    async def save_session(
        self,
        session_id: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        name: str = "",
    ):
        """
        Save a chat session with messages and metadata.

        Args:
            session_id: The identifier for the session to save.
            messages: The messages to save (defaults to empty list).
            name: Optional name for the chat session.

        Issue #665: Refactored to use extracted helper methods.
        """
        try:
            chats_directory = self._get_chats_directory()
            dir_exists = await run_in_chat_io_executor(os.path.exists, chats_directory)
            if not dir_exists:
                await run_in_chat_io_executor(
                    os.makedirs, chats_directory, exist_ok=True
                )

            chat_file = f"{chats_directory}/{session_id}_chat.json"
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")

            session_messages = self._prepare_session_messages(session_id, messages)

            chat_data = await self._load_existing_chat_data(
                session_id, chat_file, chats_directory
            )
            chat_data.update(
                {
                    "chatId": session_id,
                    "name": name or chat_data.get("name", ""),
                    "messages": session_messages,
                    "last_modified": current_time,
                    "created_time": chat_data.get("created_time", current_time),
                }
            )

            await self._write_session_to_storage(chat_file, chat_data)
            await self._update_redis_cache_on_save(session_id, chat_data)

            logger.info("Chat session '%s' saved successfully", session_id)

            if self.memory_graph_enabled and self.memory_graph:
                await self._update_memory_graph_entity(
                    session_id, session_messages, name, current_time
                )

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
                await self.memory_graph.add_observations(
                    entity_name=entity_name, observations=observations
                )
                logger.debug("Updated Memory Graph entity for session: %s", session_id)

            except (ValueError, RuntimeError) as e:
                if "Entity not found" in str(e):
                    logger.debug(
                        "Entity not found, creating new entity for session: %s",
                        session_id,
                    )
                    await self._create_memory_graph_entity_on_missing(
                        session_id, name, metadata, observations
                    )
                else:
                    raise

        except Exception as mg_error:
            logger.warning(
                "Failed to update Memory Graph entity (continuing): %s", mg_error
            )

    async def _delete_session_files(
        self, session_id: str, chats_directory: str
    ) -> bool:
        """
        Delete main session files (new and old format).

        Args:
            session_id: The session identifier.
            chats_directory: Path to the chats directory.

        Returns:
            True if at least one session file was deleted.

        Issue #620.
        """
        deleted = False

        # Delete new format file
        chat_file_new = f"{chats_directory}/{session_id}_chat.json"
        new_exists = await run_in_chat_io_executor(os.path.exists, chat_file_new)
        if new_exists:
            await run_in_chat_io_executor(os.remove, chat_file_new)
            deleted = True

        # Delete old format file if exists
        chat_file_old = f"{chats_directory}/chat_{session_id}.json"
        old_exists = await run_in_chat_io_executor(os.path.exists, chat_file_old)
        if old_exists:
            await run_in_chat_io_executor(os.remove, chat_file_old)
            deleted = True

        return deleted

    async def _delete_companion_files(
        self, session_id: str, chats_directory: str
    ) -> None:
        """
        Delete companion files (terminal logs, transcripts, etc.).

        Args:
            session_id: The session identifier.
            chats_directory: Path to the chats directory.

        Issue #620.
        """
        # Delete terminal log file
        terminal_log = f"{chats_directory}/{session_id}_terminal.log"
        log_exists = await run_in_chat_io_executor(os.path.exists, terminal_log)
        if log_exists:
            await run_in_chat_io_executor(os.remove, terminal_log)
            logger.debug("Deleted terminal log for session %s", session_id)

        # Delete terminal transcript file
        terminal_transcript = f"{chats_directory}/{session_id}_terminal_transcript.txt"
        transcript_exists = await run_in_chat_io_executor(
            os.path.exists, terminal_transcript
        )
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
            await run_in_chat_io_executor(
                self.redis_client.zrem, "chat:recent", session_id
            )
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

    async def _update_redis_session_cache(
        self, session_id: str, chat_data: Dict[str, Any]
    ) -> None:
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
            chats_directory = self._get_chats_directory()
            chat_file = await self._resolve_session_file_path(
                session_id, chats_directory
            )
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
            chat_file_new = f"{chats_directory}/{session_id}_chat.json"
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
            True if update was successful, False otherwise
        """
        try:
            chats_directory = self._get_chats_directory()

            # Try new format first
            chat_file = f"{chats_directory}/{session_id}_chat.json"
            file_exists = await run_in_chat_io_executor(os.path.exists, chat_file)
            if not file_exists:
                # Try old format
                chat_file = f"{chats_directory}/chat_{session_id}.json"
                old_exists = await run_in_chat_io_executor(os.path.exists, chat_file)
                if not old_exists:
                    logger.warning(
                        "Chat session %s not found for name update", session_id
                    )
                    return False

            # Load existing chat data
            async with aiofiles.open(chat_file, "r", encoding="utf-8") as f:
                file_content = await f.read()
            chat_data = json.loads(file_content)

            # Update name and last modified time
            chat_data["name"] = name
            chat_data["last_modified"] = time.strftime("%Y-%m-%d %H:%M:%S")

            # Save updated data (always use new format)
            chat_file_new = f"{chats_directory}/{session_id}_chat.json"
            async with aiofiles.open(chat_file_new, "w", encoding="utf-8") as f:
                await f.write(json.dumps(chat_data, indent=2, ensure_ascii=False))

            # Update Redis cache
            if self.redis_client:
                try:
                    cache_key = f"chat:session:{session_id}"
                    await self._async_cache_session(cache_key, chat_data)
                except Exception as e:
                    logger.error("Failed to update Redis cache: %s", e)

            logger.info("Chat session '%s' name updated to '%s'", session_id, name)
            return True

        except Exception as e:
            logger.error("Error updating chat session %s name: %s", session_id, e)
            return False

    async def get_session_owner(self, session_id: str) -> Optional[str]:
        """
        Get the owner/creator of a specific session.

        Args:
            session_id: The session identifier

        Returns:
            Username of session owner, or None if not found/set
        """
        try:
            chats_directory = self._get_chats_directory()
            chat_file = f"{chats_directory}/{session_id}_chat.json"

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
