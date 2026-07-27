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
from pathlib import Path
from typing import Dict, List, Tuple

from autobot_shared.time_utils import utc_timestamp
from services.deploy_artifacts import ARTIFACT_DIR_SUFFIXES, ARTIFACT_DIRS
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
        # #12450: worker components promoted from read-only visibility to a real
        # per-component resolve path. Each has an explicit post-sync definition in
        # api/code_sync.py (_WORKER_COMPONENTS / _WORKER_COMPONENT_PIP /
        # _COMPONENT_SERVICES) traced to its actual ansible deploy task — notably
        # the restart target is NOT derivable from the component name for two of
        # them (slm-agent -> autobot-agent, browser-worker -> autobot-playwright).
        "autobot-ai-stack",
        "autobot-npu-worker",
        "autobot-browser-worker",
        "autobot-slm-agent",
    }
)

# Deployed components that are visible to the drift walk but still have NO
# resolve wiring — READ-ONLY. Do NOT add an entry here without either giving it
# a post-sync definition (then it belongs in ALLOWED_COMPONENTS instead) or
# recording why it cannot have one. Whitelisting resolve without post-sync would
# rsync files but never restart the right service — half-working and worse than
# the current 400.
#
# #12450 phase 2 promoted ai-stack, npu-worker, browser-worker and slm-agent out
# of this set into ALLOWED_COMPONENTS once each had a verified post-sync
# definition. `plugins` stays here — see below.
#
# Every entry must be verified against its actual ansible deploy task before
# being added here — see _NONSTANDARD_COMPONENT_PATHS below for the ones whose
# layout isn't the standard code_source/<name> -> /opt/autobot/<name> shape.
#
# NOT resolve-capable (confirmed unmappable, see #12450 PR notes):
#   - autobot-tts-worker: deployed via a single Jinja2-templated file
#     (tts-worker.py.j2 -> tts-worker.py), not a 1:1 sync of the repo's
#     autobot-tts-worker/ directory — comparing them would report fake drift.
#   - autobot-celery / celery-beat: no distinct deployed directory — both run
#     FROM the autobot-backend deployed dir (systemd WorkingDirectory), so
#     they are already covered by the existing "autobot-backend" entry.
#   - autobot-plugins (the @autobot/vnc, @autobot/terminal npm workspace
#     packages): synced into TWO deployed locations (autobot-frontend/ and
#     autobot-slm-frontend/), so there is no single canonical deployed target
#     to compare against — needs an owner decision on which (or both) to scan.
EXTRA_VISIBILITY_COMPONENTS = frozenset({"plugins"})

# Union of the resolve-capable allowlist and the read-only extras — used by
# the GET-only drift surfaces (/status stale_components, GET /drift). The
# resolve/resolve-async endpoints must keep checking ALLOWED_COMPONENTS only
# (#12450).
VISIBILITY_COMPONENTS = ALLOWED_COMPONENTS | EXTRA_VISIBILITY_COMPONENTS

