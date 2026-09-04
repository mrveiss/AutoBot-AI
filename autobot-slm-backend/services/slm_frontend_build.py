# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Build and atomically publish the SLM frontend for the self-sync-from-code-source
path (#15462).

Extracted out of ``api/code_sync.py`` (#15462 review — build-and-publish logic
does not belong in an API router module, and the module was against its
grandfathered line-count ceiling, #14236).

Mirrors the publish ``roles/_shared/tasks/build_publish_slm_frontend.yml``
performs for the Ansible path (#15430, #15557, #15610): build into a directory
of this build's own, verify it produced a real entry point, and only THEN point
the served ``current`` symlink at it — so a failed or incomplete build never
touches what nginx is currently serving, and a successful one is published by a
single ``rename(2)`` with no instant at which the served path resolves to
nothing. The layout is the contract between the two halves; see that task file
for the full rationale. Every failure is logged loudly
(``logger.error``, never swallowed) and returns ``False`` so the caller
(``api/code_sync.py::_sync_slm_from_code_source``) can fail the whole sync
instead of marking the node up to date and restarting into a bundle that was
never actually published.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from autobot_shared.env_utils import env_int_clamped
from services.deployed_dir_resolver import get_release_component_dir

logger = logging.getLogger(__name__)

# The build output nginx serves this node's SLM UI from. Resolved through the
# same env-backed helper the rest of the SLM uses (SLM_DEPLOYED_ROOT), never
# hardcoded to an absolute path -- a literal here silently disagrees with any
# install whose deployed root differs. A WRITE: this is a build/publish
# destination, so it goes through get_release_component_dir, never the reader form.
_SLM_FRONTEND_DIR = get_release_component_dir("autobot-slm-frontend")

# Subprocess ceilings. Env-backed rather than magic numbers at the call site:
# npm ci and a Vite build are the slow steps, and an install with a cold cache
# or a slower node legitimately needs longer than this default.
_CHOWN_TIMEOUT_SECONDS = float(os.getenv("SLM_FRONTEND_CHOWN_TIMEOUT_SECONDS", "30"))
_NPM_TIMEOUT_SECONDS = float(os.getenv("SLM_FRONTEND_NPM_TIMEOUT_SECONDS", "300"))

# The #15610 layout, spelled the same way on both halves of the publish:
# `dist-<build-id>/` per build, `current` the served symlink, `previous` the
# rollback target. `dist` is the pre-#15610 served directory — never written
# here, only adopted as the first `current` on a node that has not published
# under this layout yet.
_BUILD_PREFIX = "dist-"
_CURRENT_LINK = "current"
_PREVIOUS_LINK = "previous"
_LEGACY_DIR = "dist"

# How many build directories survive a publish. Bounded, or the disk grows by
# one bundle per self-sync forever. Env-backed for the same reason the timeouts
# above are: the Ansible half reads `slm_frontend_release_keep` from inventory
# and cannot be read from here, so the two carry the number separately and move
# together.
# Read through `env_int_clamped`, not a bare `int(os.getenv(...))`: this is a
# module-level constant, so a malformed value raises ValueError at IMPORT and
# takes the backend down over a typo in an env file. The clamped reader falls
# back to the default with a warning instead. A floor of 1 also refuses 0,
# which would prune the bundle that was just published (#15610).
_RELEASE_KEEP = env_int_clamped("SLM_FRONTEND_RELEASE_KEEP", 3, 1, 50)


def _build_id() -> str:
    """A UTC id that sorts by build time.

    Same shape as the Ansible half's ``date -u +%Y%m%dT%H%M%S%3NZ``, so the two
    publishers' directories interleave in one order and pruning by name is
    pruning by age on a node both have written to.
    """
    now = datetime.now(timezone.utc)
    return f"{now:%Y%m%dT%H%M%S}{now.microsecond // 1000:03d}Z"


def _flip(root: Path, link_name: str, target: str) -> None:
    """Point *link_name* at *target* with a single ``rename(2)``.

    ``os.replace`` over a symlink is the whole fix for #15610: the name goes
    straight from its old target to its new one, so no request can observe it
    resolving to nothing. Unlinking and re-creating the symlink — what
    ``ln -sfn`` and ``Path.symlink_to`` after an ``unlink`` both do — is the
    window this replaced.
    """
    staged = root / f".{link_name}.next"
    if staged.is_symlink() or staged.exists():
        staged.unlink()
    staged.symlink_to(target)
    os.replace(staged, root / link_name)


def _seed_current_from_legacy_dist(root: Path) -> None:
    """Adopt a pre-#15610 ``dist/`` as the first ``current``.

    Runs before the build, not after it: on a node migrating to this layout the
    served path has to resolve from the moment the new nginx config can be
    read, including when the build that follows fails. That is the #15557
    invariant — a failed build leaves the previous bundle serving.
    """
    current = root / _CURRENT_LINK
    if current.is_symlink() or current.exists():
        return
    if (root / _LEGACY_DIR).is_dir():
        current.symlink_to(_LEGACY_DIR)


def _prune_old_builds(root: Path) -> None:
    """Keep the newest ``_RELEASE_KEEP`` bundles, plus whatever is reachable.

    The targets of ``current`` and ``previous`` are excluded by name rather
    than trusted to fall inside the kept window: a rollback points ``current``
    at an older bundle, and deleting the bundle being served is the outage this
    module exists to prevent.
    """
    reachable = {os.readlink(root / name) for name in (_CURRENT_LINK, _PREVIOUS_LINK) if (root / name).is_symlink()}
    builds = sorted(
        (p.name for p in root.iterdir() if p.name.startswith(_BUILD_PREFIX) and p.is_dir() and not p.is_symlink()),
        reverse=True,
    )
    for name in builds[_RELEASE_KEEP:]:
        if name in reachable:
            continue
        try:
            shutil.rmtree(root / name)
        except OSError as exc:
            logger.warning("SLM self-sync: could not prune old bundle %s: %s", name, exc)


async def _chown_slm_frontend(frontend_dir: str) -> None:
    """Fix ownership before build — Ansible may have deployed as root (#1624)."""
    proc = await asyncio.create_subprocess_exec(
        "sudo",
        "chown",
        "-R",
        "autobot:autobot",
        frontend_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    await asyncio.wait_for(proc.communicate(), timeout=_CHOWN_TIMEOUT_SECONDS)


async def _npm_ci_slm_frontend(frontend_dir: str) -> bool:
    """Install exact lockfile deps. False (loudly logged) on failure — never
    silently swallowed, so a broken self-sync can be attributed (#15462)."""
    proc = await asyncio.create_subprocess_exec(
        "npm",
        "ci",
        cwd=frontend_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_NPM_TIMEOUT_SECONDS)
    if proc.returncode != 0:
        logger.error(
            "SLM self-sync: npm ci failed (%d): %s",
            proc.returncode,
            stdout.decode(errors="replace")[:2000],
        )
        return False
    return True


async def _npm_build_slm(frontend_dir: str, build_id: str) -> bool:
    """Build into this build's own directory, never the served path (#15462).

    Mirrors the publish the shared Ansible task file performs (#15430,
    #15610): a build that fails or is interrupted leaves its own directory
    incomplete and `current` pointing exactly where it did, so the
    previously-working bundle keeps serving. Uses build:slm (VITE_API_URL=/slm)
    — the SLM UI is served under /slm, and the plain `build` script this path
    used to run bakes in the wrong API base.
    """
    proc = await asyncio.create_subprocess_exec(
        "npm",
        "run",
        "build:slm",
        "--",
        "--outDir",
        f"{_BUILD_PREFIX}{build_id}",
        "--emptyOutDir",
        cwd=frontend_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_NPM_TIMEOUT_SECONDS)
    if proc.returncode != 0:
        logger.error(
            "SLM self-sync: frontend build failed (%d) — `current` untouched: %s",
            proc.returncode,
            stdout.decode(errors="replace")[:2000],
        )
        return False
    return True


async def _publish_build(frontend_dir: str, build_id: str) -> bool:
    """Point `current` at the new bundle, only if it has a real entry point.

    Refuses to publish a build that reports success but produced no
    index.html — the exact live incident (#15462) — and leaves the bundle it
    replaces reachable as `previous`, the rollback target `dist.previous` used
    to be. The publish itself is one rename(2) (#15610).
    """
    root = Path(frontend_dir)
    built_index = root / f"{_BUILD_PREFIX}{build_id}" / "index.html"
    if not built_index.is_file() or built_index.stat().st_size == 0:
        logger.error("SLM self-sync: build has no index.html — refusing to publish (#15462)")
        return False

    def _swap() -> None:
        current = root / _CURRENT_LINK
        replaced = os.readlink(current) if current.is_symlink() else ""
        _flip(root, _CURRENT_LINK, f"{_BUILD_PREFIX}{build_id}")
        if replaced:
            _flip(root, _PREVIOUS_LINK, replaced)
        _prune_old_builds(root)

    await asyncio.to_thread(_swap)
    return True


async def build_slm_frontend() -> bool:
    """Build and atomically publish the SLM frontend (#15462).

    Issue #1607: the Ansible path builds the frontend; the self-sync path
    was missing this step, serving stale files. Returns False on any
    failure — loudly logged, never swallowed — so the caller can fail the
    whole sync instead of marking the node up to date and restarting into a
    bundle that was never actually published.
    """
    frontend_dir = _SLM_FRONTEND_DIR
    build_id = _build_id()
    try:
        await _chown_slm_frontend(frontend_dir)
        await asyncio.to_thread(_seed_current_from_legacy_dist, Path(frontend_dir))
        if not await _npm_ci_slm_frontend(frontend_dir):
            return False
        if not await _npm_build_slm(frontend_dir, build_id):
            return False
        if not await _publish_build(frontend_dir, build_id):
            return False
        logger.info("SLM self-sync: frontend build published")
        return True
    except Exception as exc:
        logger.error("SLM self-sync: frontend build failed: %s", exc)
        return False


async def write_slm_deployed_commit_marker(commit: str) -> None:
    """Write .deployed_commit so a self-sync-from-code-source deploy is
    attributable (#15462) — the same marker update-all-nodes.yml writes
    (#12223, #12202). Without it, ``_get_slm_deployed_commit()`` always
    returns None after this path runs and a bad state cannot be identified.
    """
    marker = Path(get_release_component_dir("autobot-slm-backend")) / ".deployed_commit"
    try:
        await asyncio.to_thread(marker.write_text, commit, encoding="utf-8")
    except OSError as exc:
        logger.warning("SLM self-sync: could not write .deployed_commit marker: %s", exc)
