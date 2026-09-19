# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared scrubbed-env git subprocess runner (#16310).

Split out of ``services/sync_deletions.py`` so ``services/full_tree_drift.py``
does not import a leading-underscore (module-private) helper from a sibling
module -- both need to run a bounded, env-scrubbed ``git`` subprocess against
the code_source checkout, and this is the one place that does it.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from autobot_shared.env_utils import env_float
from autobot_shared.paths import scrubbed_git_env

# Plain stdlib logging, deliberately -- NOT autobot_shared.logging_manager.
# This module is imported (via services/full_tree_drift.py, api/full_tree_drift.py)
# by api/code_sync.py, whose test harness
# (tests/api/test_collect_outdated_node_ids.py) stubs `config` as a MagicMock;
# logging_manager.get_logger() builds a RotatingFileHandler that compares
# that MagicMock to an int and raises at logger-CREATION time. Same
# precedent as autobot_shared/user_management/password_epoch.py:50-58.
logger = logging.getLogger(__name__)

# Bounds every subprocess below. A cold `git diff`/`git log` over a
# monorepo-sized range is fast, but a hung git process (a wedged fsmonitor, an
# interactive credential prompt on a misconfigured remote) must not stall a
# sync or a drift check indefinitely (#16310).
GIT_TIMEOUT_S = env_float("AUTOBOT_SYNC_GIT_TIMEOUT_S", 30.0)

# `git fetch --unshallow` downloads the ENTIRE history the shallow clone
# skipped -- on a monorepo-sized checkout that is minutes, not seconds, so it
# gets its own, longer bound rather than sharing GIT_TIMEOUT_S (#16310).
UNSHALLOW_TIMEOUT_S = env_float("AUTOBOT_SYNC_UNSHALLOW_TIMEOUT_S", 600.0)


async def run_git(repo_root: str, *args: str, timeout: float = GIT_TIMEOUT_S) -> tuple[str, int]:
    """Run ``git -C repo_root <args>`` with a scrubbed env and bounded timeout.

    ``-c core.quotePath=false`` (#16310 review 3a): git C-style-quotes any
    path with a non-ASCII byte by default (``"fooe\\301.py"`` instead of the
    literal name), so the tracked set (from git) and the present set (from a
    plain filesystem walk) would disagree for every such file. Every caller
    in this repo parses this command's output as a plain path string, so the
    flag belongs here once rather than on each call site.

    Returns ``(stdout, returncode)``. A timeout or spawn failure returns
    ``("", 1)`` -- never raises, so a wedged git process degrades the caller
    to "nothing found" rather than crashing it.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-c",
            "core.quotePath=false",
            "-C",
            repo_root,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=scrubbed_git_env(),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            logger.warning("git %s failed: %s", " ".join(args), stderr.decode("utf-8", errors="replace")[:300])
            return "", proc.returncode
        return stdout.decode("utf-8", errors="replace"), 0
    except (asyncio.TimeoutError, OSError) as exc:
        logger.warning("git %s error: %s", " ".join(args), exc)
        return "", 1


def component_pathspec(repo_root: str, source_dir: str) -> str:
    """POSIX path of *source_dir* relative to *repo_root*, for a git pathspec.

    Driven by the actual resolved source directory rather than the component
    name, so components whose source lives outside the standard
    ``code_source/<component>`` layout (ai-stack, slm-agent, plugins -- see
    ``drift_checker._NONSTANDARD_COMPONENT_PATHS``) still diff correctly.
    """
    return Path(source_dir).resolve().relative_to(Path(repo_root).resolve()).as_posix()


async def is_shallow_repository(repo_root: str) -> bool:
    """True when *repo_root* is a shallow git clone (#16310).

    Shared by :func:`ensure_full_history` (fixes it) and
    ``services/sync_deletions.py``'s bootstrap guard (refuses to plan against
    it) -- one answer to "is this clone shallow", asked with the same `git
    rev-parse` both callers would otherwise duplicate.
    """
    output, rc = await run_git(repo_root, "rev-parse", "--is-shallow-repository")
    return rc == 0 and output.strip() == "true"


async def ensure_full_history(repo_root: str) -> tuple[bool, str]:
    """Unshallow *repo_root* in place if it is a shallow clone (#16310).

    A shallow ``code_source`` checkout makes
    ``services.sync_deletions.compute_bootstrap_plan``'s ``git log
    --diff-filter=AR`` see only the commits the shallow fetch kept, so it
    silently finds almost nothing to delete. The clone came from initial
    provisioning, before anything here passed ``--depth`` -- so the fix is
    not "never create a shallow clone" (nothing does), it is "never leave
    one shallow": every fetch of the source checkout ensures full depth
    first.

    Returns ``(ok, message)``. ``ok`` is False on an unshallow that failed,
    or on one that ran and reported success but left the repository shallow
    anyway -- the caller must fail loudly on either, never proceed as if
    full history is now available (that is exactly how the original bug
    stayed invisible: an empty, error-free bootstrap plan that still wrote
    the marker).
    """
    if not await is_shallow_repository(repo_root):
        return True, f"{repo_root} already has full history"

    logger.info("git_subprocess: %s is a shallow clone -- unshallowing (#16310)", repo_root)
    _output, rc = await run_git(repo_root, "fetch", "--unshallow", timeout=UNSHALLOW_TIMEOUT_S)
    if rc != 0:
        return False, f"git fetch --unshallow failed in {repo_root}"

    if await is_shallow_repository(repo_root):
        return False, f"{repo_root} is still a shallow clone after `git fetch --unshallow`"

    return True, f"{repo_root} unshallowed"


async def last_commit_for_path(repo_root: str, pathspec: str) -> str | None:
    """Full SHA of the last commit that touched *pathspec*, or None if never tracked.

    Shared by ``services/full_tree_drift.py`` (removed_from_source verdict) and
    ``scripts/sync_deletion_planner.py``'s bootstrap plan (#16310): both ask
    the same question -- "did git ever track this path?" -- against a commit
    range too wide for a name-status diff to answer.
    """
    output, rc = await run_git(repo_root, "log", "-1", "--format=%H", "--", pathspec)
    sha = output.strip()
    return sha if rc == 0 and sha else None
