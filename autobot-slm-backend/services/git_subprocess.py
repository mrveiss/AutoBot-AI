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
# This module is imported (via services/sync_deletions.py) by api/code_sync.py,
# whose test harness (tests/api/test_collect_outdated_node_ids.py) stubs
# `config` as a MagicMock; logging_manager.get_logger() builds a
# RotatingFileHandler that compares that MagicMock to an int and raises at
# logger-CREATION time. Same precedent as
# autobot_shared/user_management/password_epoch.py:50-58.
logger = logging.getLogger(__name__)

# Bounds every subprocess below. A cold `git diff`/`git log` over a
# monorepo-sized range is fast, but a hung git process (a wedged fsmonitor, an
# interactive credential prompt on a misconfigured remote) must not stall a
# sync or a drift check indefinitely (#16310).
GIT_TIMEOUT_S = env_float("AUTOBOT_SYNC_GIT_TIMEOUT_S", 30.0)


async def run_git(repo_root: str, *args: str, timeout: float = GIT_TIMEOUT_S) -> tuple[str, int]:
    """Run ``git -C repo_root <args>`` with a scrubbed env and bounded timeout.

    Returns ``(stdout, returncode)``. A timeout or spawn failure returns
    ``("", 1)`` -- never raises, so a wedged git process degrades the caller
    to "nothing found" rather than crashing it.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
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
