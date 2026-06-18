# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Drift Checker Service (Issue #2834).

Compares file checksums between the code_source directory and the deployed
directory to detect files that have been manually patched or missed by Ansible.
"""

import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from services.git_tracker import DEFAULT_REPO_PATH

logger = logging.getLogger(__name__)

# File extensions that are meaningful to compare.
#
# Backend/config extensions (Python services, Ansible, shell scripts):
_BACKEND_EXTENSIONS: frozenset[str] = frozenset({".py", ".cfg", ".ini", ".toml", ".yaml", ".yml", ".sh", ".txt"})
# Frontend source extensions (Vue SFC, TypeScript, styles, HTML, manifests).
# These are source files — node_modules/dist/build are excluded by _SKIP_DIRS
# so compiled output is never compared, only source (Issue #10120).
_FRONTEND_EXTENSIONS: frozenset[str] = frozenset(
    {".vue", ".ts", ".tsx", ".js", ".jsx", ".css", ".scss", ".html", ".json"}
)

# Components whose source is primarily frontend files (Issue #10120).
_FRONTEND_COMPONENTS: frozenset[str] = frozenset({"autobot-frontend", "autobot-slm-frontend"})

# Union set — used as the broadest possible filter and by tests that call
# _collect_checksums without a component (backward-compatible default).
_INCLUDE_EXTENSIONS: frozenset[str] = _BACKEND_EXTENSIONS | _FRONTEND_EXTENSIONS


def comparable_extensions(component: str) -> frozenset[str]:
    """Return the file-extension set appropriate for *component* (Issue #10120).

    Frontend components (``autobot-frontend``, ``autobot-slm-frontend``) use
    the full frontend source set so that .vue/.ts/.css files are included in
    the drift comparison.  All other components (Python backends, Ansible
    playbook repos) use only the backend extension set so that stray .ts/.js
    files inside a backend directory are not accidentally compared.

    Args:
        component: Bare component name, e.g. ``"autobot-frontend"``.

    Returns:
        A frozenset of lower-case file-extension strings (e.g. ``".vue"``).
    """
    if component in _FRONTEND_COMPONENTS:
        return _FRONTEND_EXTENSIONS | _BACKEND_EXTENSIONS
    return _BACKEND_EXTENSIONS


# Permitted component names for the /drift endpoint (Issue #3427).
# Only these sub-directories may be requested to prevent path traversal.
ALLOWED_COMPONENTS = frozenset(
    {
        "autobot-slm-backend",
        "autobot-slm-frontend",
        "autobot-backend",
        "autobot-frontend",
        # #10248: the shared library is its own syncable component. Without this,
        # component code could be advanced past the autobot_shared it imports
        # (e.g. a new symbol) with no way to sync the lib and no drift signal,
        # crash-looping every backend that imports it. Resolving it restarts all
        # dependent services (see _COMPONENT_SERVICES in api/code_sync.py).
        "autobot_shared",
    }
)

# Directory names to skip entirely during traversal.
_SKIP_DIRS = {
    "__pycache__",
    ".git",
    "venv",
    ".venv",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
}

# Paths that are deployment-generated and never present in the git source tree.
# Exact-match paths and prefix patterns are checked against the POSIX relative
# path of each file before it is added to the drift report (Issue #4610).
#
#   ansible/enroll.yml          — written by install.sh during fleet enrollment
#   ansible/inventory/localhost.yml — node-specific IP/hostname; not in git
#   autobot_shared/             — embedded copy rsync'd from a separate source
#                                  dir by Ansible; intentionally absent from
#                                  code_source/<component>/
_EXPECTED_DRIFT_EXACT: frozenset[str] = frozenset(
    {
        "ansible/enroll.yml",
        "ansible/inventory/localhost.yml",
    }
)

_EXPECTED_DRIFT_PREFIXES: tuple[str, ...] = ("autobot_shared/",)


def _is_expected_drift(rel_path: str) -> bool:
    """Return True if *rel_path* is a deployment-generated file to exclude.

    Checks against the exact-match set and prefix list defined in
    ``_EXPECTED_DRIFT_EXACT`` and ``_EXPECTED_DRIFT_PREFIXES`` (Issue #4610).

    Args:
        rel_path: POSIX-style relative path of the file being evaluated.

    Returns:
        True when the path represents expected (non-actionable) drift.
    """
    if rel_path in _EXPECTED_DRIFT_EXACT:
        return True
    return any(rel_path.startswith(prefix) for prefix in _EXPECTED_DRIFT_PREFIXES)


def _file_checksum(path: Path, block_size: int = 65536) -> str:
    """Return the SHA-256 hex digest of a file.

    Reads in blocks to avoid loading large files into memory at once.

    Args:
        path: Absolute path to the file.
        block_size: Read chunk size in bytes.

    Returns:
        Lowercase hex SHA-256 digest string.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(block_size):
            h.update(chunk)
    return h.hexdigest()


def _collect_checksums(
    root: Path,
    extensions: frozenset[str] | None = None,
) -> Dict[str, str]:
    """Walk *root* and return a mapping of relative-path → SHA-256 checksum.

    Only files whose suffix is in *extensions* are included.  When *extensions*
    is ``None`` the full ``_INCLUDE_EXTENSIONS`` union is used (backward-
    compatible default for tests that call this function without a component).
    Directories in ``_SKIP_DIRS`` are pruned from the walk.

    Args:
        root: Directory to scan.
        extensions: Frozenset of lower-case file-extension strings to include.
            Defaults to ``_INCLUDE_EXTENSIONS`` (the backend ∪ frontend set).

    Returns:
        Dict mapping POSIX-style relative path strings to hex digest strings.
    """
    active_extensions = extensions if extensions is not None else _INCLUDE_EXTENSIONS
    checksums: Dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place so os.walk does not descend into them.
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

        for filename in filenames:
            filepath = Path(dirpath) / filename
            if filepath.suffix not in active_extensions:
                continue
            try:
                rel = filepath.relative_to(root).as_posix()
                checksums[rel] = _file_checksum(filepath)
            except (OSError, IOError) as exc:
                logger.warning("drift_checker: cannot read %s: %s", filepath, exc)

    return checksums


def compute_drift(
    source_dir: str,
    deployed_dir: str,
    component: str | None = None,
) -> Tuple[List[dict], int]:
    """Compare file checksums between *source_dir* and *deployed_dir*.

    Returns a tuple of (drifted_file_dicts, total_compared).

    Each drifted file dict has keys:
        path            – POSIX relative path
        source_checksum – SHA-256 of the source file (None if absent)
        deployed_checksum – SHA-256 of the deployed file (None if absent)
        status          – "modified" | "source_only" | "deployed_only"

    Files that exist in both directories with identical checksums are not
    included in the returned list.

    Args:
        source_dir: Absolute path to the authoritative code source directory.
        deployed_dir: Absolute path to the currently deployed directory.
        component: Bare component name used to select the correct extension
            set via ``comparable_extensions()``.  When ``None`` the full
            ``_INCLUDE_EXTENSIONS`` union is used (backward-compatible default).

    Returns:
        Tuple of (list_of_drift_dicts, total_files_compared).
    """
    src_path = Path(source_dir)
    dep_path = Path(deployed_dir)

    if not src_path.is_dir():
        logger.warning("drift_checker: source_dir does not exist: %s", source_dir)
        return [], 0

    if not dep_path.is_dir():
        logger.warning("drift_checker: deployed_dir does not exist: %s", deployed_dir)
        return [], 0

    extensions = comparable_extensions(component) if component is not None else None
    src_checksums = _collect_checksums(src_path, extensions)
    dep_checksums = _collect_checksums(dep_path, extensions)

    all_paths = set(src_checksums) | set(dep_checksums)
    compared = 0
    drifted: List[dict] = []

    for rel_path in sorted(all_paths):
        if _is_expected_drift(rel_path):
            logger.debug("drift_checker: skipping expected-drift path: %s", rel_path)
            continue

        compared += 1
        src_cs = src_checksums.get(rel_path)
        dep_cs = dep_checksums.get(rel_path)

        if src_cs == dep_cs:
            # Both present and identical — no drift.
            continue

        if src_cs is None:
            status = "deployed_only"
        elif dep_cs is None:
            status = "source_only"
        else:
            status = "modified"

        drifted.append(
            {
                "path": rel_path,
                "source_checksum": src_cs,
                "deployed_checksum": dep_cs,
                "status": status,
            }
        )

    return drifted, compared


def build_drift_report(
    source_dir: str,
    deployed_dir: str,
    component: str | None = None,
) -> dict:
    """Build the full drift report dict for the API response (Issue #2834).

    Args:
        source_dir: Path to code_source directory.
        deployed_dir: Path to deployed component directory.
        component: Bare component name forwarded to ``compute_drift`` so that
            the correct per-component extension set is used (Issue #10120).
            When ``None`` the full ``_INCLUDE_EXTENSIONS`` union is used.

    Returns:
        Dict matching the ``FileDriftReport`` schema.
    """
    drifted, total = compute_drift(source_dir, deployed_dir, component)  # codeql[py/path-injection]

    return {
        "source_dir": source_dir,
        "deployed_dir": deployed_dir,
        "drifted_files": drifted,
        "total_compared": total,
        "drift_detected": len(drifted) > 0,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def get_default_deployed_dir(component: str = "autobot-slm-backend") -> str:
    """Return the expected deployed path for *component* under /opt/autobot.

    Reads ``SLM_DEPLOYED_ROOT`` from the environment so the path is
    configurable without hardcoding.

    Args:
        component: Sub-directory name under the deployed root.

    Returns:
        Absolute path string for the deployed component directory.
    """
    deployed_root = os.environ.get("SLM_DEPLOYED_ROOT", "/opt/autobot")
    return str(Path(deployed_root) / component)


def get_default_source_dir(component: str = "autobot-slm-backend") -> str:
    """Return the code_source sub-directory for *component*.

    Uses ``DEFAULT_REPO_PATH`` from ``services.git_tracker``, which resolves
    ``SLM_REPO_PATH`` with the same fallback, ensuring a single source of truth.

    Args:
        component: Sub-directory name inside the code_source repository.

    Returns:
        Absolute path string for the source directory to compare against.
    """
    candidate = Path(DEFAULT_REPO_PATH) / component
    if not candidate.is_dir():
        raise ValueError(f"drift_checker: source component directory does not exist: {candidate}")
    return str(candidate)
