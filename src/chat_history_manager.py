import fcntl
import gc
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiofiles

# Import Memory Graph for entity tracking
from src.autobot_memory_graph import AutoBotMemoryGraph
from src.constants.network_constants import NetworkConstants

# Import Context Window Manager for model-aware message limits
from src.context_window_manager import ContextWindowManager
from src.encryption_service import (
    decrypt_data,
    encrypt_data,
    get_encryption_service,
    is_encryption_enabled,
)

# Import the centralized ConfigManager and Redis client utility
from src.unified_config_manager import config as global_config_manager
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class ChatHistoryManager:
    def __init__(
        self,
        history_file: Optional[str] = None,
        use_redis: Optional[bool] = None,
        redis_host: Optional[str] = None,
        redis_port: Optional[int] = None,
    ):
        """
        Initializes the ChatHistoryManager with PERFORMANCE OPTIMIZATIONS.

        Args:
            history_file (str): Path to the JSON file for persistent storage.
            use_redis (bool): If True, attempts to use Redis for active memory
                storage for performance.
            redis_host (str): Hostname for Redis server.
            redis_port (int): Port for Redis server.
        """
        # Load configuration from centralized config manager
        data_config = global_config_manager.get("data", {})
        redis_config = global_config_manager.get_redis_config()

        # Set values using configuration with environment variable overrides
        self.history_file = history_file or data_config.get(
            "chat_history_file",
            os.getenv("AUTOBOT_CHAT_HISTORY_FILE", "data/chat_history.json"),
        )
        self.use_redis = (
            use_redis if use_redis is not None else redis_config.get("enabled", False)
        )
        # Use config system instead of hardcoded IP fallback
        # Local import to avoid circular dependency
        from src.unified_config_manager import UnifiedConfigManager
        unified_config = UnifiedConfigManager()
        self.redis_host = redis_host or redis_config.get(
            "host", os.getenv("REDIS_HOST", unified_config.get_host("redis"))
        )
        self.redis_port = redis_port or redis_config.get(
            "port",
            int(os.getenv("AUTOBOT_REDIS_PORT", str(NetworkConstants.REDIS_PORT))),
        )

        self.history: List[Dict[str, Any]] = []
        self.redis_client = None
        self.encryption_enabled = is_encryption_enabled()

        # PERFORMANCE OPTIMIZATION: Memory leak protection
        self.max_messages = 10000  # Maximum messages per session
        self.cleanup_threshold = 12000  # Cleanup trigger (120% of max)
        self.max_session_files = 1000  # Maximum session files to keep
        self.memory_check_counter = 0  # Counter for periodic memory checks
        self.memory_check_interval = 50  # Check memory every N operations

        # MEMORY GRAPH INTEGRATION: Entity tracking for conversations
        self.memory_graph: Optional[AutoBotMemoryGraph] = None
        self.memory_graph_enabled = False  # Track initialization status

        # CONTEXT WINDOW MANAGEMENT: Model-aware message limits
        self.context_manager = ContextWindowManager()

        logger.info(
            f"PERFORMANCE: ChatHistoryManager initialized with memory protection - "
            f"max_messages: {self.max_messages}, cleanup_threshold: {self.cleanup_threshold}"
        )
        logger.info(f"✅ Context window manager initialized with model-aware limits")

        # Log encryption status
        if self.encryption_enabled:
            logging.info("Chat history encryption is ENABLED")
            try:
                # Verify encryption service is available
                encryption_service = get_encryption_service()
                key_info = encryption_service.get_key_info()
                logging.info(f"Encryption service initialized: {key_info['algorithm']}")
            except Exception as e:
                logging.error(f"Failed to initialize encryption service: {e}")
                self.encryption_enabled = False
        else:
            logging.info("Chat history encryption is DISABLED")

        if self.use_redis:
            # Use centralized Redis client utility
            self.redis_client = get_redis_client(async_client=False)
            if self.redis_client:
                logging.info(
                    "Redis connection established via centralized utility "
                    "for active memory storage."
                )
            else:
                logging.error(
                    "Failed to get Redis client from centralized utility. "
                    "Falling back to file storage."
                )
                self.use_redis = False

        self._ensure_data_directory_exists()
        self._load_history()

        # MEMORY GRAPH: Try to initialize asynchronously (non-blocking)
        # Actual initialization happens in async context
        logger.info(
            "ChatHistoryManager ready (Memory Graph will initialize on first async operation)"
        )

    async def _init_memory_graph(self):
        """
        Initialize Memory Graph for conversation entity tracking.

        This is called asynchronously during first session operation.
        Non-blocking - failures are logged but don't prevent normal operation.
        """
        if self.memory_graph_enabled or self.memory_graph is not None:
            return  # Already initialized

        try:
            logger.info("Initializing Memory Graph for conversation tracking...")

            self.memory_graph = AutoBotMemoryGraph(chat_history_manager=self)

            # Attempt async initialization
            initialized = await self.memory_graph.initialize()

            if initialized:
                self.memory_graph_enabled = True
                logger.info(
                    "✅ Memory Graph initialized successfully for conversation tracking"
                )
            else:
                logger.warning(
                    "⚠️ Memory Graph initialization returned False - conversation entity tracking disabled"
                )
                self.memory_graph = None

        except Exception as e:
            logger.warning(
                f"⚠️ Failed to initialize Memory Graph (continuing without entity tracking): {e}"
            )
            self.memory_graph = None
            self.memory_graph_enabled = False

    def _ensure_data_directory_exists(self):
        """Ensures the directory for the history file exists."""
        data_dir = os.path.dirname(self.history_file)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)

    def _extract_conversation_metadata(
        self, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extract metadata from conversation messages for Memory Graph entity.

        Args:
            messages: List of conversation messages

        Returns:
            Dictionary with extracted metadata (topics, entities, summary)
        """
        try:
            if not messages:
                return {
                    "topics": [],
                    "entity_mentions": [],
                    "summary": "Empty conversation",
                }

            # Extract text from all messages
            all_text = []
            user_messages = []
            bot_messages = []

            for msg in messages:
                sender = msg.get("sender", "")
                text = msg.get("text", "")

                all_text.append(text)

                if sender == "user":
                    user_messages.append(text)
                elif sender == "bot" or sender == "assistant":
                    bot_messages.append(text)

            # Topic extraction (simple keyword-based)
            topics = self._extract_topics(all_text)

            # Entity mention detection
            entity_mentions = self._detect_entity_mentions(all_text)

            # Generate summary
            summary = self._generate_conversation_summary(user_messages, bot_messages)

            return {
                "topics": topics,
                "entity_mentions": entity_mentions,
                "summary": summary,
                "message_count": len(messages),
                "user_message_count": len(user_messages),
                "bot_message_count": len(bot_messages),
            }

        except Exception as e:
            logger.warning(f"Failed to extract conversation metadata: {e}")
            return {
                "topics": [],
                "entity_mentions": [],
                "summary": "Metadata extraction failed",
                "message_count": len(messages) if messages else 0,
                "user_message_count": 0,
                "bot_message_count": 0,
            }

    def _extract_topics(self, text_list: List[str]) -> List[str]:
        """Extract topics from conversation text using keyword detection."""
        topics = set()

        # Combine all text
        combined_text = " ".join(text_list).lower()

        # Topic detection patterns
        topic_patterns = {
            "installation": ["install", "setup", "configure", "deployment"],
            "troubleshooting": ["error", "issue", "problem", "fix", "debug"],
            "architecture": ["architecture", "design", "vm", "distributed", "service"],
            "api": ["api", "endpoint", "request", "integration"],
            "knowledge_base": ["knowledge", "document", "upload", "vectorize"],
            "chat": ["chat", "conversation", "message", "response"],
            "redis": ["redis", "cache", "database"],
            "frontend": ["frontend", "vue", "ui", "interface"],
            "backend": ["backend", "fastapi", "python"],
            "security": ["security", "authentication", "encryption"],
        }

        for topic, keywords in topic_patterns.items():
            if any(keyword in combined_text for keyword in keywords):
                topics.add(topic)

        return list(topics)

    def _detect_entity_mentions(self, text_list: List[str]) -> List[str]:
        """Detect mentions of bugs, features, tasks in conversation."""
        mentions = set()

        combined_text = " ".join(text_list).lower()

        # Bug mention patterns
        if re.search(r"bug|issue|error|problem|fix", combined_text):
            mentions.add("bug_mention")

        # Feature mention patterns
        if re.search(r"feature|implement|add|new|enhancement", combined_text):
            mentions.add("feature_mention")

        # Task mention patterns
        if re.search(r"task|todo|need to|should|must", combined_text):
            mentions.add("task_mention")

        # Decision mention patterns
        if re.search(r"decide|decision|choose|select|prefer", combined_text):
            mentions.add("decision_mention")

        return list(mentions)

    def _generate_conversation_summary(
        self, user_messages: List[str], bot_messages: List[str]
    ) -> str:
        """Generate brief summary of conversation."""
        if not user_messages:
            return "No user messages"

        # Get first and last user messages for context
        first_msg = user_messages[0][:100] if user_messages else ""
        last_msg = user_messages[-1][:100] if len(user_messages) > 1 else ""

        if len(user_messages) == 1:
            return f"Single exchange: {first_msg}..."
        else:
            return f"Conversation started with: {first_msg}... ({len(user_messages)} user messages)"

    def _cleanup_messages_if_needed(self):
        """PERFORMANCE OPTIMIZATION: Clean up messages to prevent memory leaks"""
        if len(self.history) > self.cleanup_threshold:
            # Keep most recent messages within the limit
            old_count = len(self.history)
            self.history = self.history[-self.max_messages :]

            # Force garbage collection to free memory immediately
            collected_objects = gc.collect()

            logger.info(
                f"CHAT CLEANUP: Trimmed messages from {old_count} to {len(self.history)} "
                f"(limit: {self.max_messages}), collected {collected_objects} objects"
            )

    def _periodic_memory_check(self):
        """PERFORMANCE OPTIMIZATION: Periodic memory usage monitoring"""
        self.memory_check_counter += 1
        if self.memory_check_counter >= self.memory_check_interval:
            self.memory_check_counter = 0

            # Check memory usage
            message_count = len(self.history)
            if message_count > self.max_messages * 0.8:  # 80% threshold warning
                logger.warning(
                    f"MEMORY WARNING: Chat history approaching limit - "
                    f"{message_count}/{self.max_messages} messages "
                    f"({(message_count/self.max_messages)*100:.1f}%)"
                )

            # Cleanup if needed
            self._cleanup_messages_if_needed()

    def _cleanup_old_session_files(self):
        """PERFORMANCE OPTIMIZATION: Clean up old session files"""
        try:
            chats_directory = self._get_chats_directory()
            if not os.path.exists(chats_directory):
                return

            # Get all chat files sorted by modification time
            chat_files = []
            for filename in os.listdir(chats_directory):
                if filename.startswith("chat_") and filename.endswith(".json"):
                    file_path = os.path.join(chats_directory, filename)
                    mtime = os.path.getmtime(file_path)
                    chat_files.append((file_path, mtime, filename))

            # Sort by modification time (newest first)
            chat_files.sort(key=lambda x: x[1], reverse=True)

            # Remove old files if exceeding limit
            if len(chat_files) > self.max_session_files:
                files_to_remove = chat_files[self.max_session_files :]
                for file_path, _, filename in files_to_remove:
                    try:
                        os.remove(file_path)
                        logger.info(f"CLEANUP: Removed old session file: {filename}")
                    except Exception as e:
                        logger.error(f"Failed to remove session file {filename}: {e}")

                logger.info(
                    f"SESSION CLEANUP: Removed {len(files_to_remove)} old session files, "
                    f"kept {self.max_session_files} most recent"
                )

        except Exception as e:
            logger.error(f"Error cleaning up session files: {e}")

    def _encrypt_data(self, data: Dict[str, Any]) -> str:
        """Encrypt chat data if encryption is enabled."""
        if not self.encryption_enabled:
            return json.dumps(data, indent=2)

        try:
            return encrypt_data(data)
        except Exception as e:
            logging.error(f"Failed to encrypt chat data: {e}")
            # Fall back to unencrypted storage with warning
            logging.warning(
                "Falling back to unencrypted storage due to encryption failure"
            )
            return json.dumps(data, indent=2)

    def _decrypt_data(self, data_str: str) -> Dict[str, Any]:
        """Decrypt chat data if it's encrypted."""
        if not self.encryption_enabled:
            return json.loads(data_str)

        try:
            # Check if data is encrypted (base64-like format)
            encryption_service = get_encryption_service()
            if encryption_service.is_encrypted(data_str):
                return decrypt_data(data_str, as_json=True)
            else:
                # Legacy unencrypted data
                logging.debug("Loading legacy unencrypted chat data")
                return json.loads(data_str)
        except Exception as e:
            logging.error(f"Failed to decrypt chat data: {e}")
            # Try as unencrypted JSON as fallback
            try:
                return json.loads(data_str)
            except json.JSONDecodeError:
                logging.error("Data is neither valid encrypted nor JSON format")
                raise ValueError(
                    "Cannot decode chat data - corrupted or invalid format"
                )

    def _get_chats_directory(self) -> str:
        """Get the chats directory path from configuration."""
        data_config = global_config_manager.get("data", {})
        return data_config.get(
            "chats_directory",
            os.getenv("AUTOBOT_CHATS_DIRECTORY", "data/chats"),
        )

    async def _async_cache_session(self, cache_key: str, chat_data: Dict[str, Any]):
        """
        Helper method to cache session data in Redis asynchronously.

        Args:
            cache_key: Redis key for the session
            chat_data: Session data to cache
        """
        try:
            # Redis sync client expects sync operations
            self.redis_client.setex(
                cache_key, 3600, json.dumps(chat_data)  # 1 hour TTL
            )
        except Exception as e:
            logger.error(f"Failed to cache session data: {e}")

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
                logger.warning(f"No messages found in session {session_id}")
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
                f"Added {tool_type} tool marker to last message in session {session_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to add tool marker to session {session_id}: {e}")
            return False

    def _load_history(self):
        """
        DEPRECATED: Legacy chat history loading (for backward compatibility only).

        Modern architecture uses per-session files in data/chats/ directory.
        self.history should remain EMPTY to prevent data pollution when
        save_session() is called without explicit messages.

        CRITICAL FIX: Do NOT load old chat_history.json into self.history
        as it causes historical messages to leak into new sessions.
        """
        # BUG FIX: Initialize with empty history instead of loading old data
        # Loading chat_history.json was causing 91+ old messages to pollute new sessions
        self.history = []

        logging.info(
            "ChatHistoryManager initialized with EMPTY default history. "
            "All sessions are managed independently in data/chats/ directory."
        )

        # Check if obsolete chat_history.json exists and warn
        if os.path.exists(self.history_file):
            logging.warning(
                f"⚠️  Legacy chat_history.json file exists at {self.history_file}. "
                "This file is NO LONGER USED. Sessions are stored in data/chats/ directory. "
                "Consider archiving this file to prevent confusion."
            )

    async def _save_history(self):
        """
        Saves current chat history to the JSON file and optionally to Redis
        if enabled.

        PERFORMANCE OPTIMIZATION: Includes memory cleanup before save.
        """
        # PERFORMANCE: Check and cleanup memory before saving
        self._periodic_memory_check()

        # Save to file for persistence
        try:
            async with aiofiles.open(self.history_file, "w") as f:
                await f.write(json.dumps(self.history, indent=2))
        except Exception as e:
            logging.error(f"Error saving chat history to {self.history_file}: {str(e)}")

        # Also save to Redis if enabled for fast access
        if self.use_redis and self.redis_client:
            try:
                self.redis_client.set("autobot:chat_history", json.dumps(self.history))
                # Optionally set expiration time (e.g., 1 day) to clean up
                # old data
                self.redis_client.expire("autobot:chat_history", 86400)
            except Exception as e:
                logging.error(f"Error saving chat history to Redis: {str(e)}")

    async def create_session(
        self,
        session_id: Optional[str] = None,
        title: Optional[str] = None,
        session_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Creates a new chat session.

        Args:
            session_id (str): Optional session ID (auto-generated if not provided).
            title (str): Optional title for the session.
            session_name (str): Optional name for the session (backward compatibility).
            metadata (Dict[str, Any]): Optional metadata for the session.

        Returns:
            Dict[str, Any]: Session data including session_id, title, etc.
        """
        import uuid

        # Initialize Memory Graph if not already done
        await self._init_memory_graph()

        # Generate session ID if not provided
        if not session_id:
            session_id = f"chat-{int(time.time() * 1000)}-{str(uuid.uuid4())[:8]}"

        current_time = time.strftime("%Y-%m-%d %H:%M:%S")

        # Use title, or session_name (for backward compatibility), or auto-generate
        session_title = title or session_name or f"Chat {session_id[:13]}"

        # Prepare session data
        session_data = {
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

        # Create session with initial metadata
        await self.save_session(session_id=session_id, messages=[], name=session_title)

        # MEMORY GRAPH: Create conversation entity (non-blocking)
        if self.memory_graph_enabled and self.memory_graph:
            try:
                entity_metadata = {
                    "session_id": session_id,
                    "title": session_title,
                    "created_at": current_time,
                    "status": "active",
                    "priority": "medium",
                }

                # Merge user-provided metadata
                if metadata:
                    entity_metadata.update(metadata)

                # Create conversation entity
                await self.memory_graph.create_conversation_entity(
                    session_id=session_id, metadata=entity_metadata
                )

                logger.info(f"✅ Created Memory Graph entity for session: {session_id}")

            except Exception as e:
                logger.warning(
                    f"⚠️ Failed to create Memory Graph entity (continuing): {e}"
                )

        logging.info(f"Created new chat session: {session_id}")
        return session_data

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
            limit (Optional[int]): Maximum number of messages to return. If None, uses model-aware default.
            model_name (Optional[str]): LLM model name for context-aware limiting.

        Returns:
            List[Dict[str, Any]]: List of messages in the session.
        """
        messages = await self.load_session(session_id)

        # Use model-aware limit if not explicitly provided
        if limit is None:
            limit = self.context_manager.calculate_retrieval_limit(model_name)
            logger.debug(
                f"Using model-aware limit: {limit} messages for model {model_name or 'default'}"
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

    async def get_session_owner(self, session_id: str) -> Optional[str]:
        """
        Gets the owner/creator of a specific session.

        Args:
            session_id (str): The session identifier.

        Returns:
            Optional[str]: Username of session owner, or None if not found/set.
        """
        try:
            chats_directory = self._get_chats_directory()
            chat_file = f"{chats_directory}/{session_id}_chat.json"

            # Try new format first
            if os.path.exists(chat_file):
                async with aiofiles.open(chat_file, "r") as f:
                    file_content = await f.read()
                chat_data = self._decrypt_data(file_content)

                # Check metadata for owner field
                metadata = chat_data.get("metadata", {})
                return metadata.get("owner") or metadata.get("username")

        except Exception as e:
            logger.warning(f"Failed to get session owner for {session_id}: {e}")

        return None

    async def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """
        Updates session metadata (name, etc).

        Args:
            session_id (str): The session identifier.
            updates (Dict[str, Any]): Dictionary of fields to update.

        Returns:
            bool: True if update successful, False otherwise.
        """
        try:
            chats_directory = self._get_chats_directory()

            # Try new format first
            chat_file = f"{chats_directory}/{session_id}_chat.json"
            if not os.path.exists(chat_file):
                # Try old format
                chat_file = f"{chats_directory}/chat_{session_id}.json"
                if not os.path.exists(chat_file):
                    logging.warning(f"Session {session_id} not found for update")
                    return False

            # Load existing data
            async with aiofiles.open(chat_file, "r") as f:
                file_content = await f.read()
            chat_data = self._decrypt_data(file_content)

            # Update fields
            chat_data.update(updates)
            chat_data["last_modified"] = time.strftime("%Y-%m-%d %H:%M:%S")

            # Save updated data (always use new format)
            chat_file_new = f"{chats_directory}/{session_id}_chat.json"
            encrypted_data = self._encrypt_data(chat_data)
            async with aiofiles.open(chat_file_new, "w") as f:
                await f.write(encrypted_data)

            # Update Redis cache
            if self.redis_client:
                try:
                    cache_key = f"chat:session:{session_id}"
                    await self._async_cache_session(cache_key, chat_data)
                except Exception as e:
                    logger.error(f"Failed to update Redis cache: {e}")

            logging.info(f"Session {session_id} updated successfully")
            return True

        except Exception as e:
            logging.error(f"Error updating session {session_id}: {e}")
            return False

    async def export_session(
        self, session_id: str, format: str = "json"
    ) -> Optional[str]:
        """
        Exports a session in the specified format.

        Args:
            session_id (str): The session identifier.
            format (str): Export format ('json', 'txt', 'md').

        Returns:
            Optional[str]: Exported data as string, or None on error.
        """
        try:
            messages = await self.load_session(session_id)

            if format == "json":
                return json.dumps(messages, indent=2)
            elif format == "txt":
                lines = []
                for msg in messages:
                    timestamp = msg.get("timestamp", "")
                    sender = msg.get("sender", "unknown")
                    text = msg.get("text", "")
                    lines.append(f"[{timestamp}] {sender}: {text}")
                return "\n".join(lines)
            elif format == "md":
                lines = [f"# Chat Session: {session_id}\n"]
                for msg in messages:
                    timestamp = msg.get("timestamp", "")
                    sender = msg.get("sender", "unknown")
                    text = msg.get("text", "")
                    lines.append(f"**{sender}** ({timestamp}):\n{text}\n")
                return "\n".join(lines)
            else:
                logging.error(f"Unsupported export format: {format}")
                return None

        except Exception as e:
            logging.error(f"Error exporting session {session_id}: {e}")
            return None

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
        """
        message = {
            "sender": sender,
            "text": text,
            "messageType": message_type,
            "metadata": raw_data,  # CRITICAL FIX: Use 'metadata' to match frontend expectations
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Add tool markers if provided
        if tool_markers:
            message["toolMarkers"] = tool_markers

        # If session_id provided, add to that session
        if session_id:
            try:
                messages = await self.load_session(session_id)
                messages.append(message)
                await self.save_session(session_id, messages=messages)
                logging.debug(f"Added message to session {session_id}")
                return
            except Exception as e:
                logging.error(f"Error adding message to session {session_id}: {e}")
                # Fall through to add to default history

        # Otherwise add to default history
        self.history.append(message)

        # PERFORMANCE: Periodic memory checks
        self._periodic_memory_check()

        await self._save_history()
        logging.debug(f"Added message from {sender} with type {message_type}")

    def get_all_messages(self) -> List[Dict[str, Any]]:
        """Returns the entire chat history."""
        return self.history

    async def update_message_metadata(
        self,
        session_id: str,
        metadata_filter: Dict[str, Any],
        metadata_updates: Dict[str, Any]
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

            # Find message matching all filter criteria
            for message in messages:
                msg_metadata = message.get("metadata", {})

                # Check if all filter criteria match
                matches = all(
                    msg_metadata.get(key) == value
                    for key, value in metadata_filter.items()
                )

                if matches:
                    # Update metadata
                    if "metadata" not in message:
                        message["metadata"] = {}

                    message["metadata"].update(metadata_updates)

                    # Save updated messages
                    await self.save_session(session_id, messages=messages)

                    logging.info(
                        f"Updated message metadata in session {session_id}: "
                        f"filter={metadata_filter}, updates={metadata_updates}"
                    )
                    return True

            logging.warning(
                f"No message found matching metadata filter in session {session_id}: {metadata_filter}"
            )
            return False

        except Exception as e:
            logging.error(f"Error updating message metadata in session {session_id}: {e}")
            return False

    async def clear_history(self):
        """
        Clears the entire chat history and saves the empty history to file.

        PERFORMANCE OPTIMIZATION: Forces garbage collection after clear.
        """
        old_count = len(self.history)
        self.history = []

        # Force garbage collection to free memory
        collected_objects = gc.collect()

        await self._save_history()
        logging.info(
            f"Chat history cleared: removed {old_count} messages, "
            f"collected {collected_objects} objects"
        )

    async def list_sessions(self) -> List[Dict[str, Any]]:
        """Lists available chat sessions with their metadata."""
        try:
            sessions = []
            chats_directory = self._get_chats_directory()

            # Ensure chats directory exists
            if not os.path.exists(chats_directory):
                os.makedirs(chats_directory, exist_ok=True)
                return sessions

            # Clean up old session files if needed
            self._cleanup_old_session_files()

            # Look for chat files in the chats directory (both old and new formats)
            for filename in os.listdir(chats_directory):
                # Support both formats: chat_{uuid}.json and {uuid}_chat.json
                chat_id = None
                if filename.startswith("chat_") and filename.endswith(".json"):
                    # Old format: chat_{uuid}.json
                    chat_id = filename.replace("chat_", "").replace(".json", "")
                elif filename.endswith("_chat.json"):
                    # New format: {uuid}_chat.json
                    chat_id = filename.replace("_chat.json", "")

                if not chat_id:
                    continue

                chat_path = os.path.join(chats_directory, filename)

                try:
                    async with aiofiles.open(chat_path, "r") as f:
                        file_content = await f.read()
                        chat_data = self._decrypt_data(file_content)

                        # Get chat metadata
                        chat_name = chat_data.get("name", "")
                        chat_messages = chat_data.get("messages", [])
                        created_time = chat_data.get("created_time", "")
                        last_modified = chat_data.get("last_modified", "")

                        sessions.append(
                            {
                                "chatId": chat_id,
                                "name": chat_name,
                                "messageCount": len(chat_messages),
                                "createdTime": created_time,
                                "lastModified": last_modified,
                            }
                        )
                except Exception as e:
                    logging.error(f"Error reading chat file {filename}: {str(e)}")
                    continue

            # Sort by last modified time (most recent first)
            sessions.sort(key=lambda x: x.get("lastModified", ""), reverse=True)
            return sessions

        except Exception as e:
            logging.error(f"Error listing chat sessions: {str(e)}")
            return []

    def list_sessions_fast(self) -> List[Dict[str, Any]]:
        """Fast listing of chat sessions using file metadata only (no decryption)."""
        try:
            sessions = []
            chats_directory = self._get_chats_directory()

            # Ensure chats directory exists
            if not os.path.exists(chats_directory):
                os.makedirs(chats_directory, exist_ok=True)
                return sessions

            # Use file system metadata for performance - avoid decryption
            # Support both formats: chat_{uuid}.json and {uuid}_chat.json
            for filename in os.listdir(chats_directory):
                chat_id = None
                if filename.startswith("chat_") and filename.endswith(".json"):
                    # Old format: chat_{uuid}.json
                    chat_id = filename.replace("chat_", "").replace(".json", "")
                elif filename.endswith("_chat.json"):
                    # New format: {uuid}_chat.json
                    chat_id = filename.replace("_chat.json", "")

                if not chat_id:
                    continue

                chat_path = os.path.join(chats_directory, filename)

                try:
                    # Get file stats for metadata
                    stat = os.stat(chat_path)
                    created_time = datetime.fromtimestamp(stat.st_ctime).isoformat()
                    last_modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
                    file_size = stat.st_size

                    # Read chat name and message count from file (lightweight, no full decryption)
                    chat_name = None
                    message_count = 0
                    try:
                        with open(chat_path, "r", encoding="utf-8") as f:
                            chat_data = json.load(f)
                            chat_name = chat_data.get("name", "").strip()
                            messages = chat_data.get("messages", [])
                            message_count = (
                                len(messages) if isinstance(messages, list) else 0
                            )
                    except Exception as read_err:
                        logging.debug(
                            f"Could not read chat file content for {filename}: {read_err}"
                        )

                    # Create unique chat names using timestamp or full UUID
                    if not chat_name:  # Only generate default if no name in file
                        if chat_id.startswith("chat-") and len(chat_id) > 15:
                            # For timestamp-based IDs, use the last 8 digits for uniqueness
                            unique_part = chat_id[-8:]
                            chat_name = f"Chat {unique_part}"
                        elif len(chat_id) >= 8:
                            # For UUID-based IDs, use first 8 characters
                            chat_name = f"Chat {chat_id[:8]}"
                        else:
                            # Fallback for short IDs
                            chat_name = f"Chat {chat_id}"

                    sessions.append(
                        {
                            # Frontend-compatible property names
                            "id": chat_id,  # Frontend expects 'id'
                            "chatId": chat_id,  # Keep for backward compatibility
                            "title": chat_name,  # Frontend expects 'title' - use actual name from file
                            "name": chat_name,  # Keep for backward compatibility
                            "messages": [],  # Frontend expects messages array - empty in fast mode
                            "messageCount": message_count,  # Actual count from file
                            "createdAt": created_time,  # Frontend expects 'createdAt'
                            "createdTime": created_time,  # Keep for backward compatibility
                            "updatedAt": last_modified,  # Frontend expects 'updatedAt'
                            "lastModified": last_modified,  # Keep for backward compatibility
                            "isActive": False,  # Frontend expects 'isActive'
                            "fileSize": file_size,
                            "fast_mode": True,  # Indicate this is fast mode without full data
                        }
                    )
                except Exception as e:
                    logging.error(f"Error reading file stats for {filename}: {str(e)}")
                    continue

            # CRITICAL: Detect orphaned terminal files and auto-create chat sessions
            # This ensures terminal logs/transcripts without chat.json appear in GUI
            existing_chat_ids = {session["id"] for session in sessions}

            # Scan for orphaned terminal files
            orphaned_sessions_created = 0
            for filename in os.listdir(chats_directory):
                session_id = None

                # Check for terminal log files
                if filename.endswith("_terminal.log"):
                    session_id = filename.replace("_terminal.log", "")
                # Check for terminal transcript files
                elif filename.endswith("_terminal_transcript.txt"):
                    session_id = filename.replace("_terminal_transcript.txt", "")

                # If we found a terminal file and no corresponding chat exists
                if session_id and session_id not in existing_chat_ids:
                    try:
                        # Create minimal empty chat.json for this orphaned terminal session
                        chat_file = os.path.join(chats_directory, f"{session_id}_chat.json")

                        # Only create if it doesn't already exist
                        if not os.path.exists(chat_file):
                            empty_chat = {
                                "id": session_id,
                                "name": f"Terminal Session {session_id[:8]}",
                                "messages": [],
                                "created_at": datetime.now().isoformat(),
                                "metadata": {
                                    "auto_created": True,
                                    "reason": "orphaned_terminal_files",
                                    "source": f"Found {filename}"
                                }
                            }

                            with open(chat_file, "w", encoding="utf-8") as f:
                                json.dump(empty_chat, f, indent=2, ensure_ascii=False)

                            # Add to existing_chat_ids to prevent duplicates
                            existing_chat_ids.add(session_id)
                            orphaned_sessions_created += 1

                            # Get file stats for the newly created chat
                            stat = os.stat(chat_file)
                            created_time = datetime.fromtimestamp(stat.st_ctime).isoformat()
                            last_modified = datetime.fromtimestamp(stat.st_mtime).isoformat()

                            # Add to sessions list
                            sessions.append({
                                "id": session_id,
                                "chatId": session_id,
                                "title": f"Terminal Session {session_id[:8]}",
                                "name": f"Terminal Session {session_id[:8]}",
                                "messages": [],
                                "messageCount": 0,
                                "createdAt": created_time,
                                "createdTime": created_time,
                                "updatedAt": last_modified,
                                "lastModified": last_modified,
                                "isActive": False,
                                "fileSize": stat.st_size,
                                "fast_mode": True,
                                "auto_created": True,  # Mark as auto-created
                            })

                            logging.info(
                                f"Auto-created chat session for orphaned terminal file: {session_id} (from {filename})"
                            )

                    except Exception as create_err:
                        logging.error(
                            f"Failed to auto-create chat session for orphaned {filename}: {create_err}"
                        )
                        continue

            if orphaned_sessions_created > 0:
                logging.info(
                    f"✅ Auto-created {orphaned_sessions_created} chat sessions for orphaned terminal files"
                )

            # Sort by last modified time (most recent first)
            sessions.sort(key=lambda x: x.get("lastModified", ""), reverse=True)
            return sessions

        except Exception as e:
            logging.error(f"Error listing chat sessions (fast mode): {str(e)}")
            return []

    async def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Loads a specific chat session with Redis cache-first strategy."""
        try:
            # Try Redis cache first
            if self.redis_client:
                try:
                    cache_key = f"chat:session:{session_id}"
                    cached_data = self.redis_client.get(cache_key)

                    if cached_data:
                        if isinstance(cached_data, bytes):
                            cached_data = cached_data.decode("utf-8")
                        chat_data = json.loads(cached_data)
                        logger.debug(f"Cache HIT for session {session_id}")
                        return chat_data.get("messages", [])
                except Exception as e:
                    logger.error(f"Failed to read from Redis cache: {e}")

            logger.debug(f"Cache MISS for session {session_id}")

            # Cache miss - read from file
            chats_directory = self._get_chats_directory()

            # Try new naming convention first: {uuid}_chat.json
            chat_file = f"{chats_directory}/{session_id}_chat.json"

            # Backward compatibility: try old naming convention if new doesn't exist
            if not os.path.exists(chat_file):
                chat_file_old = f"{chats_directory}/chat_{session_id}.json"
                if os.path.exists(chat_file_old):
                    chat_file = chat_file_old
                    logger.debug(f"Using legacy file format for session {session_id}")
                else:
                    logging.warning(f"Chat session {session_id} not found")
                    return []

            async with aiofiles.open(chat_file, "r") as f:
                file_content = await f.read()

            # Decrypt data if encryption is enabled
            chat_data = self._decrypt_data(file_content)

            # Warm up Redis cache with file data
            if self.redis_client:
                try:
                    cache_key = f"chat:session:{session_id}"
                    await self._async_cache_session(cache_key, chat_data)
                    logger.debug(f"Warmed cache for session {session_id}")
                except Exception as e:
                    logger.error(f"Failed to warm cache: {e}")

            return chat_data.get("messages", [])

        except Exception as e:
            logging.error(f"Error loading chat session {session_id}: {str(e)}")
            return []

    async def _atomic_write(self, file_path: str, content: str) -> None:
        """
        Atomic file write with exclusive locking to prevent data corruption.

        Uses fcntl.flock() for process-level locking and atomic rename to ensure
        that concurrent writes don't corrupt the file. The file is written to a
        temporary file in the same directory, then atomically renamed.

        Args:
            file_path: Target file path
            content: Content to write

        Raises:
            Exception: If write fails (temp file is cleaned up automatically)
        """
        dir_path = os.path.dirname(file_path)

        # Create temporary file in same directory (required for atomic rename)
        fd, temp_path = tempfile.mkstemp(dir=dir_path, prefix='.tmp_chat_', suffix='.json')

        try:
            # Acquire exclusive lock on the file descriptor
            fcntl.flock(fd, fcntl.LOCK_EX)

            # Write content to temporary file using aiofiles for async I/O
            os.close(fd)  # Close fd so aiofiles can open it
            async with aiofiles.open(temp_path, 'w') as f:
                await f.write(content)

            # Atomic rename (cross-platform atomic operation)
            os.replace(temp_path, file_path)

            logger.debug(f"Atomic write completed: {file_path}")

        except Exception as e:
            # Cleanup temporary file on failure
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp file {temp_path}: {cleanup_error}")

            logger.error(f"Atomic write failed for {file_path}: {e}")
            raise e

    async def save_session(
        self,
        session_id: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        name: str = "",
    ):
        """
        Saves a chat session with messages and metadata.

        PERFORMANCE OPTIMIZATION: Includes session file cleanup.

        Args:
            session_id (str): The identifier for the session to save.
            messages (Optional[List[Dict[str, Any]]]): The messages to save
                (defaults to current history).
            name (str): Optional name for the chat session.
        """
        try:
            # Ensure chats directory exists
            chats_directory = self._get_chats_directory()
            if not os.path.exists(chats_directory):
                os.makedirs(chats_directory, exist_ok=True)

            # Use new naming convention: {uuid}_chat.json
            chat_file = f"{chats_directory}/{session_id}_chat.json"
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")

            # Use provided messages or empty list (NEVER use self.history as default)
            # BUG FIX: Previously defaulted to self.history which contained ALL historical
            # messages from old chat_history.json, causing new sessions to be polluted
            session_messages = messages if messages is not None else []

            # PERFORMANCE: Limit session messages to prevent excessive file sizes
            if len(session_messages) > self.max_messages:
                logger.warning(
                    f"Session {session_id} has {len(session_messages)} messages, "
                    f"truncating to {self.max_messages} most recent"
                )
                session_messages = session_messages[-self.max_messages :]

            # Load existing chat data if it exists to preserve metadata
            chat_data = {}

            # Check new format first, then old format for backward compatibility
            if os.path.exists(chat_file):
                try:
                    async with aiofiles.open(chat_file, "r") as f:
                        file_content = await f.read()
                    chat_data = self._decrypt_data(file_content)
                except Exception as e:
                    logging.warning(
                        "Could not load existing chat data for "
                        f"{session_id}: {str(e)}"
                    )
            else:
                # Try old format for backward compatibility
                chat_file_old = f"{chats_directory}/chat_{session_id}.json"
                if os.path.exists(chat_file_old):
                    try:
                        async with aiofiles.open(chat_file_old, "r") as f:
                            file_content = await f.read()
                        chat_data = self._decrypt_data(file_content)
                        logger.debug(f"Migrating session {session_id} from old format")
                    except Exception as e:
                        logging.warning(f"Could not load old format data: {str(e)}")

            # Update chat data
            chat_data.update(
                {
                    "chatId": session_id,
                    "name": name or chat_data.get("name", ""),
                    "messages": session_messages,
                    "last_modified": current_time,
                    "created_time": chat_data.get("created_time", current_time),
                }
            )

            # Save to file with encryption if enabled (always use new format)
            # Use atomic write to prevent corruption from concurrent saves
            encrypted_data = self._encrypt_data(chat_data)
            try:
                await self._atomic_write(chat_file, encrypted_data)
            except Exception as atomic_error:
                # Fallback to direct write if atomic write fails
                logger.warning(f"Atomic write failed, falling back to direct write: {atomic_error}")
                async with aiofiles.open(chat_file, "w") as f:
                    await f.write(encrypted_data)

            # Update Redis cache (write-through)
            if self.redis_client:
                try:
                    cache_key = f"chat:session:{session_id}"
                    await self._async_cache_session(cache_key, chat_data)

                    # Update recent chats sorted set for fast listing
                    self.redis_client.zadd("chat:recent", {session_id: time.time()})

                    logger.debug(f"Cached session {session_id} in Redis")
                except Exception as e:
                    logger.error(f"Failed to cache session in Redis: {e}")

            logging.info(f"Chat session '{session_id}' saved successfully")

            # MEMORY GRAPH: Update conversation entity with observations (non-blocking)
            if self.memory_graph_enabled and self.memory_graph:
                try:
                    # Extract metadata from conversation
                    metadata = self._extract_conversation_metadata(session_messages)

                    # Find entity by session_id
                    entity_name = f"Conversation {session_id[:8]}"

                    # Create observations from metadata
                    observations = [
                        f"Summary: {metadata['summary']}",
                        f"Topics: {', '.join(metadata['topics'])}",
                        f"Message count: {metadata['message_count']}",
                        f"Last updated: {current_time}",
                    ]

                    # Add entity mentions if any
                    if metadata["entity_mentions"]:
                        observations.append(
                            f"Mentions: {', '.join(metadata['entity_mentions'])}"
                        )

                    # Update entity with new observations
                    try:
                        await self.memory_graph.add_observations(
                            entity_name=entity_name, observations=observations
                        )
                        logger.debug(
                            f"✅ Updated Memory Graph entity for session: {session_id}"
                        )

                    except (ValueError, RuntimeError) as e:
                        # Entity doesn't exist yet - create it
                        # Check if it's an entity-not-found error (can be ValueError or RuntimeError)
                        if "Entity not found" in str(e):
                            logger.debug(
                                f"Entity not found, creating new entity for session: {session_id}"
                            )

                            entity_metadata = {
                                "session_id": session_id,
                                "title": name or session_id,
                                "status": "active",
                                "priority": "medium",
                                "topics": metadata["topics"],
                                "entity_mentions": metadata["entity_mentions"],
                            }

                            # Create entity with observations included (prevents race condition)
                            await self.memory_graph.create_conversation_entity(
                                session_id=session_id,
                                metadata=entity_metadata,
                                observations=observations,
                            )

                            logger.info(
                                f"✅ Created Memory Graph entity for session: {session_id}"
                            )
                        else:
                            # Re-raise if it's a different error
                            raise

                except Exception as mg_error:
                    logger.warning(
                        f"⚠️ Failed to update Memory Graph entity (continuing): {mg_error}"
                    )

            # PERFORMANCE: Periodic cleanup of old session files
            if hasattr(self, "_session_save_counter"):
                self._session_save_counter += 1
            else:
                self._session_save_counter = 1

            if self._session_save_counter % 10 == 0:  # Every 10th save
                self._cleanup_old_session_files()

        except Exception as e:
            logging.error(f"Error saving chat session {session_id}: {str(e)}")

    def delete_session(self, session_id: str) -> bool:
        """
        Deletes a chat session and its companion files.

        Args:
            session_id (str): The identifier for the session to delete.

        Returns:
            bool: True if deletion was successful, False otherwise.
        """
        try:
            chats_directory = self._get_chats_directory()
            deleted = False

            # Delete new format file
            chat_file_new = f"{chats_directory}/{session_id}_chat.json"
            if os.path.exists(chat_file_new):
                os.remove(chat_file_new)
                deleted = True

            # Delete old format file if exists
            chat_file_old = f"{chats_directory}/chat_{session_id}.json"
            if os.path.exists(chat_file_old):
                os.remove(chat_file_old)
                deleted = True

            # Delete companion files (terminal logs, transcripts, etc.)
            terminal_log = f"{chats_directory}/{session_id}_terminal.log"
            if os.path.exists(terminal_log):
                os.remove(terminal_log)
                logger.debug(f"Deleted terminal log for session {session_id}")

            # Delete terminal transcript file
            terminal_transcript = f"{chats_directory}/{session_id}_terminal_transcript.txt"
            if os.path.exists(terminal_transcript):
                os.remove(terminal_transcript)
                logger.debug(f"Deleted terminal transcript for session {session_id}")

            # Clear Redis cache
            if self.redis_client:
                try:
                    cache_key = f"chat:session:{session_id}"
                    self.redis_client.delete(cache_key)
                    self.redis_client.zrem("chat:recent", session_id)
                    logger.debug(f"Cleared Redis cache for session {session_id}")
                except Exception as e:
                    logger.error(f"Failed to clear Redis cache: {e}")

            if not deleted:
                logging.warning(f"Chat session {session_id} not found for deletion")
                return False

            logging.info(f"Chat session '{session_id}' deleted successfully")
            return True

        except Exception as e:
            logging.error(f"Error deleting chat session {session_id}: {str(e)}")
            return False

    async def update_session_name(self, session_id: str, name: str) -> bool:
        """
        Updates the name of a chat session.

        Args:
            session_id (str): The identifier for the session to update.
            name (str): The new name for the session.

        Returns:
            bool: True if update was successful, False otherwise.
        """
        try:
            chats_directory = self._get_chats_directory()

            # Try new format first
            chat_file = f"{chats_directory}/{session_id}_chat.json"
            if not os.path.exists(chat_file):
                # Try old format
                chat_file = f"{chats_directory}/chat_{session_id}.json"
                if not os.path.exists(chat_file):
                    logging.warning(
                        f"Chat session {session_id} not found for name update"
                    )
                    return False

            # Load existing chat data
            async with aiofiles.open(chat_file, "r") as f:
                file_content = await f.read()
            chat_data = json.loads(file_content)

            # Update name and last modified time
            chat_data["name"] = name
            chat_data["last_modified"] = time.strftime("%Y-%m-%d %H:%M:%S")

            # Save updated data (always use new format)
            chat_file_new = f"{chats_directory}/{session_id}_chat.json"
            async with aiofiles.open(chat_file_new, "w") as f:
                await f.write(json.dumps(chat_data, indent=2))

            # Update Redis cache
            if self.redis_client:
                try:
                    cache_key = f"chat:session:{session_id}"
                    await self._async_cache_session(cache_key, chat_data)
                except Exception as e:
                    logger.error(f"Failed to update Redis cache: {e}")

            logging.info(f"Chat session '{session_id}' name updated to '{name}'")
            return True

        except Exception as e:
            logging.error(f"Error updating chat session {session_id} name: {str(e)}")
            return False

    def get_memory_stats(self) -> Dict[str, Any]:
        """PERFORMANCE: Get current memory usage statistics"""
        return {
            "current_messages": len(self.history),
            "max_messages": self.max_messages,
            "cleanup_threshold": self.cleanup_threshold,
            "memory_usage_percent": (len(self.history) / self.max_messages) * 100,
            "memory_check_counter": self.memory_check_counter,
            "memory_check_interval": self.memory_check_interval,
            "needs_cleanup": len(self.history) > self.cleanup_threshold,
        }

    def force_cleanup(self) -> Dict[str, Any]:
        """PERFORMANCE: Force memory cleanup and return statistics"""
        old_count = len(self.history)
        self._cleanup_messages_if_needed()
        collected_objects = gc.collect()

        return {
            "messages_before": old_count,
            "messages_after": len(self.history),
            "messages_removed": old_count - len(self.history),
            "objects_collected": collected_objects,
            "cleanup_performed": old_count > len(self.history),
        }


# Example Usage (for testing)
if __name__ == "__main__":
    # Use a temporary file for testing
    test_file = "data/test_chat_history.json"
    if os.path.exists(test_file):
        os.remove(test_file)

    manager = ChatHistoryManager(test_file)
    print("Initial history:", manager.get_all_messages())
    print("Memory stats:", manager.get_memory_stats())

    import asyncio

    async def test_memory_protection():
        # Add many messages to test memory protection
        for i in range(100):
            await manager.add_message("user", f"Test message {i}")
            await manager.add_message("bot", f"Response {i}")

        print(f"After adding 200 messages: {len(manager.get_all_messages())}")
        print("Memory stats:", manager.get_memory_stats())

        # Test cleanup
        cleanup_stats = manager.force_cleanup()
        print("Cleanup stats:", cleanup_stats)

        # Clear history
        await manager.clear_history()
        print("History after clearing:", len(manager.get_all_messages()))

    asyncio.run(test_memory_protection())

    if os.path.exists(test_file):
        os.remove(test_file)
