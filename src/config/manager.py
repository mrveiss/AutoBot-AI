#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Core UnifiedConfigManager using composition of specialized modules.
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.config.async_ops import AsyncOperationsMixin
from src.config.file_watcher import FileWatcherMixin
from src.config.loader import load_configuration
from src.config.model_config import ModelConfigMixin
from src.config.service_config import ServiceConfigMixin
from src.config.settings import UnifiedConfigSettings
from src.config.sync_ops import SyncOperationsMixin
from src.config.timeout_config import TimeoutConfigMixin
from src.config.validation import ValidationMixin

logger = logging.getLogger(__name__)


class UnifiedConfigManager(
    SyncOperationsMixin,
    AsyncOperationsMixin,
    ModelConfigMixin,
    ServiceConfigMixin,
    TimeoutConfigMixin,
    FileWatcherMixin,
    ValidationMixin,
):
    """
    Unified configuration manager combining sync/async operations,
    file management, caching, and model management.

    Uses composition pattern with multiple mixins for different functionality areas.
    """

    def __init__(
        self,
        config_dir: str = "config",
        settings: Optional[UnifiedConfigSettings] = None,
    ):
        """Initialize unified config manager with directory paths and settings."""
        # Find project root dynamically
        self.project_root = Path(__file__).parent.parent.parent
        self.config_dir = self.project_root / config_dir
        self.base_config_file = self.config_dir / "config.yaml"
        self.settings_file = self.config_dir / "settings.json"

        # Async settings
        self.settings = settings or UnifiedConfigSettings()

        # Configuration cache
        self._config: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._sync_cache_timestamp: Optional[float] = None
        self.CACHE_DURATION = 30  # 30 seconds for sync cache

        # Async support
        self._async_lock = asyncio.Lock() if hasattr(asyncio, "current_task") else None
        self._sync_lock = None  # Will be created when needed
        self._file_watchers: Dict[str, asyncio.Task] = {}
        self._callbacks: Dict[str, List[Callable]] = {}

        # Initialize
        self._reload_config()

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _reload_config(self) -> None:
        """Reload configuration from files"""
        self._config = load_configuration(
            self.config_dir, self.base_config_file, self.settings_file
        )
        self._sync_cache_timestamp = time.time()


# Create singleton instance
_unified_config_manager_instance: Optional[UnifiedConfigManager] = None


def get_unified_config_manager() -> UnifiedConfigManager:
    """Get or create the singleton UnifiedConfigManager instance"""
    global _unified_config_manager_instance
    if _unified_config_manager_instance is None:
        _unified_config_manager_instance = UnifiedConfigManager()
    return _unified_config_manager_instance