# Source/deployed path overrides for components whose layout does not follow
# the code_source/<component> -> <SLM_DEPLOYED_ROOT>/<component> convention
# assumed by get_default_source_dir/get_default_deployed_dir (#12450). Paths
# are relative to DEFAULT_REPO_PATH / SLM_DEPLOYED_ROOT respectively. Verified
# against the live ansible deploy tasks — do not add an entry without tracing
# it to the actual unarchive/copy/synchronize task.
_NONSTANDARD_COMPONENT_PATHS: dict[str, tuple[str, str]] = {
    # ai-stack has no top-level code_source/autobot-ai-stack dir; it lives
    # under autobot-infrastructure/ and deploys with --strip-components=4 so
    # the ai-stack/ subtree contents land directly under the deployed root
    # (ansible/playbooks/update-all-nodes.yml ~135-141, ~1060-1064).
    "autobot-ai-stack": (
        "autobot-infrastructure/shared/docker/ai-stack",
        "autobot-ai-stack",
    ),
    # slm-agent has no top-level code_source/autobot-slm-agent dir either;
    # its source of truth is the individual per-file `copy:` tasks in the
    # slm_agent role, all of which live under files/slm/agent/ and land at
    # <slm_agent_dir>/slm/agent/ (ansible/roles/slm_agent/tasks/main.yml
    # ~132-213). config.yaml/role.json/version.json are Jinja2 templates
    # (not raw source files) and are intentionally excluded from this scan.
    "autobot-slm-agent": (
        "autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent",
        "autobot-slm-agent/slm/agent",
    ),
    # plugins/ ships at the repo root, a SIBLING of autobot-backend/, and is
    # rsynced into the backend's own plugins/ subdirectory rather than its
    # own top-level /opt/autobot/plugins tree (ansible/roles/backend/tasks/
    # main.yml #10294).
    "plugins": (
        "plugins",
        "autobot-backend/plugins",
    ),
}


# Directory names / suffixes to skip entirely during traversal. Sourced from the
# canonical deploy-artifact vocabulary (#11459) so the drift walk and the
# code_sync rsync excludes never disagree about what is an artifact — the
# divergence that let ``*.egg-info`` be drift-skipped (#11440) yet still
# rsync-churned. See services/deploy_artifacts.py for the shared definitions.
_SKIP_DIRS = set(ARTIFACT_DIRS)
_SKIP_DIR_SUFFIXES: tuple[str, ...] = ARTIFACT_DIR_SUFFIXES

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
        # Prune skip dirs in-place so os.walk does not descend into them. Also
        # prune variable-named build-artifact dirs like ``<pkg>.egg-info`` (#11440).
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.endswith(_SKIP_DIR_SUFFIXES)]

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
    drifted, total = compute_drift(source_dir, deployed_dir, component)

    return {
        "source_dir": source_dir,
        "deployed_dir": deployed_dir,
        "drifted_files": drifted,
        "total_compared": total,
        "drift_detected": len(drifted) > 0,
        "checked_at": utc_timestamp(),
    }


def get_default_deployed_dir(component: str = "autobot-slm-backend") -> str:
    """Return the expected deployed path for *component* under /opt/autobot.

    Reads ``SLM_DEPLOYED_ROOT`` from the environment so the path is
    configurable without hardcoding. Components listed in
    ``_NONSTANDARD_COMPONENT_PATHS`` (#12450) use their verified override
    sub-path instead of the standard ``<root>/<component>`` convention.

    Args:
        component: Sub-directory name under the deployed root.

    Returns:
        Absolute path string for the deployed component directory.
    """
    deployed_root = os.environ.get("SLM_DEPLOYED_ROOT", "/opt/autobot")
    override = _NONSTANDARD_COMPONENT_PATHS.get(component)
    rel_path = override[1] if override else component
    return str(Path(deployed_root) / rel_path)


def get_default_source_dir(component: str = "autobot-slm-backend") -> str:
    """Return the code_source sub-directory for *component*.

    Uses ``DEFAULT_REPO_PATH`` from ``services.git_tracker``, which resolves
    ``SLM_REPO_PATH`` with the same fallback, ensuring a single source of truth.
    Components listed in ``_NONSTANDARD_COMPONENT_PATHS`` (#12450) use their
    verified override sub-path instead of the standard
    ``code_source/<component>`` convention (e.g. ai-stack, which lives under
    ``autobot-infrastructure/``).

    Args:
        component: Sub-directory name inside the code_source repository.

    Returns:
        Absolute path string for the source directory to compare against.
    """
    override = _NONSTANDARD_COMPONENT_PATHS.get(component)
    rel_path = override[0] if override else component
    candidate = Path(DEFAULT_REPO_PATH) / rel_path
    if not candidate.is_dir():
        raise ValueError(f"drift_checker: source component directory does not exist: {candidate}")
    return str(candidate)
