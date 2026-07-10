# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical build/deploy-artifact vocabulary (single source of truth).

The set of "generated artifacts that are never part of the git source tree"
was previously hard-coded in several places that drifted apart: the rsync
`--exclude` lists in ``api/code_sync.py`` (4× inline) and the walk-prune sets in
``services/drift_checker.py``. They disagreed — e.g. ``*.egg-info`` was skipped
by the drift report (#11440) but still deleted-and-resynced by rsync — which is
exactly the class of bug #11440 fixed for one path only.

Both consumers now derive from this module so they stay in lockstep (#11459):

* ``drift_checker`` prunes ``ARTIFACT_DIRS`` (exact dir names) and
  ``ARTIFACT_DIR_SUFFIXES`` (variable-prefixed dirs like ``<pkg>.egg-info``)
  from its file-tree walk.
* ``code_sync`` feeds :func:`rsync_artifact_excludes` into the rsync
  ``--exclude`` chokepoint so every deploy sync ignores the same artifacts.
"""

from __future__ import annotations

# Exact directory names that are always build/deploy artifacts — never synced,
# never drift-reported. VCS, Python/JS build caches, virtualenvs, bundler output.
ARTIFACT_DIRS: frozenset[str] = frozenset(
    {
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
)

# Directory-name SUFFIXES — variable-prefixed artifact dirs that an exact-name
# match can't catch. ``<pkg>.egg-info`` is created by ``pip install`` in the
# deployed dir; its contents (SOURCES.txt, requires.txt, top_level.txt,
# dependency_links.txt) are deployment-generated and absent from the git source,
# so they read as permanent false drift when not skipped (#11440).
ARTIFACT_DIR_SUFFIXES: tuple[str, ...] = (".egg-info",)

# File glob patterns that are always artifacts (compiled bytecode, logs).
ARTIFACT_FILE_GLOBS: tuple[str, ...] = ("*.pyc", "*.log")


def rsync_artifact_excludes() -> list[str]:
    """rsync ``--exclude`` patterns covering every build/deploy artifact.

    Directories by name, variable-prefixed dirs by ``*<suffix>`` glob, and file
    globs — the full artifact vocabulary as rsync patterns. Sorted for stable,
    reviewable ``--exclude`` ordering.
    """
    return [
        *sorted(ARTIFACT_DIRS),
        *(f"*{suffix}" for suffix in ARTIFACT_DIR_SUFFIXES),
        *ARTIFACT_FILE_GLOBS,
    ]
