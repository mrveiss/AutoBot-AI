# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
UnifiedRegistry (GH#7369)

Single registry for all manifest types: plugins, skills, and extensions.
"""

import logging
import threading
from typing import Callable, Optional

from plugin_sdk.manifest_contract import ManifestContract

logger = logging.getLogger(__name__)


class UnifiedRegistry:
    """Singleton registry that accepts any ManifestContract-conforming manifest."""

    _instance: Optional["UnifiedRegistry"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "UnifiedRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._manifests: dict[str, ManifestContract] = {}
                    instance._loaders: dict[str, Optional[Callable]] = {}
                    cls._instance = instance
        return cls._instance

    def register(self, manifest: ManifestContract, loader_fn: Optional[Callable] = None) -> None:
        """Register a manifest by name, optionally with a loader callable."""
        if not isinstance(manifest, ManifestContract):
            raise TypeError(f"Object does not satisfy ManifestContract: {type(manifest)}")
        self._manifests[manifest.name] = manifest
        self._loaders[manifest.name] = loader_fn
        logger.debug("UnifiedRegistry: registered %s (%s)", manifest.name, manifest.kind)

    def get(self, name: str) -> Optional[ManifestContract]:
        """Return manifest by name, or None if not registered."""
        return self._manifests.get(name)

    def list_all(self) -> list[ManifestContract]:
        """Return all registered manifests sorted by name."""
        return sorted(self._manifests.values(), key=lambda m: m.name)

    def clear(self) -> None:
        """Clear registry (primarily for test isolation)."""
        self._manifests.clear()
        self._loaders.clear()


def get_unified_registry() -> UnifiedRegistry:
    """Return the process-level UnifiedRegistry singleton."""
    return UnifiedRegistry()
