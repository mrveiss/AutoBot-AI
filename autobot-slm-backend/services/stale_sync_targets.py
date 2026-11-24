# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which files under the OLD code-sync targets are stale: the planning half, no filesystem and no ssh (#22033).

Before #22030 the code-sync rsynced the backend, frontend, SLM backend and SLM frontend roles into the install
root itself and the SLM agent into the agent directory; each role now has its own directory. The copies the old
sync left behind are stale, but an install root also holds host state and other roles' directories, so "no
tracked source maps to it" is not proof. A present file is stale ONLY when it is byte-identical to some version
git ever tracked at that path of that role's source (owner decision D2): anything else is kept and reported as
``modified_on_host``. Old targets are derived from the roles' corrected ``target_path`` (which already honours
AUTOBOT_BASE_DIR / SLM_AGENT_DIR), so no path literal lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Iterable, Mapping

from services.deploy_artifacts import is_host_generated
from services.git_subprocess import ShallowCheck, is_shallow_repository, run_git_capture
from services.host_state_filter import host_state_pattern
from services.sync_deletions import is_artifact_path, is_lexically_contained, strip_prefix

#: The roles #22030 moved, and how many trailing path segments their corrected target adds to the old one
#: (the old target of the backend is ``{base_dir}``, of the agent ``{agent_dir}`` for ``{agent_dir}/slm/agent``).
MOVED_ROLES: dict[str, int] = {"backend": 1, "frontend": 1, "slm-backend": 1, "slm-frontend": 1, "slm-agent": 2}

KEPT_MODIFIED = "modified_on_host"
KEPT_HOST_STATE = "host_state"
KEPT_ARTIFACT = "artifact"
KEPT_CLAIMED = "claimed_by_corrected_target"
KEPT_UNSAFE = "unsafe_name"

_NO_BLOB = "0" * 40


class StaleListingError(Exception):
    """The listing cannot be trusted (shallow clone, git failure, node unreachable); it names why."""


@dataclass(frozen=True)
class RoleSource:
    """One moved role: where the old sync put its files, where the source lives in git, and the new target."""

    role: str
    old_target: str
    corrected_target: str
    pathspec: str


@dataclass(frozen=True)
class PresentFile:
    """A regular, non-symlink file found on the node, with the git blob id of its content."""

    rel: str
    size: int
    mtime: int
    blob: str


@dataclass(frozen=True)
class StaleFile:
    """A file safe to offer for removal: byte-identical to a version git tracked at that path."""

    old_target: str
    role: str
    path: str
    size_bytes: int
    modified_at: datetime
    blob: str


@dataclass(frozen=True)
class KeptFile:
    """A file under an old target that is NOT offered, with the named reason."""

    old_target: str
    path: str
    reason: str


def old_target_of(corrected_target: str, depth: int) -> str | None:
    """*corrected_target* minus its last *depth* segments; None when that would be the filesystem root or nothing."""
    path = PurePosixPath(corrected_target)
    if not path.is_absolute() or depth < 1 or len(path.parts) <= depth + 1:
        return None
    return str(path.parents[depth - 1])


def moved_role_sources(roles: Iterable[Mapping], moved: Mapping[str, int] = MOVED_ROLES) -> list[RoleSource]:
    """The moved roles among *roles* (``DEFAULT_ROLES`` shape), each with its old target and source pathspec."""
    sources = []
    for role in roles:
        depth, target, paths = moved.get(role.get("name")), role.get("target_path"), role.get("source_paths") or []
        old = old_target_of(target, depth) if depth and isinstance(target, str) and paths else None
        if old is not None:
            sources.append(RoleSource(role["name"], old, target, str(paths[0]).strip("/")))
    return sources


def parse_raw_log(output: str, pathspec: str) -> dict[str, set[str]]:
    """``git log --raw --no-abbrev`` -> {path relative to *pathspec*: every blob id git tracked at it}.

    A deletion (all-zero blob) adds nothing; a rename adds the NEW blob at the new path. A path git quotes
    (a double quote, a control character) is skipped: it can never be offered.
    """
    blobs: dict[str, set[str]] = {}
    for line in output.splitlines():
        head, _, tail = line.partition("\t")
        fields = head.split()
        if not line.startswith(":") or len(fields) < 5 or fields[4][0] not in "AMRC":
            continue
        path, blob = tail.split("\t")[-1], fields[3]
        if blob != _NO_BLOB and not path.startswith('"'):
            for rel in strip_prefix([path], pathspec):
                blobs.setdefault(rel, set()).add(blob)
    return blobs


async def historical_blobs(repo_root: str, pathspec: str) -> dict[str, set[str]]:
    """Every blob git ever had at each path under *pathspec*; raises :class:`StaleListingError` when it cannot know.

    One git call. ``--diff-merges=separate`` diffs a merge against each parent, so a version only a merge
    resolution introduced is tracked too (plain ``git log`` shows no diff for a merge). A shallow or
    undeterminable clone cannot answer: an empty history there would read as "nothing is stale", so it is an
    error instead (the same refusal as ``compute_bootstrap_plan``).
    """
    if await is_shallow_repository(repo_root) is not ShallowCheck.FULL:
        raise StaleListingError("the code_source clone is shallow or its depth is unknown; unshallow it and retry")
    output, rc = await run_git_capture(
        repo_root, "log", "-M", "--raw", "--no-abbrev", "--diff-merges=separate", "--format=", "--", pathspec
    )
    if rc != 0:
        raise StaleListingError("git log of the source history failed")
    return parse_raw_log(output, pathspec)


def kept_reason_for(source: RoleSource, rel: str) -> str | None:
    """Why *rel* may never be a candidate for *source*'s role, or None."""
    if not rel.isprintable() or not is_lexically_contained(rel):
        return KEPT_UNSAFE
    if is_artifact_path(rel):
        return KEPT_ARTIFACT
    if host_state_pattern(rel) is not None or is_host_generated(PurePosixPath(source.pathspec).name, rel):
        return KEPT_HOST_STATE
    return None


def is_claimed(old_target: str, rel: str, protected_dirs: Iterable[str]) -> bool:
    """Whether the file lies inside (or is) a directory the corrected sync, or code_source, now owns."""
    path = PurePosixPath(old_target) / rel
    return any(path == PurePosixPath(d) or PurePosixPath(d) in path.parents for d in protected_dirs if d)


def candidates(
    source: RoleSource, history: Mapping[str, set[str]], protected: Iterable[str]
) -> tuple[list[str], list[KeptFile]]:
    """The relative paths to look for on the node for *source*, and the paths refused up front."""
    wanted, kept = [], []
    for rel in sorted(history):
        reason = kept_reason_for(source, rel) or (
            KEPT_CLAIMED if is_claimed(source.old_target, rel, protected) else None
        )
        if reason:
            kept.append(KeptFile(source.old_target, rel, reason))
        else:
            wanted.append(rel)
    return wanted, kept


def classify(
    source: RoleSource, present: Iterable[PresentFile], history: Mapping[str, set[str]]
) -> tuple[list[StaleFile], list[KeptFile]]:
    """Split the files found on the node: byte-identical to a tracked version -> stale; anything else -> kept."""
    stale, kept = [], []
    for found in present:
        if found.blob in history.get(found.rel, ()):
            modified = datetime.fromtimestamp(found.mtime, tz=timezone.utc)
            stale.append(StaleFile(source.old_target, source.role, found.rel, found.size, modified, found.blob))
        else:
            kept.append(KeptFile(source.old_target, found.rel, KEPT_MODIFIED))
    return stale, kept
