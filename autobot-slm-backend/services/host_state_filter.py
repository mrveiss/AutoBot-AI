# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Kept-on-disk host state a git-proven deletion must never remove (#16310).

``git diff --diff-filter=D`` also reports a file that was ``git rm --cached``
then added to ``.gitignore`` -- tracked once, deliberately kept on disk now,
exactly #16300's pattern. Deleting it because git shows a "D" would silently
remove live state a human chose to keep. Two independent signals, either one
is enough to keep a path:

* it matches ``deploy_artifacts.HOST_STATE_EXCLUDES`` (minus
  ``HOST_STATE_REINCLUDES``) -- the same rules the rsync chokepoint already
  protects from a delete-style sync.
* ``git check-ignore`` reports it ignored at the commit currently checked
  out in the source repo -- the #16300 shape itself.

Shared by ``services/sync_deletions.py`` (skip before unlinking) and
``services/full_tree_drift.py`` (classify as ``host_state``, not
``removed_from_source``, so an operator is never steered into deleting it
by hand).
"""

from __future__ import annotations

from fnmatch import fnmatch

from services.deploy_artifacts import HOST_STATE_EXCLUDES, HOST_STATE_REINCLUDES
from services.git_subprocess import run_git


def _pattern_matches(rel_path: str, pattern: str) -> bool:
    """One ``HOST_STATE_EXCLUDES`` entry against *rel_path* (rsync-exclude shape).

    A leading ``/`` anchors at the transfer root (component-relative); a bare
    pattern matches any path SEGMENT, mirroring how rsync itself applies
    these same strings at the sync chokepoint (``_rsync_exclude_args``).
    """
    if pattern.startswith("/"):
        core = pattern.strip("/")
        return rel_path == core or rel_path.startswith(f"{core}/")
    return any(fnmatch(segment, pattern) for segment in rel_path.split("/"))


def host_state_pattern(rel_path: str) -> str | None:
    """The ``HOST_STATE_EXCLUDES`` pattern *rel_path* matches, or ``None``.

    A ``HOST_STATE_REINCLUDES`` match wins over any exclude -- the same
    precedence ``rsync_host_state_args`` gives the re-includes by emitting
    them first (rsync applies the FIRST matching rule).
    """
    if any(_pattern_matches(rel_path, pattern) for pattern in HOST_STATE_REINCLUDES):
        return None
    return next((p for p in HOST_STATE_EXCLUDES if _pattern_matches(rel_path, p)), None)


async def is_git_ignored(repo_root: str, pathspec: str) -> bool:
    """True when *pathspec* is ignored by the ``.gitignore`` rules checked
    out in *repo_root* right now -- the commit the deletion diff runs against."""
    _, rc = await run_git(repo_root, "check-ignore", "-q", "--", pathspec)
    return rc == 0


async def kept_reason(rel_path: str, repo_root: str, pathspec: str) -> str | None:
    """Named reason *rel_path* must survive deletion, or ``None`` to proceed.

    Checks the cheap, local pattern match before the git subprocess -- no
    reason to shell out for a path ``HOST_STATE_EXCLUDES`` already settles.
    """
    pattern = host_state_pattern(rel_path)
    if pattern is not None:
        return f"host_state:{pattern}"
    if await is_git_ignored(repo_root, pathspec):
        return "host_state:gitignored"
    return None
