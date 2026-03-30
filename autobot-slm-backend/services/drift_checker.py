# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

logger = logging.getLogger(__name__)

# File extensions that are meaningful to compare.
_INCLUDE_EXTENSIONS = {".py", ".cfg", ".ini", ".toml", ".yaml", ".yml", ".sh", ".txt"}

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


def _collect_checksums(root: Path) -> Dict[str, str]:
    """Walk *root* and return a mapping of relative-path → SHA-256 checksum.

    Only files with extensions in ``_INCLUDE_EXTENSIONS`` are included.
    Directories in ``_SKIP_DIRS`` are pruned from the walk.

    Args:
        root: Directory to scan.

    Returns:
        Dict mapping POSIX-style relative path strings to hex digest strings.
    """
    checksums: Dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place so os.walk does not descend into them.
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

        for filename in filenames:
            filepath = Path(dirpath) / filename
            if filepath.suffix not in _INCLUDE_EXTENSIONS:
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
) -> Tuple[List[dict], int]:
    """Compare file checksums between *source_dir* and *deployed_dir*.

    Returns a tuple of (drifted_file_dicts, total_compared_count).

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

    src_checksums = _collect_checksums(src_path)
    dep_checksums = _collect_checksums(dep_path)

    all_paths = set(src_checksums) | set(dep_checksums)
    total_compared = len(all_paths)
    drifted: List[dict] = []

    for rel_path in sorted(all_paths):
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

    return drifted, total_compared


def build_drift_report(
    source_dir: str,
    deployed_dir: str,
) -> dict:
    """Build the full drift report dict for the API response (Issue #2834).

    Args:
        source_dir: Path to code_source directory.
        deployed_dir: Path to deployed component directory.

    Returns:
        Dict matching the ``FileDriftReport`` schema.
    """
    drifted, total = compute_drift(source_dir, deployed_dir)

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

    Reads ``SLM_REPO_PATH`` from the environment (same var used by git_tracker).
    Falls back to the repository root when the component sub-directory does not
    exist yet (e.g. monorepo roots that serve as the authoritative source).

    Args:
        component: Sub-directory name inside the code_source repository.

    Returns:
        Absolute path string for the source directory to compare against.
    """
    source_root = os.environ.get("SLM_REPO_PATH", "/opt/autobot/code_source")
    candidate = Path(source_root) / component
    return str(candidate) if candidate.is_dir() else source_root
