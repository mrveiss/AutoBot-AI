#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Core ConfigManager using composition of specialized modules.

SSOT Migration (Issue #763, #3829):
    Infrastructure values (VMs, ports, LLM models, timeouts) are now the
    canonical responsibility of ``autobot_shared.ssot_config``:

        from autobot_shared.ssot_config import config
        redis_host    = config.vm.redis
        ollama_url    = config.ollama_url
        default_model = config.llm.default_model
        llm_timeout   = config.timeout.llm

    ConfigManager (this class) remains the authority for *runtime* config
    values that users can change via the GUI and that are persisted to
    config.yaml / settings.json:
        - feature flags
        - circuit-breaker thresholds
        - batch sizes
        - agent-specific overrides stored by the UI

    Do NOT add new infrastructure values here; add them to ssot_config instead.
"""

import asyncio
import logging  # stdlib: avoids deadlock — config is on the logging-manager init path (GH#7765 pattern)
import time
from datetime import datetime
from typing import Any, Callable, Dict, List

from autobot_shared.singleton_factory import lazy_singleton
from config.async_ops import AsyncOperationsMixin
from config.file_watcher import FileWatcherMixin
from config.loader import load_configuration
from config.model_config import ModelConfigMixin
from config.service_config import ServiceConfigMixin
from config.settings import ConfigSettings
from config.sync_ops import SyncOperationsMixin
from config.timeout_config import TimeoutConfigMixin
from config.validation import ValidationMixin
from constants.path_constants import PATH

logger = logging.getLogger(__name__)


class ConfigManager(
    SyncOperationsMixin,
    AsyncOperationsMixin,
    ModelConfigMixin,
    ServiceConfigMixin,
    TimeoutConfigMixin,
    FileWatcherMixin,
    ValidationMixin,
):
    """
    Configuration manager combining sync/async operations,
    file management, caching, and model management.

    SSOT Migration (Issue #763):
        Infrastructure values (VMs, ports, models) are now accessed via
        ConfigRegistry. Runtime config (user preferences, feature flags)
        continues to come from config.yaml.

    Uses composition pattern with multiple mixins for different functionality areas.
    """

    def __init__(
        self,
        config_dir: str = "config",
        settings: ConfigSettings | None = None,
    ):
        """Initialize config manager with directory paths and settings."""
        # Use centralized PathConstants (Issue #380)
        self.project_root = PATH.PROJECT_ROOT
        self.config_dir = self.project_root / config_dir
        self.base_config_file = self.config_dir / "config.yaml"
        self.settings_file = self.config_dir / "settings.json"

        # Async settings
        self.settings = settings or ConfigSettings()

        # Configuration cache
        self._config: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._sync_cache_timestamp: float | None = None
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
        """Reload configuration from files."""
        self._config = load_configuration(self.config_dir, self.base_config_file, self.settings_file)
        self._sync_cache_timestamp = time.time()


get_config_manager = lazy_singleton(ConfigManager)


# Deprecated: use ConfigManager and get_config_manager instead
UnifiedConfigManager = ConfigManager
get_unified_config_manager = get_config_manager
