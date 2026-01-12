# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat History Base - Core initialization and configuration.

Provides the foundation for the ChatHistoryManager composed class with:
- Configuration loading from unified config manager
- Redis client initialization
- Memory Graph integration
- Context window management
"""

import logging
import os
import threading
from typing import Optional

from src.autobot_memory_graph import AutoBotMemoryGraph
from src.constants.network_constants import NetworkConstants
from src.context_window_manager import ContextWindowManager
from src.encryption_service import get_encryption_service, is_encryption_enabled
from src.config import config as global_config_manager
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class ChatHistoryBase:
    """
    Base class for ChatHistoryManager providing core initialization.

    Handles:
    - Configuration loading from unified config manager
    - Redis client setup
    - Encryption service initialization
    - Memory Graph integration
    - Context window management
    - Performance optimization settings
    """

    def _load_config_values(
        self,
        history_file: Optional[str],
        use_redis: Optional[bool],
        redis_host: Optional[str],
        redis_port: Optional[int],
    ) -> None:
        """
        Load configuration values from config manager with overrides.

        Issue #665: Extracted from __init__ to reduce function length.

        Args:
            history_file: Optional override for history file path
            use_redis: Optional override for Redis usage flag
            redis_host: Optional override for Redis host
            redis_port: Optional override for Redis port
        """
        from src.config import UnifiedConfigManager

        data_config = global_config_manager.get("data", {})
        redis_config = global_config_manager.get_redis_config()
        unified_config = UnifiedConfigManager()

        self.history_file = history_file or data_config.get(
            "chat_history_file",
            os.getenv("AUTOBOT_CHAT_HISTORY_FILE", "data/chat_history.json"),
        )
        self.use_redis = (
            use_redis if use_redis is not None else redis_config.get("enabled", False)
        )
        self.redis_host = redis_host or redis_config.get(
            "host", os.getenv("REDIS_HOST", unified_config.get_host("redis"))
        )
        self.redis_port = redis_port or redis_config.get(
            "port",
            int(os.getenv("AUTOBOT_REDIS_PORT", str(NetworkConstants.REDIS_PORT))),
        )

    def _init_state_and_settings(self) -> None:
        """
        Initialize instance state and performance settings.

        Issue #665: Extracted from __init__ to reduce function length.
        """
        # Message history storage
        self.history: list = []
        self.redis_client = None
        self.encryption_enabled = is_encryption_enabled()

        # Performance optimization settings
        self.max_messages = 10000
        self.cleanup_threshold = 12000
        self.max_session_files = 1000
        self.memory_check_counter = 0
        self.memory_check_interval = 50
        self._counter_lock = threading.Lock()
        self._session_save_counter = 0

        # Memory Graph integration
        self.memory_graph: Optional[AutoBotMemoryGraph] = None
        self.memory_graph_enabled = False

        # Context window management
        self.context_manager = ContextWindowManager()

    def __init__(
        self,
        history_file: Optional[str] = None,
        use_redis: Optional[bool] = None,
        redis_host: Optional[str] = None,
        redis_port: Optional[int] = None,
    ):
        """
        Initialize the ChatHistoryManager base with performance optimizations.

        Issue #665: Refactored to use extracted helper methods.

        Args:
            history_file: Path to the JSON file for persistent storage.
            use_redis: If True, attempts to use Redis for active memory storage.
            redis_host: Hostname for Redis server.
            redis_port: Port for Redis server.
        """
        # Issue #665: Use helpers for configuration and state setup
        self._load_config_values(history_file, use_redis, redis_host, redis_port)
        self._init_state_and_settings()

        logger.info(
            "PERFORMANCE: ChatHistoryManager initialized with memory protection - "
            "max_messages: %d, cleanup_threshold: %d",
            self.max_messages,
            self.cleanup_threshold,
        )
        logger.info("✅ Context window manager initialized with model-aware limits")

        # Initialize subsystems
        self._init_encryption()
        self._init_redis()
        self._ensure_data_directory_exists()
        self._load_history()

        logger.info(
            "ChatHistoryManager ready (Memory Graph will initialize on first async operation)"
        )

    def _init_encryption(self):
        """Initialize encryption service if enabled."""
        if self.encryption_enabled:
            logger.info("Chat history encryption is ENABLED")
            try:
                encryption_service = get_encryption_service()
                key_info = encryption_service.get_key_info()
                logger.info("Encryption service initialized: %s", key_info['algorithm'])
            except Exception as e:
                logger.error("Failed to initialize encryption service: %s", e)
                self.encryption_enabled = False
        else:
            logger.info("Chat history encryption is DISABLED")

    def _init_redis(self):
        """Initialize Redis client for caching."""
        if self.use_redis:
            self.redis_client = get_redis_client(async_client=False)
            if self.redis_client:
                logger.info(
                    "Redis connection established via centralized utility "
                    "for active memory storage."
                )
            else:
                logger.error(
                    "Failed to get Redis client from centralized utility. "
                    "Falling back to file storage."
                )
                self.use_redis = False

    def _ensure_data_directory_exists(self):
        """Ensure the directory for the history file exists."""
        data_dir = os.path.dirname(self.history_file)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)

    def _get_chats_directory(self) -> str:
        """Get the chats directory path from configuration."""
        data_config = global_config_manager.get("data", {})
        return data_config.get(
            "chats_directory",
            os.getenv("AUTOBOT_CHATS_DIRECTORY", "data/chats"),
        )

    def _load_history(self):
        """
        Initialize with empty history.

        Modern architecture uses per-session files in data/chats/ directory.
        self.history remains EMPTY to prevent data pollution.
        """
        self.history = []

        logger.info(
            "ChatHistoryManager initialized with EMPTY default history. "
            "All sessions are managed independently in data/chats/ directory."
        )

        # Warn about obsolete legacy file
        if os.path.exists(self.history_file):
            logger.warning(
                f"⚠️ Legacy chat_history.json file exists at {self.history_file}. "
                "This file is NO LONGER USED. Sessions are stored in data/chats/ directory. "
                "Consider archiving this file to prevent confusion."
            )

    async def _init_memory_graph(self):
        """
        Initialize Memory Graph for conversation entity tracking.

        Called asynchronously during first session operation.
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
                    "⚠️ Memory Graph initialization returned False - "
                    "conversation entity tracking disabled"
                )
                self.memory_graph = None

        except Exception as e:
            logger.warning(
                "⚠️ Failed to initialize Memory Graph (continuing without entity tracking): %s",
                e,
            )
            self.memory_graph = None
            self.memory_graph_enabled = False

    def get_all_messages(self) -> list:
        """Return the entire chat history (legacy method)."""
        return self.history
