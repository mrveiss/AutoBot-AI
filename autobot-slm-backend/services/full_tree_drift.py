# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""All-file drift verdicts across every deployed component (#16310).

The original drift check (``services/drift_checker.py``, Issue #2834) only
ever compared a fixed extension allowlist (``.py``/``.yaml``/``.vue``/...) and
folded every file present on the host but absent from source into a single
``untracked`` bucket that was excluded from ``drift_detected`` outright. That
hid the exact failure this issue is about: a file DELETED from source reads
identically to a file that was never tracked, so "drift-free" stopped meaning
anything.

Owner requirement, 11 Sep 2026: every file gets one of four verdicts, and
every exclusion is named and counted, never silently dropped:

* ``modified``            -- present on both sides, checksums disagree
* ``removed_from_source``  -- present only on the host; git proves it WAS
                               tracked (the commit that removed it is named)
* ``build_bundle``        -- an expected deploy/publish artifact (a
                               ``dist-<id>/`` release bundle, ``current``/
                               ``previous`` symlinks, venv, node_modules, ...)
* ``host_state``           -- present only on the host; git has never tracked
                               this path at all (runtime or host-generated
                               state), named by its declared category or
                               ``host_state:unclassified`` when nothing
                               declares it -- unclassified is still counted,
                               never dropped (#16310).

Only ``modified`` and ``removed_from_source`` count as drift. Runs over every
component in ``drift_checker.VISIBILITY_COMPONENTS`` in one pass -- the
resolve-capable components, the read-only extras, and ``autobot_shared``
together -- rather than one component at a time.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from autobot_shared.time_utils import utc_timestamp
from services.deploy_artifacts import ARTIFACT_DIR_SUFFIXES, ARTIFACT_DIRS
from services.deployed_dir_resolver import get_live_dir
from services.drift_checker import VISIBILITY_COMPONENTS, deploy_only_entries, get_default_source_dir, owned_subtrees
from services.git_subprocess import component_pathspec, last_commit_for_path
from services.git_tracker import DEFAULT_REPO_PATH
from services.host_state_filter import kept_reason

# Plain stdlib logging, deliberately -- see services/git_subprocess.py's
# comment: get_logger() crashes at creation time under a MagicMock `config`,
# the precedent autobot_shared/user_management/password_epoch.py:50-58 sets.
logger = logging.getLogger(__name__)

# Top-level names the SLM frontend publish step owns (services/
# slm_frontend_build.py's _BUILD_PREFIX/_CURRENT_LINK/_PREVIOUS_LINK/
# _LEGACY_DIR, plus the pre-#15610 dist.previous/ this issue also retires):
# expected release artifacts at ANY retention depth -- the publish step's own
# SLM_FRONTEND_RELEASE_KEEP pruning is what bounds them, not this check.
_BUILD_BUNDLE_PREFIX = "dist-"
_BUILD_BUNDLE_NAMES = frozenset({"current", "previous", "dist", "dist.previous"})

# Drift verdicts. Only the first two are drift; the rest are named exclusions.
VERDICT_MODIFIED = "modified"
VERDICT_REMOVED_FROM_SOURCE = "removed_from_source"
VERDICT_BUILD_BUNDLE = "build_bundle"
VERDICT_HOST_STATE = "host_state"


@dataclass
class FileVerdict:
    """One deployed-relative path and the verdict it earned."""

    path: str
    verdict: str
    detail: str | None = None  # e.g. the short commit that removed it


@dataclass
class ComponentDrift:
    """One component's full-tree drift result."""

    component: str
    compared: int = 0
    drifted: list[FileVerdict] = field(default_factory=list)
    exclusions: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    skipped: bool = False  # not colocated on this host -- legitimate, not an error


def _bump(exclusions: dict[str, int], name: str) -> None:
    exclusions[name] = exclusions.get(name, 0) + 1


def _sha256(path: Path, block_size: int = 65536) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(block_size):
            digest.update(chunk)
    return digest.hexdigest()


def _is_build_bundle_top(name: str) -> bool:
    return name in _BUILD_BUNDLE_NAMES or name.startswith(_BUILD_BUNDLE_PREFIX)


def _prune_reason(rel_dir: str, name: str, owned: frozenset[str]) -> str | None:
    """Exclusion bucket name for a directory the walk must not descend into, or None."""
    if name in ARTIFACT_DIRS or name.endswith(ARTIFACT_DIR_SUFFIXES):
        return f"artifact:{name}"
    rel = name if rel_dir in ("", ".") else f"{rel_dir}/{name}"
    if any(rel == sub or rel.startswith(f"{sub}/") for sub in owned):
        return "owned_by_other_component"
    if rel_dir in ("", ".") and _is_build_bundle_top(name):
        return VERDICT_BUILD_BUNDLE
    return None


def _can_list(root: Path) -> bool:
    """False when *root* itself cannot even be scanned (unreadable, not merely empty)."""
    try:
        next(os.walk(root))
        return True
    except (StopIteration, OSError) as exc:
        logger.error("full_tree_drift: cannot list %s: %s", root, exc)
        return False


def _prune_dirnames(dirpath: Path, root: Path, dirnames: list[str], owned: frozenset[str], exclusions: dict) -> None:
    """Filter *dirnames* in place, tallying every pruned reason."""
    rel_dir = dirpath.relative_to(root).as_posix()
    kept = []
    for name in dirnames:
        reason = _prune_reason(rel_dir, name, owned)
        if reason is None:
            kept.append(name)
        else:
            _bump(exclusions, reason)
    dirnames[:] = kept


def _checksum_files(dirpath: Path, root: Path, filenames: list[str], checksums: dict[str, str]) -> None:
    for filename in filenames:
        filepath = dirpath / filename
        rel = filepath.relative_to(root).as_posix()
        try:
            checksums[rel] = _sha256(filepath)
        except OSError as exc:
            logger.warning("full_tree_drift: cannot read %s: %s", filepath, exc)


def _walk_checksums(root: Path, owned: frozenset[str], exclusions: dict[str, int]) -> dict[str, str] | None:
    """Every file under *root*, sha256'd, minus artifact/owned/bundle dirs.

    Returns ``None`` when *root* itself cannot be listed -- an unreadable
    tree, distinct from an empty-but-readable one (#16310).
    """
    if not _can_list(root):
        return None

    checksums: dict[str, str] = {}
    onerror = lambda exc: logger.warning("full_tree_drift: %s", exc)  # noqa: E731
    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror):
        _prune_dirnames(Path(dirpath), root, dirnames, owned, exclusions)
        _checksum_files(Path(dirpath), root, filenames, checksums)
    return checksums


def _classify_host_state(rel_path: str, component: str) -> str:
    """Named exclusion bucket for a deployed file git has never tracked.

    Falls back to ``host_state:unclassified`` rather than dropping the file
    silently -- "clean" must never mean "did not look" (#16310).
    """
    if rel_path in deploy_only_entries(component):
        return f"deploy_only:{rel_path}"
    top = rel_path.split("/", 1)[0]
    if _is_build_bundle_top(top):
        return VERDICT_BUILD_BUNDLE
    if rel_path == ".deployed_commit":
        return "host_state:deployed_commit_marker"
    if top in ("data", "logs"):
        return f"host_state:{top}"
    if top == "config":
        return "host_state:config"
    if top.startswith(".env"):
        return "host_state:env"
    if top == "ansible":
        return "host_state:ansible"
    return "host_state:unclassified"


async def _classify_deployed_only(
    rel_path: str, component: str, repo_root: str, pathspec_prefix: str
) -> tuple[str, str | None]:
    """Verdict and detail for a file present only in the deployed tree.

    #16310 review (MEDIUM 4): the host-state/ignored check runs BEFORE the
    git-history check. A file that was ``git rm --cached`` then gitignored
    still has history -- checking history first would label it
    ``removed_from_source`` and steer an operator into deleting a live key
    by hand, exactly the #16300 pattern ``services/host_state_filter.py``
    exists to catch.
    """
    pathspec = f"{pathspec_prefix}/{rel_path}" if pathspec_prefix else rel_path
    reason = await kept_reason(rel_path, repo_root, pathspec)
    if reason is not None:
        return VERDICT_HOST_STATE, reason
    commit = await last_commit_for_path(repo_root, pathspec)
    if commit is not None:
        return VERDICT_REMOVED_FROM_SOURCE, commit[:12]
    return VERDICT_HOST_STATE, _classify_host_state(rel_path, component)


def _resolve_component_trees(component: str) -> tuple[str, str] | ComponentDrift:
    """(source_dir, deployed_dir), or an early terminal result (skipped/error)."""
    deployed_dir = get_live_dir(component)
    if not Path(deployed_dir).exists():
        return ComponentDrift(component=component, skipped=True)  # not colocated here
    try:
        source_dir = get_default_source_dir(component)
    except ValueError as exc:
        return ComponentDrift(component=component, error=f"source path unavailable: {exc}")
    return source_dir, deployed_dir


def _collect_both_checksums(
    source_dir: str, deployed_dir: str, owned: frozenset[str], exclusions: dict[str, int]
) -> tuple[dict[str, str], dict[str, str]] | str:
    """(deployed, source) checksums, or an error string naming which side failed."""
    dep_checksums = _walk_checksums(Path(deployed_dir), owned, exclusions)
    if dep_checksums is None:
        return f"deployed tree unreadable: {deployed_dir}"
    if not dep_checksums:
        return f"deployed tree is empty: {deployed_dir}"
    src_checksums = _walk_checksums(Path(source_dir), frozenset(), {})
    if src_checksums is None:
        return f"source tree unreadable: {source_dir}"
    return dep_checksums, src_checksums


async def _classify_all_paths(
    dep_checksums: dict[str, str],
    src_checksums: dict[str, str],
    component: str,
    repo_root: str,
    pathspec_prefix: str,
    result: ComponentDrift,
) -> None:
    for rel_path in sorted(set(dep_checksums) | set(src_checksums)):
        result.compared += 1
        src_cs, dep_cs = src_checksums.get(rel_path), dep_checksums.get(rel_path)
        if src_cs == dep_cs:
            continue
        if dep_cs is None:
            continue  # source-only: role has not deployed it yet -- not this issue's scope
        if src_cs is not None:
            result.drifted.append(FileVerdict(rel_path, VERDICT_MODIFIED))
            continue
        verdict, detail = await _classify_deployed_only(rel_path, component, repo_root, pathspec_prefix)
        if verdict == VERDICT_REMOVED_FROM_SOURCE:
            result.drifted.append(FileVerdict(rel_path, verdict, detail))
        else:
            _bump(result.exclusions, detail)


async def compute_full_tree_drift(component: str, repo_root: str = DEFAULT_REPO_PATH) -> ComponentDrift:
    """Full-tree drift for one component -- every file, one of four verdicts."""
    trees = _resolve_component_trees(component)
    if isinstance(trees, ComponentDrift):
        return trees
    source_dir, deployed_dir = trees

    result = ComponentDrift(component=component)
    both = _collect_both_checksums(source_dir, deployed_dir, owned_subtrees(component), result.exclusions)
    if isinstance(both, str):
        result.error = both
        return result

    dep_checksums, src_checksums = both
    pathspec_prefix = component_pathspec(repo_root, source_dir)
    await _classify_all_paths(dep_checksums, src_checksums, component, repo_root, pathspec_prefix, result)
    return result


async def compute_all_components_drift(
    components: frozenset[str] | None = None,
) -> tuple[list[ComponentDrift], str]:
    """Full-tree drift for every component in one run (#16310)."""
    results = [await compute_full_tree_drift(component) for component in sorted(components or VISIBILITY_COMPONENTS)]
    return results, utc_timestamp()
