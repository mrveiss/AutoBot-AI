#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Core UnifiedConfigManager using composition of specialized modules.

SSOT Migration (Issue #602):
    This manager now integrates with the SSOT config system (ssot_config.py).
    The SSOT config provides infrastructure values (VMs, ports, LLM models),
    while UnifiedConfigManager continues to manage runtime config (config.yaml).

    For infrastructure values, prefer SSOT directly:
        from src.config.ssot_config import config
        redis_host = config.vm.redis
        default_model = config.llm.default_model
"""

import asyncio
import logging
import threading
import time
from datetime import datetime
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
from src.constants.path_constants import PATH

logger = logging.getLogger(__name__)


def _get_ssot_config():
    """Get SSOT config with graceful fallback."""
    try:
        from src.config.ssot_config import get_config

        return get_config()
    except Exception:
        return None


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

    SSOT Migration (Issue #602):
        This class now integrates with SSOT config. Infrastructure values
        (VMs, ports, models) are sourced from SSOT, while runtime config
        (user preferences, feature flags) comes from config.yaml.

    Uses composition pattern with multiple mixins for different functionality areas.
    """

    def __init__(
        self,
        config_dir: str = "config",
        settings: Optional[UnifiedConfigSettings] = None,
    ):
        """Initialize unified config manager with directory paths and settings."""
        # Use centralized PathConstants (Issue #380)
        self.project_root = PATH.PROJECT_ROOT
        self.config_dir = self.project_root / config_dir
        self.base_config_file = self.config_dir / "config.yaml"
        self.settings_file = self.config_dir / "settings.json"

        # SSOT config integration (Issue #602)
        self._ssot = _get_ssot_config()

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

    @property
    def ssot(self):
        """
        Get SSOT config for infrastructure values.

        SSOT Migration (Issue #602):
            Access infrastructure config (VMs, ports, LLM) via this property.
            Example:
                manager.ssot.vm.redis  # Redis VM IP
                manager.ssot.llm.default_model  # Default LLM model
        """
        return self._ssot

    def _reload_config(self) -> None:
        """Reload configuration from files"""
        self._config = load_configuration(
            self.config_dir, self.base_config_file, self.settings_file
        )
        self._sync_cache_timestamp = time.time()

        # Also refresh SSOT reference
        self._ssot = _get_ssot_config()


# Create singleton instance with thread-safe locking (Issue #613)
_unified_config_manager_instance: Optional[UnifiedConfigManager] = None
_unified_config_manager_lock = threading.Lock()


def get_unified_config_manager() -> UnifiedConfigManager:
    """Get or create the singleton UnifiedConfigManager instance (thread-safe).

    Uses double-check locking pattern to ensure thread safety while
    minimizing lock contention after initialization (Issue #613).
    """
    global _unified_config_manager_instance
    if _unified_config_manager_instance is None:
        with _unified_config_manager_lock:
            # Double-check after acquiring lock
            if _unified_config_manager_instance is None:
                _unified_config_manager_instance = UnifiedConfigManager()
    return _unified_config_manager_instance
