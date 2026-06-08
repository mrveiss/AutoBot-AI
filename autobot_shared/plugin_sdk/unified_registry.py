# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
UnifiedRegistry (GH#7369)

Single registry for all manifest types: plugins, skills, and extensions.
"""

from __future__ import annotations

import logging
import threading

from .manifest_contract import ManifestContract

logger = logging.getLogger(__name__)


class UnifiedRegistry:
    """Singleton registry that accepts any ManifestContract-conforming manifest."""

    _instance: "UnifiedRegistry" | None = None
    _lock: threading.Lock = threading.Lock()
    _manifests: dict[str, ManifestContract]

    def __new__(cls) -> "UnifiedRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._manifests = {}
                    cls._instance = instance
        return cls._instance

    def register(self, manifest: ManifestContract) -> None:
        """Register a manifest by name."""
        if not isinstance(manifest, ManifestContract):
            raise TypeError(f"Object does not satisfy ManifestContract: {type(manifest)}")
        self._manifests[manifest.name] = manifest
        logger.debug("UnifiedRegistry: registered %s (%s)", manifest.name, manifest.kind)

    def unregister(self, name: str) -> bool:
        """Remove a manifest by name. Returns True if it was present."""
        if name in self._manifests:
            del self._manifests[name]
            logger.debug("UnifiedRegistry: unregistered %s", name)
            return True
        return False

    def get(self, name: str) -> ManifestContract | None:
        """Return manifest by name, or None if not registered."""
        return self._manifests.get(name)

    def list_all(self) -> list[ManifestContract]:
        """Return all registered manifests sorted by name."""
        return sorted(self._manifests.values(), key=lambda m: m.name)

    def clear(self) -> None:
        """Clear registry (primarily for test isolation)."""
        self._manifests.clear()


def get_unified_registry() -> UnifiedRegistry:
    """Return the process-level UnifiedRegistry singleton."""
    return UnifiedRegistry()
