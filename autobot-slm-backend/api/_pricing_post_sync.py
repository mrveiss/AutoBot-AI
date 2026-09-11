# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Post-sync pricing refresh for `autobot-backend` (#16231).

Split out of ``api/code_sync.py``, which sits at its #14236 ceiling: a new
post-sync step is added lines, and a grandfathered file may not grow.
``api/_resume_plan.py`` (#15881) is the precedent this module follows,
including moving ``_load_env_file`` here so code_sync.py imports it back
under the same name rather than keeping two copies.

Runs ``python -m services.pricing_refresh`` (autobot-backend/services/
pricing_refresh.py, #16229/#16231) inside the deployed backend's own venv,
immediately after every install and update, so prices are current from the
moment the sync finishes rather than waiting for the next beat tick. Never
fails the sync: an unreachable catalogue, a timeout, or a non-zero exit is
recorded as a human-readable step and the update proceeds regardless --
prices stay *unknown* until the next successful refresh (#16228 decision).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from autobot_shared.env_utils import env_float

# Plain stdlib logging, deliberately -- see autobot_shared/user_management/
# password_epoch.py:50-58: this module is imported by code_sync.py, whose
# test harness (tests/api/test_collect_outdated_node_ids.py) stubs config as
# a MagicMock, and autobot_shared.logging_manager.get_logger compares that
# MagicMock against an int at call time, raising under that harness.
logger = logging.getLogger(__name__)

#: Seconds the post-sync pricing refresh may run before it is abandoned. The
#: install/update itself is never blocked past this: on timeout the step is
#: recorded as failed and the sync proceeds regardless (#16231).
_PRICING_POST_SYNC_TIMEOUT_S: float = env_float("AUTOBOT_PRICING_POST_SYNC_TIMEOUT_S", 120.0)


def _load_env_file(env_path: Path) -> Dict[str, str]:
    """Parse a deployed KEY=VALUE .env into a dict (for subprocess env).

    Moved from ``api/code_sync.py`` (#16231, to keep that file at its
    grandfathered ceiling); code_sync.py imports it back under this name.

    *env_path* must resolve inside the deployed root (CodeQL py/path-injection,
    #16229 review) -- raises ValueError otherwise, rather than silently
    returning {} for a path that escaped it. The caller
    (``run_pricing_refresh_post_sync``) already runs inside a never-fail
    ``try``, so this becomes a recorded "failed to start" step, not a crash.

    The containment check below is inlined rather than delegated to a
    shared helper: CodeQL's py/path-injection dataflow analysis only
    recognises a guard as a sanitiser for a value used in the same scope
    the guard runs in, not one raised by a helper in another function
    (#16229 review, alerts #1132/#1133). ``deployed_root()`` still supplies
    the root so this stays on the one configured source of truth.
    """
    from services.deployed_dir_resolver import deployed_root

    root = os.path.realpath(deployed_root())
    real = os.path.realpath(str(env_path))
    if real != root and not real.startswith(root + os.sep):
        raise ValueError(f"env file path resolves outside the deployed root {root!r}")
    real_path = Path(real)

    env: Dict[str, str] = {}
    if not real_path.exists():
        return env
    for raw in real_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _pricing_subprocess_env(deployed_dir: str) -> Dict[str, str]:
    """Environment for the refresh subprocess (#16231): built exactly the way
    ``_run_alembic_migrations`` builds its own -- os.environ, the deployed
    .env, and PYTHONPATH pointed at the deployed tree.
    """
    env = dict(os.environ)
    env.update(_load_env_file(Path(deployed_dir) / ".env"))
    env["PYTHONPATH"] = deployed_dir
    return env


async def _spawn_pricing_refresh(python_bin: Path, deployed_dir: str, env: Dict[str, str]) -> Tuple[int, str, str]:
    """Run the one-shot pricing refresh CLI; return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        str(python_bin),
        "-m",
        "services.pricing_refresh",
        cwd=deployed_dir,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_PRICING_POST_SYNC_TIMEOUT_S)
    return (
        proc.returncode,
        stdout.decode(errors="replace") if stdout else "",
        stderr.decode(errors="replace") if stderr else "",
    )


def _parse_summary(stdout_text: str) -> Optional[dict]:
    """The refresh CLI's one-line JSON summary, or None if it wrote nothing parseable."""
    lines = stdout_text.strip().splitlines()
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except ValueError:
        return None


def _record_pricing_result(rc: int, stdout_text: str, stderr_text: str, steps: List[str]) -> None:
    """Append one human-readable step line describing the refresh outcome (#16231)."""
    if rc != 0:
        steps.append(
            f"pricing refresh: FAILED (rc={rc}) — prices stay unknown until the next refresh: {stderr_text[-200:]}"
        )
        logger.warning("pricing post-sync: rc=%d: %s", rc, stderr_text[-300:])
        return
    summary = _parse_summary(stdout_text)
    if summary is None:
        steps.append("pricing refresh: ran but produced no summary — prices stay unknown until the next refresh")
        return
    steps.append(f"pricing refresh: ok — wrote {summary.get('written', 0)} prices, indexed {summary.get('indexed', 0)}")


async def run_pricing_refresh_post_sync(component: str, deployed_dir: str, pip_bin: str, steps: List[str]) -> None:
    """Refresh LLM pricing right after autobot-backend's own venv is ready (#16231).

    Runs only for ``autobot-backend`` -- the refresh CLI lives in that
    component's venv, and no other component's sync should trigger it. Never
    raises: a broken refresh must never fail the sync (#16228 decision).
    """
    if component != "autobot-backend":
        return
    python_bin = Path(pip_bin).with_name("python")
    try:
        rc, stdout_text, stderr_text = await _spawn_pricing_refresh(
            python_bin, deployed_dir, _pricing_subprocess_env(deployed_dir)
        )
    except asyncio.TimeoutError:
        steps.append(
            f"pricing refresh: timed out after {_PRICING_POST_SYNC_TIMEOUT_S:.0f}s — "
            "prices stay unknown until the next refresh"
        )
        logger.warning("pricing post-sync: timed out after %ss", _PRICING_POST_SYNC_TIMEOUT_S)
        return
    except Exception as exc:  # noqa: BLE001 - a broken refresh must never fail the sync (#16231)
        steps.append(f"pricing refresh: failed to start: {exc} — prices stay unknown until the next refresh")
        logger.warning("pricing post-sync: failed to start: %s", exc)
        return
    _record_pricing_result(rc, stdout_text, stderr_text, steps)
