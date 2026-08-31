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


# ---------------------------------------------------------------------------
# Host-generated state (#14231)
# ---------------------------------------------------------------------------
# Artifacts above are *generated from the source tree*. These are different:
# they exist only in the deployment, are never tracked in git, and a
# delete-style sync removes them because the source has nothing to match.
#
# The list grew one incident at a time -- `.env`/`data` (#9970), `logs`
# (#13851), and then four more (#14231) surfaced by a refused resync on a live
# node. Each fix protected the single path that had just been reported. The
# rule they were all instances of: **a path that exists only on the host and
# holds state the node cannot regenerate must survive every sync.**
#
# Anchored (`/`-prefixed) entries match at the transfer root only. This matters:
# a bare `config` would also exclude `autobot-slm-frontend/src/config/`, which
# is tracked source, and suppressing it would read as permanent drift -- the
# #11440 failure mode, arriving from the opposite direction.
HOST_STATE_EXCLUDES: tuple[str, ...] = (
    ".env",  # systemd EnvironmentFile (#2824, #9970) -- service will not start without it
    ".env.*",  # .env.production and siblings; the exact `.env` pattern never matched them
    "data",  # per-service runtime state (#9970)
    "logs",  # audit trail; a dry run once listed logs/audit/*.jsonl among 55 deletions (#13851)
    "/config/",  # host-rendered service config
    "/.deployed_commit",  # what the self-update skip-check reads (#12202)
    "/ansible/enroll.yml",  # the node's rendered enrolment play
)

# Tracked source files that a HOST_STATE_EXCLUDES pattern would otherwise catch.
# rsync applies the FIRST matching rule, so these must be emitted as `--include`
# ahead of the excludes. Deriving the exclude family from a glob is what makes
# this necessary -- `.env.*` is right for host state and wrong for the one
# `.env.example` the backend tracks. A guard test asserts this list covers every
# such file, so adding `.env.template` tomorrow fails loudly instead of silently
# going undeployed.
HOST_STATE_REINCLUDES: tuple[str, ...] = ("/.env.example",)


def rsync_host_state_args() -> list[str]:
    """rsync args protecting host-generated state, re-includes first.

    Returns `--include` args ahead of `--exclude` args because rsync stops at
    the first matching rule; the order is the mechanism, not a preference.
    """
    return [
        *(f"--include={pattern}" for pattern in HOST_STATE_REINCLUDES),
        *(f"--exclude={pattern}" for pattern in HOST_STATE_EXCLUDES),
    ]


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
