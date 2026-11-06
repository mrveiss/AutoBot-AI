# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The commits an operator may roll back to, and the validation of the one chosen (#20214).

Only ancestors of the tracked branch's remote head are offered, so a rollback can never deploy
code that was not reviewed into ``main``. The list carries dates and subjects: the operator picks
a line, never types an id. The id that comes back is still treated as untrusted input: it must be
a full commit id, pass the shared safe-ref check, name a commit that exists, and be an ancestor of
the remote head before anything else runs.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.git_refs import is_safe_ref
from autobot_shared.logging_manager import get_logger
from services.git_subprocess import run_git_capture
from services.rollback_target import is_full_sha

logger = get_logger(__name__)

#: How many recent commits the picker offers. Env-backed; the clamp keeps a typo from asking git for the whole history.
ROLLBACK_CANDIDATE_LIMIT = env_int_clamped("SLM_ROLLBACK_CANDIDATE_LIMIT", 50, 1, 500)

_FIELD_SEP = "\x1f"
_LOG_FORMAT = f"%H{_FIELD_SEP}%cI{_FIELD_SEP}%s"
_NOT_AN_ANCESTOR = 1

#: The module that reads a rollback's ref out of the resume plan after the SLM restarts onto the target.
#: A commit without it cannot finish a rollback: it restarts, ignores the ref, and updates the fleet to ``main``.
ROLLBACK_SUPPORT_PATH = "autobot-slm-backend/services/rollback_target.py"
PREDATES_ROLLBACK = "This version predates rollback support, so it cannot be rolled back to."


class RollbackRefused(Exception):
    """The request cannot proceed; ``reason`` is written for the operator."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class CommitInfo:
    commit: str
    date: str
    subject: str

    @property
    def short(self) -> str:
        return self.commit[:12]


def remote_ref(remote: str, branch: str) -> str:
    """The remote-tracking ref candidates are measured against, e.g. ``origin/main``."""
    ref = f"{remote}/{branch}"
    if not is_safe_ref(ref):
        raise RollbackRefused("The tracked branch name is not a valid git ref.")
    return ref


def _parse_log(output: str) -> list[CommitInfo]:
    commits = []
    for line in output.splitlines():
        parts = line.split(_FIELD_SEP, 2)
        if len(parts) == 3 and is_full_sha(parts[0]):
            commits.append(CommitInfo(commit=parts[0], date=parts[1], subject=parts[2]))
    return commits


async def supports_rollback(repo: str, commit: str) -> bool:
    """True when ``commit`` ships the code that carries a rollback across the SLM's restart."""
    if not is_full_sha(commit):
        return False
    _, rc = await run_git_capture(repo, "cat-file", "-e", f"{commit}:{ROLLBACK_SUPPORT_PATH}")
    return rc == 0


async def list_candidates(
    repo: str, remote: str, branch: str, limit: int = ROLLBACK_CANDIDATE_LIMIT
) -> list[CommitInfo]:
    """The newest ``limit`` commits reachable from the remote head, newest first."""
    ref = remote_ref(remote, branch)
    stdout, rc = await run_git_capture(repo, "log", f"--max-count={int(limit)}", f"--format={_LOG_FORMAT}", ref)
    if rc != 0:
        raise RollbackRefused("The commit history could not be read from the code source.")
    commits = _parse_log(stdout)
    flags = await asyncio.gather(*(supports_rollback(repo, c.commit) for c in commits))
    return [c for c, ok in zip(commits, flags) if ok]


async def describe_commit(repo: str, commit: str) -> CommitInfo | None:
    """Date and subject of one validated commit id, or None when git cannot show it."""
    if not is_full_sha(commit):
        return None
    stdout, rc = await run_git_capture(repo, "log", "-1", f"--format={_LOG_FORMAT}", commit)
    parsed = _parse_log(stdout) if rc == 0 else []
    return parsed[0] if parsed else None


async def resolve_target(repo: str, remote: str, branch: str, commit: object) -> CommitInfo:
    """Validate an operator-chosen commit server-side; raise ``RollbackRefused`` unless it may be deployed.

    Nothing user-supplied reaches git until it is a full 40-hex id that also passes the shared
    safe-ref check, which a leading dash or any option-like text cannot.
    """
    if not is_full_sha(commit):
        raise RollbackRefused("Choose a commit from the list; the selection was not a valid commit.")
    head = remote_ref(remote, branch)
    _, rc = await run_git_capture(repo, "cat-file", "-e", f"{commit}^{{commit}}")
    if rc != 0:
        raise RollbackRefused("That commit is not in the code source. Refresh the list and choose again.")
    _, rc = await run_git_capture(repo, "merge-base", "--is-ancestor", commit, head)
    if rc == _NOT_AN_ANCESTOR:
        raise RollbackRefused(f"That commit is not part of {branch}'s history, so it cannot be deployed.")
    if rc != 0:
        raise RollbackRefused("Whether that commit belongs to the branch history could not be determined.")
    if not await supports_rollback(repo, commit):
        raise RollbackRefused(PREDATES_ROLLBACK)
    info = await describe_commit(repo, commit)
    if info is None:
        raise RollbackRefused("The chosen commit could not be read from the code source.")
    return info
