# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Deletion-plan computation for the builtin updater (#16310).

Owner decision (#16310, recorded after review): deletion runs ansible-side,
right after each role's file-sync task succeeds -- one mechanism for
co-located and remote targets, never a second Python-applied path. This
module is the PLANNING library only: it decides WHICH component-relative
paths are safe to delete, using git history plus host-state/gitignore
filtering plus lexical containment. It never touches a filesystem itself.
``scripts/sync_deletion_planner.py`` wraps it as a CLI an ansible task calls
with ``delegate_to: localhost``; the actual removal is a `realpath`-checked
shell step on the target (refusing anything that resolves outside the
target root), and the target's own marker is slurped before this runs and
written after, by ansible -- see
``ansible/roles/_shared/tasks/sync_deletions.yml``.

Two plans:

* :func:`compute_deletion_plan` -- the previous commit is known (the
  target's marker). Every path ``git diff --diff-filter=DR`` names between
  it and the new commit, minus host state / gitignored / lexically unsafe.
* :func:`compute_bootstrap_plan` -- no marker exists yet (first run, or a
  component the SLM's own ``.deployed_commit`` never covered). The
  candidates are paths ansible's own ``find`` reports present on the
  target that git tracked at SOME point and does not track at the new
  commit, same filtering. Run at most once per component, per the owner's
  gating requirement -- enforced by the caller (the marker's absence IS the
  gate; this function does not re-check it).

Never reads or writes ``.deployed_commit`` -- that remains
``_get_slm_deployed_commit()``'s C4 self-update skip-gate (#12202), and a
read-only bootstrap of it (when this module's own marker is absent) is a
caller concern, not this module's.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from services.deploy_artifacts import ARTIFACT_DIR_SUFFIXES, ARTIFACT_DIRS
from services.git_subprocess import component_pathspec, run_git
from services.host_state_filter import kept_reason

# Plain stdlib logging, deliberately -- see services/git_subprocess.py's
# comment: get_logger() crashes at creation time under a MagicMock `config`,
# the precedent autobot_shared/user_management/password_epoch.py:50-58 sets.
logger = logging.getLogger(__name__)


@dataclass
class DeletionPlan:
    """What a plan decided: paths to delete, paths kept, or why it could not run."""

    delete: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    error: str | None = None
    # #16310 review round 12, N6: True when compute_deletion_plan's
    # previous_commit is unknown to this clone (a force-push or a re-clone
    # moved history out from under a target whose marker still names the old
    # commit). Without this, an unknown commit was a permanent `error` --
    # the ansible block's own rescue warns and skips FOREVER, never
    # advancing. The caller (sync_deletions.yml) treats this the same as no
    # marker existing at all: fall back to compute_bootstrap_plan, the same
    # one-time mode, rather than a fatal, repeating error.
    bootstrap_required: bool = False


async def _commit_known(repo_root: str, commit: str) -> bool:
    """True when *commit* exists in *repo_root*'s history.

    ``cat-file -e`` is the cheapest way to ask git "do you have this object"
    without also triggering the "unknown revision or path not in the working
    tree" failure a `git diff`/`git log` against an unknown commit would
    otherwise surface as an indistinguishable, permanent planner error.
    """
    _output, rc = await run_git(repo_root, "cat-file", "-e", f"{commit}^{{commit}}")
    return rc == 0


def _is_lexically_contained(rel_path: str) -> bool:
    """False for a path that could escape the deployed dir once joined (#16310 MEDIUM 3).

    The planner runs on the controller and cannot resolve symlinks on a
    possibly-remote target, so containment here is lexical: never an
    absolute path, never a ``..`` traversal segment. Ansible joins the
    result with the role's own target dir and deletes on the target.
    """
    if not rel_path or rel_path.startswith("/"):
        return False
    return ".." not in Path(rel_path).parts


def _name_status_paths(output: str, pathspec: str, *, take_new: bool) -> list[str]:
    """Component-relative paths a ``--name-status`` diff reports.

    An add/delete line is ``STATUS\\tpath``; a rename is
    ``R###\\told\\tnew``. *take_new* picks which side a rename contributes:
    False for a DR (delete-side) diff -- the OLD path is what the deployed
    tree must drop; True for an AR (add-side) diff -- the NEW path is what
    now (or once) existed under that name. ``-- pathspec`` scoping means
    every line here is already inside *pathspec* -- no further filtering
    needed, only stripping the prefix down to a deployed-relative path.
    """
    prefix = f"{pathspec}/" if pathspec else ""
    paths: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        repo_path = parts[-1] if take_new else parts[1]
        if not prefix or repo_path.startswith(prefix):
            paths.append(repo_path[len(prefix) :] if prefix else repo_path)
    return paths


async def _partition(candidates: list[str], repo_root: str, pathspec_prefix: str) -> tuple[list[str], list[str]]:
    """Split *candidates* into (safe-to-delete, kept)."""
    to_delete: list[str] = []
    kept: list[str] = []
    for rel in candidates:
        full_pathspec = f"{pathspec_prefix}/{rel}" if pathspec_prefix else rel
        if not _is_lexically_contained(rel):
            logger.warning("sync_deletions: refusing lexically unsafe candidate %s", rel)
            kept.append(rel)
            continue
        reason = await kept_reason(rel, repo_root, full_pathspec)
        if reason is None:
            to_delete.append(rel)
        else:
            kept.append(rel)
            logger.info("sync_deletions: keeping %s (%s)", rel, reason)
    return to_delete, kept


async def compute_deletion_plan(source_dir: str, repo_root: str, previous_commit: str, new_commit: str) -> DeletionPlan:
    """Every path git proves was deleted/renamed between two known commits."""
    if previous_commit == new_commit:
        return DeletionPlan()

    if not await _commit_known(repo_root, previous_commit):
        # #16310 review round 12, N6: fails SAFE -- deleting nothing this
        # run, same as the ordinary error path -- but tells the caller to
        # retry via bootstrap next, rather than repeating this exact failure
        # forever.
        logger.warning(
            "sync_deletions: previous commit %s is unknown to this clone -- falling back to bootstrap mode",
            previous_commit[:12],
        )
        return DeletionPlan(bootstrap_required=True)

    pathspec = component_pathspec(repo_root, source_dir)
    diff_output, rc = await run_git(
        repo_root, "diff", "-M", "--name-status", "--diff-filter=DR", f"{previous_commit}..{new_commit}", "--", pathspec
    )
    if rc != 0:
        return DeletionPlan(error=f"git diff {previous_commit[:12]}..{new_commit[:12]} failed")

    candidates = _name_status_paths(diff_output, pathspec, take_new=False)
    to_delete, kept = await _partition(candidates, repo_root, pathspec)
    return DeletionPlan(delete=to_delete, kept=kept)


def _strip_prefix(paths: list[str], pathspec: str) -> set[str]:
    prefix = f"{pathspec}/" if pathspec else ""
    return {p[len(prefix) :] if prefix else p for p in paths if not prefix or p.startswith(prefix)}


async def _tracked_paths_at_commit(repo_root: str, commit: str, pathspec: str) -> set[str] | None:
    """Every component-relative path git tracks at *commit*. None on git error."""
    output, rc = await run_git(repo_root, "ls-tree", "-r", "--name-only", commit, "--", pathspec)
    if rc != 0:
        return None
    return _strip_prefix(output.splitlines(), pathspec)


async def _ever_added_paths(repo_root: str, pathspec: str) -> set[str] | None:
    """Every component-relative path git has ever added OR renamed a file
    into, in ONE call (#16310 review: replaces a `git log -1`/`git cat-file
    -e` pair PER FILE, which took hours on a real backend/frontend node's
    first bootstrap).

    ``--diff-filter=AR`` with ``-M`` (rename detection is NOT on by default),
    not just ``A`` (#16310 review round 4, HIGH): a path that only ever
    arrived through a rename -- never a plain add under that exact name --
    would otherwise never appear in "ever tracked", and its stale copy would
    survive on every host forever, exactly what AC5 is about.
    """
    output, rc = await run_git(repo_root, "log", "-M", "--name-status", "--diff-filter=AR", "--format=", "--", pathspec)
    if rc != 0:
        return None
    return set(_name_status_paths(output, pathspec, take_new=True))


def _is_artifact_path(rel_path: str) -> bool:
    """True when any path segment is a build/deploy artifact (venv, node_modules, ...).

    Planner-side defence in depth (#16310 review): the ansible ``find`` that
    gathers *present_paths* already prunes these directories with the SAME
    ``ARTIFACT_DIRS``/``ARTIFACT_DIR_SUFFIXES`` vocabulary, so this only fires
    if that pruning is ever missed or bypassed -- it must never be the only
    guard.
    """
    return any(seg in ARTIFACT_DIRS or seg.endswith(ARTIFACT_DIR_SUFFIXES) for seg in rel_path.split("/"))


def _bootstrap_candidates(present_paths: list[str], ever_added: set[str], tracked_now: set[str]) -> list[str]:
    """*present_paths* git once added (or renamed something into) and does not track now.

    Residual risk, named for the caller: a file deleted from git long ago and
    put back on the host by other means (not this module's business, not
    synced content) would ALSO satisfy "added once, absent now". The owner's
    #16310 decision accepts that risk for the one-time bootstrap only -- see
    ``scripts/sync_deletion_planner.py``'s ``--help`` and
    ``ansible/roles/_shared/tasks/sync_deletions.yml``'s comment.
    """
    return [rel for rel in present_paths if not _is_artifact_path(rel) and rel in ever_added and rel not in tracked_now]


async def compute_bootstrap_plan(
    source_dir: str, repo_root: str, new_commit: str, present_paths: list[str]
) -> DeletionPlan:
    """One-time plan when no marker (dedicated or legacy) exists for this target.

    *present_paths* are component-relative paths ansible's own ``find``
    reported present on the target -- this module never touches a
    filesystem, so it cannot enumerate them itself. Exactly two git calls
    total, never one per file: every path tracked at *new_commit*, and every
    path git has ever added or renamed something into.
    """
    pathspec_prefix = component_pathspec(repo_root, source_dir)
    tracked_now = await _tracked_paths_at_commit(repo_root, new_commit, pathspec_prefix)
    if tracked_now is None:
        return DeletionPlan(error=f"git ls-tree at {new_commit[:12]} failed")
    ever_added = await _ever_added_paths(repo_root, pathspec_prefix)
    if ever_added is None:
        return DeletionPlan(error="git log --diff-filter=AR failed")

    candidates = _bootstrap_candidates(present_paths, ever_added, tracked_now)
    to_delete, kept = await _partition(candidates, repo_root, pathspec_prefix)
    return DeletionPlan(delete=to_delete, kept=kept)
