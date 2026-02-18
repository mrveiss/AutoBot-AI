# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Manifest Loader Service (Issue #926 Phase 3).

Loads, validates, and caches role manifests from
autobot-infrastructure/autobot-<role>/manifest.yml.
Single source of truth reader for deployment, health, conflict, and
policy decisions.
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from models.manifest import RoleManifest, UpdatePolicy

logger = logging.getLogger(__name__)

# Base dir where autobot-infrastructure/ lives on the SLM server
_AUTOBOT_BASE = Path(os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot"))
_INFRA_BASE = _AUTOBOT_BASE / "autobot-infrastructure"

# Cache TTL in seconds (5 minutes)
_CACHE_TTL = 300


class ManifestLoader:
    """
    Loads and caches role manifests from autobot-infrastructure/.

    Singleton — use get_manifest_loader() rather than instantiating directly.
    """

    def __init__(self, infra_base: Path = _INFRA_BASE) -> None:
        self._infra_base = infra_base
        self._cache: Dict[str, Tuple[RoleManifest, float]] = {}

    def _manifest_path(self, role_name: str) -> Path:
        """Return the expected manifest.yml path for a role."""
        return self._infra_base / role_name / "manifest.yml"

    def _load_from_disk(self, role_name: str) -> Optional[RoleManifest]:
        """Load and parse manifest.yml for role_name."""
        path = self._manifest_path(role_name)
        if not path.exists():
            logger.debug("Manifest not found for role %s at %s", role_name, path)
            return None
        try:
            with path.open(encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
            return RoleManifest.model_validate(raw)
        except Exception as exc:
            logger.warning("Failed to load manifest for %s: %s", role_name, exc)
            return None

    def load(
        self, role_name: str, *, force_reload: bool = False
    ) -> Optional[RoleManifest]:
        """Return the RoleManifest for role_name, using cache if fresh."""
        cached = self._cache.get(role_name)
        if cached and not force_reload:
            manifest, loaded_at = cached
            if time.monotonic() - loaded_at < _CACHE_TTL:
                return manifest

        manifest = self._load_from_disk(role_name)
        if manifest is not None:
            self._cache[role_name] = (manifest, time.monotonic())
        return manifest

    def load_all(self) -> Dict[str, RoleManifest]:
        """Load manifests for all roles found under infra_base."""
        result: Dict[str, RoleManifest] = {}
        if not self._infra_base.exists():
            logger.warning("Infrastructure base dir not found: %s", self._infra_base)
            return result
        for child in sorted(self._infra_base.iterdir()):
            if child.is_dir() and child.name.startswith("autobot-"):
                manifest = self.load(child.name)
                if manifest:
                    result[child.name] = manifest
        return result

    def invalidate(self, role_name: str) -> None:
        """Remove a role from cache (force reload on next access)."""
        self._cache.pop(role_name, None)

    # ------------------------------------------------------------------
    # Convenience accessors (avoid repeated None checks at call sites)
    # ------------------------------------------------------------------

    def get_health_endpoint(self, role_name: str) -> Optional[str]:
        """Return the health.endpoint URL for a role, or None."""
        m = self.load(role_name)
        return m.health.endpoint if m and m.health else None

    def get_port_numbers(self, role_name: str) -> List[int]:
        """Return all port numbers declared by a role."""
        m = self.load(role_name)
        return m.port_numbers() if m else []

    def get_hard_conflicts(self, role_name: str) -> List[str]:
        """Return role names this role hard-conflicts with."""
        m = self.load(role_name)
        return m.hard_conflicts() if m else []

    def get_soft_warnings(self, role_name: str) -> List[str]:
        """Return role names this role warns about."""
        m = self.load(role_name)
        return list(m.coexistence.warns_with) if m else []

    def get_update_policy(self, role_name: str) -> Optional[UpdatePolicy]:
        """Return the system_updates.policy for a role."""
        m = self.load(role_name)
        return m.system_updates.policy if m else None

    def get_service_order(self, role_name: str) -> List[Tuple[str, int]]:
        """Return [(service_name, start_order), ...] sorted by start_order."""
        m = self.load(role_name)
        if not m:
            return []
        return sorted(
            [(svc.name, svc.start_order) for svc in m.services],
            key=lambda x: x[1],
        )

    def get_tls_auto_rotate(self, role_name: str) -> bool:
        """Return True if the role wants TLS auto-rotation."""
        m = self.load(role_name)
        return bool(m and m.tls and m.tls.auto_rotate)

    def get_tls_rotate_days_before(self, role_name: str) -> int:
        """Return how many days before expiry to rotate TLS cert."""
        m = self.load(role_name)
        if m and m.tls and m.tls.rotate_days_before is not None:
            return m.tls.rotate_days_before
        return 14  # sensible default

    def node_update_policy(self, role_names: List[str]) -> UpdatePolicy:
        """
        Return the most restrictive update policy across all roles on a node.

        Priority: manual > security > full
        """
        priority = {
            UpdatePolicy.MANUAL: 0,
            UpdatePolicy.SECURITY: 1,
            UpdatePolicy.FULL: 2,
        }
        most_restrictive = UpdatePolicy.FULL
        for role_name in role_names:
            policy = self.get_update_policy(role_name)
            if policy and priority.get(policy, 99) < priority.get(most_restrictive, 99):
                most_restrictive = policy
        return most_restrictive


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_loader: Optional[ManifestLoader] = None


def get_manifest_loader() -> ManifestLoader:
    """Return the global ManifestLoader singleton."""
    global _loader
    if _loader is None:
        _loader = ManifestLoader()
    return _loader


def init_manifest_loader(infra_base: Optional[Path] = None) -> ManifestLoader:
    """Initialize (or reinitialize) the global ManifestLoader."""
    global _loader
    _loader = ManifestLoader(infra_base=infra_base or _INFRA_BASE)
    logger.info("ManifestLoader initialized (base: %s)", _loader._infra_base)
    return _loader
