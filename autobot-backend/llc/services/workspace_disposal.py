# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Whether a reclaimed workspace may be removed, and the removal itself (#16818 AC7).

Reclaiming a lease frees a slot. It says nothing about whether the directory still
holds the only copy of something. This module is the second gate, and it answers one
question: **is this workspace's work demonstrably on the remote?**

The shell script this replaces already got the hard part right -- it asked "would
anything be lost?" rather than "did this land?" -- and that judgement is kept here
rather than re-derived. What it could not do was record the answer anywhere, because
the domain had nothing to record it against.

Three outcomes, never two. ``LANDED`` authorises removal. ``NOT_LANDED`` refuses it
and says what is unpushed. ``UNKNOWN`` refuses it too, but for a different reason:
the question could not be answered -- git failed, the path is gone, the branch is
unknown. Collapsing ``UNKNOWN`` into ``NOT_LANDED`` would be safe; collapsing it into
``LANDED`` would delete work whenever git happened to error, so the two refusals are
kept apart to stop anyone later "simplifying" them in the wrong direction.

Removal is ``git worktree remove`` without ``--force``, deliberately. Git refuses a
worktree with uncommitted changes, and that refusal is information -- a workspace
that will not go is a workspace someone should look at. Forcing it would convert
every one of those signals into silent data loss.
"""

import asyncio
import logging
import os
from enum import Enum
from pathlib import Path
from typing import NamedTuple, Optional

from autobot_shared.paths import scrubbed_git_env

logger = logging.getLogger(__name__)

GIT_TIMEOUT_SECONDS = 30


class DisposalVerdict(str, Enum):
    """Whether a workspace's work is safely on the remote."""

    LANDED = "landed"
    NOT_LANDED = "not_landed"
    UNKNOWN = "unknown"


class DisposalCheck(NamedTuple):
    """A verdict and the evidence for it, so a refusal can be acted on."""

    verdict: DisposalVerdict
    detail: str

    @property
    def may_dispose(self) -> bool:
        """Only an affirmative answer authorises removal. Both refusals refuse."""
        return self.verdict is DisposalVerdict.LANDED


async def _git(*args: str, cwd: Optional[str] = None) -> tuple[int, str]:
    """Run git, returning (returncode, combined output stripped).

    A non-zero return is a normal outcome here, not an exception: "this branch has
    no upstream" is an answer. Only a failure to run git at all is exceptional, and
    that surfaces as a negative return code so the caller reports UNKNOWN.

    ``env=scrubbed_git_env()`` is load-bearing, not hygiene (#15783). ``GIT_DIR``
    outranks ``cwd=``, so an inherited one would make every check below answer about
    whatever repository the environment names -- with a zero exit code. A LANDED
    verdict read off the wrong repository authorises removing a workspace whose work
    was never pushed, which is the one outcome this module exists to prevent.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=cwd,
            env=scrubbed_git_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=GIT_TIMEOUT_SECONDS)
        return process.returncode or 0, stdout.decode("utf-8", errors="replace").strip()
    except asyncio.TimeoutError as exc:
        # `wait_for` cancels the await; it does not stop the child. Without this the
        # git process outlives the sweep that gave up on it, holding the worktree it
        # was asked about -- and this sweep's whole job is deciding whether that
        # directory is safe to remove (#17725 review).
        process.kill()
        await process.wait()
        logger.warning(
            "#16818: git %s timed out in %s after %ss, child killed", " ".join(args), cwd, GIT_TIMEOUT_SECONDS
        )
        return -1, f"{type(exc).__name__}: {exc}"
    except OSError as exc:
        logger.warning("#16818: git %s failed in %s: %s", " ".join(args), cwd, exc)
        return -1, f"{type(exc).__name__}: {exc}"


async def work_landed(path: str, branch: Optional[str] = None) -> DisposalCheck:
    """Whether everything in *path* is reachable from a remote ref.

    Checks, in order, the three ways a workspace can still be the only copy:
    uncommitted changes, commits that are not on any remote, and a path or branch
    the question cannot even be asked about.
    """
    if not path or not os.path.isdir(path):
        return DisposalCheck(DisposalVerdict.UNKNOWN, f"no directory at {path!r} to inspect")

    code, out = await _git("status", "--porcelain", cwd=path)
    if code < 0:
        return DisposalCheck(DisposalVerdict.UNKNOWN, f"could not read worktree status: {out}")
    if code != 0:
        return DisposalCheck(DisposalVerdict.UNKNOWN, f"not a usable git worktree: {out}")
    if out:
        changed = len(out.splitlines())
        return DisposalCheck(DisposalVerdict.NOT_LANDED, f"{changed} uncommitted change(s) in the worktree")

    # Commits reachable from HEAD but from no remote-tracking ref. This is the
    # question that matters and the one a branch-name comparison gets wrong: a
    # branch can exist on the remote and still be behind what is here.
    code, out = await _git("log", "--oneline", "-5", "HEAD", "--not", "--remotes", cwd=path)
    if code < 0:
        return DisposalCheck(DisposalVerdict.UNKNOWN, f"could not compare against remotes: {out}")
    if code != 0:
        return DisposalCheck(DisposalVerdict.UNKNOWN, f"could not resolve HEAD against remotes: {out}")
    if out:
        unpushed = len(out.splitlines())
        return DisposalCheck(
            DisposalVerdict.NOT_LANDED,
            f"{unpushed} commit(s) reachable from HEAD are on no remote: {out.splitlines()[0]}",
        )

    where = f"branch {branch}" if branch else "HEAD"
    return DisposalCheck(DisposalVerdict.LANDED, f"{where} is fully present on a remote; nothing would be lost")


async def dispose_workspace(path: str, branch: Optional[str] = None) -> DisposalCheck:
    """Remove *path* if -- and only if -- its work is demonstrably on the remote.

    Returns the check that decided it. On refusal nothing is touched and the detail
    says what is in the way, which is the state the fleet actually wants: a workspace
    held back with a reason beats one removed on an assumption.
    """
    check = await work_landed(path, branch)
    if not check.may_dispose:
        logger.info("#16818: keeping workspace %s -- %s (%s)", path, check.detail, check.verdict.value)
        return check

    # `worktree remove` must run inside the repository that OWNS the worktree, and
    # it cannot run inside the worktree being removed -- git refuses to remove the
    # tree it is standing in. So neither the inherited cwd nor `cwd=path` works: the
    # first makes the answer depend on wherever the worker happens to live, the
    # second is refused outright. Resolve the owner from the worktree itself.
    code, common = await _git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=path)
    if code != 0:
        logger.warning("#16818: cannot resolve the repository owning workspace %s: %s", path, common)
        return DisposalCheck(DisposalVerdict.UNKNOWN, f"owning repository not resolvable: {common}")
    owner = str(Path(common.strip()).parent)

    # No --force: git refuses a worktree it considers unsafe to remove, and that
    # refusal is a finding rather than an obstacle.
    code, out = await _git("worktree", "remove", path, cwd=owner)
    if code != 0:
        logger.warning("#16818: git declined to remove workspace %s: %s", path, out)
        return DisposalCheck(DisposalVerdict.UNKNOWN, f"git refused the removal: {out}")

    logger.info("#16818: disposed of workspace %s -- %s", path, check.detail)
    return check


__all__ = [
    "DisposalCheck",
    "DisposalVerdict",
    "dispose_workspace",
    "work_landed",
]
