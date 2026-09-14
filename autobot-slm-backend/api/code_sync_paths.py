# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Containment-checked source-tree helpers for code_sync.py (#16713).

Split out of ``api/code_sync.py``, which sits at its #14236 ceiling: a new
containment guard is added lines, and a grandfathered file may not grow — the
same reason ``api/_pricing_post_sync.py`` (#16231) and ``api/_resume_plan.py``
(#15881) moved out before it. ``code_sync.py`` imports both functions back
under their original names, so every existing caller and every
``patch("api.code_sync._deploy_constraints_dir", ...)``-style test double
keeps resolving the same object (#12572).

Both guards below are inlined in the same function as the filesystem sink
they protect, rather than delegated to a shared helper — even one in this
same module. CodeQL's py/path-injection dataflow analysis only recognises a
containment check as a sanitiser for a value used in the *scope the check
itself runs in*, not one raised by a call to another function; established at
#16229 review (``_pricing_post_sync.py``'s ``_load_env_file``, alerts
#1132/#1133) and reconfirmed by #16236 (a compound ``==`` guard alongside the
``startswith`` left #1134/#1135 red on the same value) — so each check here is
a single ``not resolved.startswith(root + os.sep)`` condition, never combined
with an equality branch.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from autobot_shared.env_utils import env_float

# Plain stdlib logging, deliberately -- see autobot_shared/user_management/
# password_epoch.py:50-58 and api/_pricing_post_sync.py: this module is
# imported by code_sync.py, whose test harness stubs config as a MagicMock,
# and autobot_shared.logging_manager.get_logger compares that MagicMock
# against an int at call time, raising under that harness.
logger = logging.getLogger(__name__)

_CONSTRAINTS_SOURCE_SUBDIR: str = "constraints"

#: Top-level repo-root files copied to the deploy base before pip installs,
#: so a component's ``-r ../requirements.txt`` reference resolves (#11336).
_REPO_ROOT_REQUIREMENT_FILES: tuple[str, ...] = ("requirements.txt",)

#: Seconds the top-level constraints/ rsync may run before it is abandoned.
_CONSTRAINTS_RSYNC_TIMEOUT_S: float = env_float("AUTOBOT_CONSTRAINTS_RSYNC_TIMEOUT_S", 30.0)

#: Seconds each top-level repo-root file's cp may run before it is abandoned.
_ROOT_REQS_CP_TIMEOUT_S: float = env_float("AUTOBOT_ROOT_REQS_CP_TIMEOUT_S", 10.0)

#: Seconds `alembic upgrade heads` may run before it is abandoned (#11255).
_ALEMBIC_UPGRADE_TIMEOUT_S: float = env_float("AUTOBOT_ALEMBIC_UPGRADE_TIMEOUT_S", 300.0)


async def _deploy_constraints_dir(source_root: str, steps: List[str]) -> None:
    """Rsync top-level constraints/ to /opt/autobot/constraints/ before pip (#11322).

    autobot-backend/requirements.txt uses `-c ../constraints/shared.txt` so the
    relative reference resolves to /opt/autobot/constraints/shared.txt at deploy
    time. Code-sync only rsyncs component subdirs, so this helper deploys the
    constraints dir explicitly — preventing the silent pip failure that occurred
    when the file was absent.

    *source_root* must resolve inside the code_source root (CodeQL
    py/path-injection, #16713) — refuses and returns otherwise, rather than
    rsyncing from wherever it actually points. Neither caller (the sync
    endpoint nor the async job runner) wraps this call, so raising here would
    surface as an unhandled 500 or a path in an operator-visible job record
    (#16713 review) instead of the same graceful refusal the other three
    containment checks in this split give (log server-side, note the refusal
    in *steps*, return). ``_get_code_source_root()`` stays on
    ``api.code_sync``'s single source of truth for that root, but the import
    is lazy: a module-level import back into ``code_sync`` would be circular
    (``code_sync`` imports this module at its own top level).
    """
    from api.code_sync import _get_code_source_root, _get_deploy_base

    root = os.path.realpath(str(_get_code_source_root()))
    src = os.path.realpath(f"{source_root}/{_CONSTRAINTS_SOURCE_SUBDIR}/")
    if not src.startswith(root + os.sep):
        logger.error("code-sync: constraints source root resolves outside the code_source root: %s", src)
        steps.append("constraints: refusing a source root outside the code_source root")
        return
    dst = str(_get_deploy_base() / _CONSTRAINTS_SOURCE_SUBDIR) + "/"
    if not Path(src).exists():
        steps.append(f"constraints: source {src} not found — skipped")
        return
    steps.append(f"constraints: deploying {src} -> {dst}")
    try:
        proc = await asyncio.create_subprocess_exec(
            "rsync",
            "-avz",
            "--delete",
            src,
            dst,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        _, _ = await asyncio.wait_for(proc.communicate(), timeout=_CONSTRAINTS_RSYNC_TIMEOUT_S)
        if proc.returncode == 0:
            steps.append("constraints: deployed ok")
        else:
            steps.append(f"constraints: rsync failed (rc={proc.returncode})")
    except Exception as exc:
        steps.append(f"constraints: deploy error: {exc}")


async def _deploy_repo_root_requirements(source_root: str, steps: List[str]) -> None:
    """Copy top-level repo-root files to /opt/autobot/ before pip (#11336).

    autobot-backend/requirements.txt uses `-r ../requirements.txt` so the
    relative reference resolves to /opt/autobot/requirements.txt at deploy time.
    Code-sync only rsyncs component subdirs, so each file listed in
    _REPO_ROOT_REQUIREMENT_FILES is copied explicitly from source_root.
    Skips gracefully when the source file is absent (non-fatal).

    Each copied *src* must resolve inside the code_source root (CodeQL
    py/path-injection, #16713) — refuses and skips that file otherwise, for
    the same unwrapped-caller reason ``_deploy_constraints_dir`` does not
    raise (#16713 review). Both lookups are lazy for the same circular-import
    reason as ``_deploy_constraints_dir``.
    """
    from api.code_sync import _get_code_source_root, _get_deploy_base

    source_root_resolved = os.path.realpath(str(_get_code_source_root()))
    base = _get_deploy_base()
    for filename in _REPO_ROOT_REQUIREMENT_FILES:
        src = os.path.realpath(str(Path(source_root) / filename))
        if not src.startswith(source_root_resolved + os.sep):
            logger.error("code-sync: root-reqs %r resolves outside the code_source root: %s", filename, src)
            steps.append(f"root-reqs: refusing {filename!r} outside the code_source root")
            continue
        src_path = Path(src)
        dst = base / filename
        if not src_path.exists():
            steps.append(f"root-reqs: {src_path} not found — skipped")
            continue
        steps.append(f"root-reqs: copying {src_path} -> {dst}")
        try:
            proc = await asyncio.create_subprocess_exec(
                "cp",
                "--",
                str(src_path),
                str(dst),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            _, _ = await asyncio.wait_for(proc.communicate(), timeout=_ROOT_REQS_CP_TIMEOUT_S)
            if proc.returncode == 0:
                steps.append(f"root-reqs: {filename} deployed ok")
            else:
                steps.append(f"root-reqs: cp {filename} failed (rc={proc.returncode})")
        except Exception as exc:
            steps.append(f"root-reqs: {filename} deploy error: {exc}")


async def _run_alembic_upgrade_subprocess(
    alembic_bin: str,
    cfg_path: str,
    deployed_dir: str,
    env: Dict[str, str],
    component: str,
    display_dump: Optional[str],
    steps: List[str],
) -> bool:
    """Spawn ``alembic -c cfg_path upgrade heads`` and record the result (#11255).

    Split out of ``api.code_sync._run_alembic_migrations`` to keep that
    function under the function-length guard (#620) — *alembic_bin* and
    *cfg_path* are already containment-checked by the caller before this
    runs, and this helper touches no filesystem sink itself.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            alembic_bin,
            "-c",
            cfg_path,
            "upgrade",
            "heads",
            cwd=deployed_dir,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_ALEMBIC_UPGRADE_TIMEOUT_S)
        out = stdout.decode(errors="replace") if stdout else ""
        if proc.returncode == 0:
            logger.info("drift resolve: alembic upgrade ok for %s", component)
            steps.append("alembic: upgrade succeeded")
            return True
        logger.error(
            "drift resolve: alembic upgrade FAILED (%d) for %s: %s",
            proc.returncode,
            component,
            out[-400:],
        )
        _backup_ref = f" — DB backup at {display_dump}" if display_dump else ""
        steps.append(f"alembic: upgrade FAILED (rc={proc.returncode}): {out[-200:]}{_backup_ref}")
        return False
    except asyncio.TimeoutError:
        logger.error("drift resolve: alembic upgrade timed out for %s", component)
        _backup_ref = f" — DB backup at {display_dump}" if display_dump else ""
        steps.append(f"alembic: upgrade timed out after {_ALEMBIC_UPGRADE_TIMEOUT_S:.0f}s{_backup_ref}")
        return False
    except Exception as exc:
        logger.error("drift resolve: alembic upgrade error for %s: %s", component, exc)
        _backup_ref = f" — DB backup at {display_dump}" if display_dump else ""
        steps.append(f"alembic: upgrade error: {exc}{_backup_ref}")
        return False
