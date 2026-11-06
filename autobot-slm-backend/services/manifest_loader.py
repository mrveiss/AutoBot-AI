# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Manifest Loader Service (Issue #926 Phase 3).

Loads, validates, and caches role manifests from
autobot-infrastructure/autobot-<role>/manifest.yml.
Single source of truth reader for deployment, health, conflict, and
policy decisions.

Environment:
    ``SLM_MANIFEST_CACHE_TTL`` -- seconds a parsed manifest is served from
    cache, default 300. ``0`` or negative disables caching, which is the
    dev-mode bypass for editing a manifest on the SLM host (#16026).
    Read through ``autobot_shared.env_utils.env_int``, as the other SLM knobs
    are. Documented here rather than in ``autobot_shared/env_registry.py``:
    that registry holds ``AUTOBOT_*`` names and carries no ``SLM_*`` entry.

    ``SLM_INFRA_BASE_DIR`` -- overrides where ``autobot-infrastructure/`` is
    read from. Without it the first that exists wins (#20567): ``<code_source>/autobot-infrastructure``
    (the copy the SLM updates; the one beside the install was never updated), then
    ``<base_dir>/autobot-infrastructure`` (a checkout, or a node with no code_source). With none
    present manifests are unavailable and a warning says so. Kept
    separate from ``AUTOBOT_BASE_DIR`` (#16025) because ``role_registry.py``
    reads that same variable for the unrelated deploy *target* directory
    (``/opt/autobot`` in production); a test or dev host pointing manifests at
    the repo's own ``autobot-infrastructure/`` must not also redirect every
    role's deploy target.
"""

import logging
import os
import re
import time
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import yaml

from autobot_shared.env_utils import env_int
from autobot_shared.ssot_config import config as ssot_config
from models.manifest import RoleManifest, UpdatePolicy

logger = logging.getLogger(__name__)

INFRA_DIR_NAME = "autobot-infrastructure"


def resolve_infra_base(
    override: str | None = None, code_source: Path | None = None, base_dir: Path | None = None
) -> Path:
    """Where role manifests are read from: override, else code_source's copy, else the install's.

    Arguments default to ``SLM_INFRA_BASE_DIR`` and the SSOT paths; they exist so the order can be
    exercised on real directories. #16025: the override is independent of ``AUTOBOT_BASE_DIR`` -- see
    the module docstring.
    """
    override = override if override is not None else os.environ.get("SLM_INFRA_BASE_DIR")
    if override:
        return Path(override)
    code_source = code_source if code_source is not None else ssot_config.path.code_source_path
    base_dir = base_dir if base_dir is not None else Path(ssot_config.path.base_dir)
    candidates = (code_source / INFRA_DIR_NAME, base_dir / INFRA_DIR_NAME)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    logger.warning(
        "Role manifests are unavailable: no %s found in %s or %s, so pre-flight checks that read them are skipped",
        INFRA_DIR_NAME,
        code_source,
        base_dir,
    )
    return candidates[0]


def candidate_infra_roots(
    override: str | None = None, code_source: Path | None = None, base_dir: Path | None = None
) -> list[Path]:
    """Every directory a role manifest may be read from, best first, re-read from disk on each call.

    The override alone when set; else each existing ``autobot-infrastructure`` of code_source then the install.
    A role missing from the first is looked up in the next (an incomplete tree must not hide the install's
    copy and silently skip a role's conflict checks), and a code_source populated after start is seen at once.
    """
    override = override if override is not None else os.environ.get("SLM_INFRA_BASE_DIR")
    if override:
        return [Path(override)]
    code_source = code_source if code_source is not None else ssot_config.path.code_source_path
    base_dir = base_dir if base_dir is not None else Path(ssot_config.path.base_dir)
    existing = [c for c in (code_source / INFRA_DIR_NAME, base_dir / INFRA_DIR_NAME) if c.is_dir()]
    return existing or [code_source / INFRA_DIR_NAME]


_INFRA_BASE = resolve_infra_base()

# Cache TTL in seconds, env-backed rather than a bare literal (#16026): a
# manifest is an operator-edited file, so the staleness window has to be tunable
# on the host that edits it. `<= 0` disables caching, which is the dev-mode
# bypass.
#
# `env_int` rather than a local reader: it already treats a blank value as
# absent (#12782 -- a template rendering an undefined var exports `NAME=`, which
# defeats every `os.environ.get(name, default)` fallback) and already warns and
# falls back on a non-integer instead of raising at import. services/reconciler.py
# and api/code_sync.py in this same service already read their knobs this way.
_CACHE_TTL = env_int("SLM_MANIFEST_CACHE_TTL", 300)


class ManifestLoader:
    """
    Loads and caches role manifests from autobot-infrastructure/.

    Singleton — use get_manifest_loader() rather than instantiating directly.
    """

    def __init__(self, infra_base: Path | None = None, roots: Callable[[], List[Path]] | None = None) -> None:
        """*infra_base* pins one directory; *roots* supplies the candidates; neither reads them live from disk."""
        self._roots_source: Callable[[], List[Path]] = (
            (lambda: [infra_base]) if infra_base is not None else (roots or candidate_infra_roots)
        )
        self._roots_seen: Tuple[Path, ...] = ()
        self._cache: Dict[str, Tuple[RoleManifest, float]] = {}

    @property
    def _infra_base(self) -> Path:
        """The first (preferred) root."""
        return self._roots_source()[0]

    def _current_roots(self) -> List[Path]:
        """The roots now; when they differ from last time the cached manifests came from elsewhere, so drop them."""
        roots = self._roots_source()
        if tuple(roots) != self._roots_seen:
            self._cache.clear()
            self._roots_seen = tuple(roots)
        return roots

    #: A role directory name. Ansible role names are lowercase with underscores
    #: or hyphens; nothing legitimate contains a separator, a dot or whitespace.
    #: `fullmatch`, not `match`: with `match` the trailing `$` also matches
    #: before a final newline, so "backend\n" was accepted (#17300 review).
    _ROLE_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")

    def _manifest_path(self, role_name: str) -> Path | None:
        """The manifest.yml path for *role_name*, or None if it is not a real role.

        #17300: `role_name` arrives from a `role` query parameter and a
        `role_name` POST body field, and was joined as its own path segment with
        no validation -- `role_name="../../../../etc"` walked out of the infra
        base before `path.exists()` and `path.open()`.

        The path is built from a DIRECTORY LISTING, not from the argument: the
        argument only ever selects an entry that already exists under the infra
        base. That is what makes traversal impossible rather than merely
        difficult -- there is no string concatenation for an attacker to steer,
        so the property holds without anyone having to reason about what the
        allowlist excludes. The allowlist and the containment check remain as
        two cheaper filters in front of it.

        Returns None rather than raising, which is the caller's existing
        "no manifest for this role" path and the honest answer for a name that
        cannot be a role.
        """
        if not self._ROLE_NAME_RE.fullmatch(role_name or ""):
            logger.warning("Rejected manifest lookup for a non-role name: %r (#17300)", role_name)
            return None

        base, entry = self._find_role_dir(role_name)
        if entry is None:
            return None

        candidate = (entry / "manifest.yml").resolve()
        # A role directory that is a symlink out of the base resolves outside it;
        # the listing alone would not catch that.
        if not candidate.is_relative_to(base):
            logger.warning("Rejected manifest path outside the infra base: %r (#17300)", role_name)
            return None
        return candidate

    def _find_role_dir(self, role_name: str) -> Tuple[Path, Path | None]:
        """(root, role directory) from the first root that holds *role_name*; (first root, None) when none does."""
        roots = [root.resolve() for root in self._current_roots()]
        for base in roots:
            try:
                entries = {entry.name: entry for entry in base.iterdir() if entry.is_dir()}
            except OSError as exc:
                logger.warning("Cannot list the infra base %s: %s", base, exc)
                continue
            if role_name in entries:
                return base, entries[role_name]
        return roots[0], None

    def _load_from_disk(self, role_name: str) -> RoleManifest | None:
        """Load and parse manifest.yml for role_name."""
        path = self._manifest_path(role_name)
        if path is None or not path.exists():
            logger.debug("Manifest not found for role %s at %s", role_name, path)
            return None
        try:
            with path.open(encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
            return RoleManifest.model_validate(raw)
        except Exception as exc:
            logger.warning("Failed to load manifest for %s: %s", role_name, exc)
            return None

    def load(self, role_name: str, *, force_reload: bool = False) -> RoleManifest | None:
        """Return the RoleManifest for role_name, using cache if fresh."""
        self._current_roots()
        cached = self._cache.get(role_name)
        if cached and not force_reload and _CACHE_TTL > 0:
            manifest, loaded_at = cached
            if time.monotonic() - loaded_at < _CACHE_TTL:
                return manifest

        manifest = self._load_from_disk(role_name)
        if manifest is None:
            # A failed read must not leave the previous entry behind (#16204). A
            # forced reload that fails returns None to its caller; if the old entry
            # survived, every later plain load() inside the TTL would serve the
            # pre-reload manifest -- the one caller that asked for fresh data told
            # the truth, every later caller told the old answer. An expired entry
            # whose reload fails is dropped for the same reason: it is never served,
            # so keeping it only leaves the cache asserting what the disk no longer says.
            self._cache.pop(role_name, None)
        else:
            self._cache[role_name] = (manifest, time.monotonic())
        return manifest

    def load_all(self, *, force_reload: bool = False) -> Dict[str, RoleManifest]:
        """Load manifests for all roles found under infra_base.

        ``force_reload`` is threaded through to :meth:`load` because
        ``services/reconciler.py`` reads the whole set through this method and
        had no way to reach the per-role bypass (#16026) -- an override that a
        caller cannot get at is not an override.
        """
        result: Dict[str, RoleManifest] = {}
        roots = [root for root in self._current_roots() if root.exists()]
        if not roots:
            logger.warning("Infrastructure base dir not found: %s", self._infra_base)
            return result
        names = sorted(
            {c.name for root in roots for c in root.iterdir() if c.is_dir() and c.name.startswith("autobot-")}
        )
        for name in names:
            manifest = self.load(name, force_reload=force_reload)
            if manifest:
                result[name] = manifest
        return result

    def invalidate(self, role_name: str) -> None:
        """Remove a role from cache (force reload on next access)."""
        self._cache.pop(role_name, None)

    # ------------------------------------------------------------------
    # Convenience accessors (avoid repeated None checks at call sites)
    # ------------------------------------------------------------------

    def get_health_endpoint(self, role_name: str) -> str | None:
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

    def get_update_policy(self, role_name: str) -> UpdatePolicy | None:
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

_loader: ManifestLoader | None = None


def get_manifest_loader() -> ManifestLoader:
    """Return the global ManifestLoader singleton."""
    global _loader
    if _loader is None:
        _loader = ManifestLoader()
    return _loader


def init_manifest_loader(infra_base: Path | None = None) -> ManifestLoader:
    """Initialize (or reinitialize) the global ManifestLoader."""
    global _loader
    _loader = ManifestLoader(infra_base=infra_base)
    logger.info("ManifestLoader initialized (base: %s)", _loader._infra_base)
    return _loader
