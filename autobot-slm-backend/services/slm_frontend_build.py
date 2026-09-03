# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Build and atomically publish the SLM frontend for the self-sync-from-code-source
path (#15462).

Extracted out of ``api/code_sync.py`` (#15462 review — build-and-publish logic
does not belong in an API router module, and the module was against its
grandfathered line-count ceiling, #14236).

Mirrors the staged publish ``update-all-nodes.yml`` uses for the Ansible path
(#15430): build into ``dist.staging``, verify it produced a real entry point,
and only THEN swap it into ``dist/`` — so a failed or incomplete build never
touches what nginx is currently serving. Every failure is logged loudly
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
from pathlib import Path

from services.drift_checker import get_default_deployed_dir

logger = logging.getLogger(__name__)

# The build output nginx serves this node's SLM UI from. Resolved through the
# same env-backed helper the rest of the SLM uses (SLM_DEPLOYED_ROOT), never
# hardcoded to an absolute path -- a literal here silently disagrees with any
# install whose deployed root differs.
_SLM_FRONTEND_DIR = get_default_deployed_dir("autobot-slm-frontend")

# Subprocess ceilings. Env-backed rather than magic numbers at the call site:
# npm ci and a Vite build are the slow steps, and an install with a cold cache
# or a slower node legitimately needs longer than this default.
_CHOWN_TIMEOUT_SECONDS = float(os.getenv("SLM_FRONTEND_CHOWN_TIMEOUT_SECONDS", "30"))
_NPM_TIMEOUT_SECONDS = float(os.getenv("SLM_FRONTEND_NPM_TIMEOUT_SECONDS", "300"))


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


async def _npm_build_slm_staged(frontend_dir: str) -> bool:
    """Build into dist.staging, never straight into the served dist/ (#15462).

    Mirrors the staged publish update-all-nodes.yml uses (#15430): a build
    that fails or is interrupted leaves dist.staging incomplete and dist/
    completely untouched, so the previously-working bundle keeps serving.
    Uses build:slm (VITE_API_URL=/slm) — the SLM UI is served under /slm, and
    the plain `build` script this path used to run bakes in the wrong API
    base (see the same warning in update-all-nodes.yml).
    """
    proc = await asyncio.create_subprocess_exec(
        "npm",
        "run",
        "build:slm",
        "--",
        "--outDir",
        "dist.staging",
        "--emptyOutDir",
        cwd=frontend_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_NPM_TIMEOUT_SECONDS)
    if proc.returncode != 0:
        logger.error(
            "SLM self-sync: frontend build failed (%d) — previous dist/ untouched: %s",
            proc.returncode,
            stdout.decode(errors="replace")[:2000],
        )
        return False
    return True


async def _publish_staged_slm_build(frontend_dir: str) -> bool:
    """Promote dist.staging to dist only if it produced a real entry point.

    Refuses to publish a build that reports success but produced no
    index.html — the exact live incident (#15462) — and keeps the bundle it
    replaces as dist.previous so this swap is the only place dist/ changes.
    """
    root = Path(frontend_dir)
    staged_index = root / "dist.staging" / "index.html"
    if not staged_index.is_file() or staged_index.stat().st_size == 0:
        logger.error("SLM self-sync: staged build has no index.html — refusing to publish (#15462)")
        return False

    def _swap() -> None:
        previous = root / "dist.previous"
        if previous.exists():
            shutil.rmtree(previous)
        current = root / "dist"
        if current.exists():
            current.rename(previous)
        (root / "dist.staging").rename(current)

    await asyncio.to_thread(_swap)
    return True


async def build_slm_frontend() -> bool:
    """Build and atomically publish the SLM frontend (#15462).

    Issue #1607: the Ansible path builds the frontend; the self-sync path
    was missing this step, serving stale dist/ files. Returns False on any
    failure — loudly logged, never swallowed — so the caller can fail the
    whole sync instead of marking the node up to date and restarting into a
    bundle that was never actually published.
    """
    frontend_dir = _SLM_FRONTEND_DIR
    try:
        await _chown_slm_frontend(frontend_dir)
        if not await _npm_ci_slm_frontend(frontend_dir):
            return False
        if not await _npm_build_slm_staged(frontend_dir):
            return False
        if not await _publish_staged_slm_build(frontend_dir):
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
    marker = Path(get_default_deployed_dir("autobot-slm-backend")) / ".deployed_commit"
    try:
        await asyncio.to_thread(marker.write_text, commit, encoding="utf-8")
    except OSError as exc:
        logger.warning("SLM self-sync: could not write .deployed_commit marker: %s", exc)
