# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Is a self-update play running right now? (#13913)

The drift endpoint compares checksums between the source tree and the deployed
tree. While ansible is mid-write those two trees genuinely differ, so drift is
reported for files that are simply being copied. Measured across one update:
28 of 30 reported drifts evaporated once the play settled, same host, same
endpoint, ten minutes apart. Nothing in the response said a deploy was running.

That window is exactly when an operator looks — checking whether an update
worked is the reason to open the drift view — and the remediation is a
delete-style rsync (#13851), so acting on a mid-deploy reading is destructive
against files that are mid-write.

Why not derive this from the self-update log
--------------------------------------------
``read_self_update_verdict`` reports ``complete=False`` both for a run that is
still going and for one that died. Those are opposite situations for a caller
deciding whether to trust a drift reading, so the log alone cannot answer the
question. ``GET /api/code-sync/status`` has the same limitation: its
``self_update_incomplete`` verdict describes the *previous* run, not the one
currently executing, which is why it reported ``false`` throughout the window.

The signal used here is the transient systemd service the detached run lives in
(#11492/#12596). It is forked by PID 1 rather than by this backend, so — unlike
any in-process flag — it survives the ``systemctl restart autobot-slm-backend``
that Play 1 performs halfway through the very run being tracked.

Unknown is a third state, not a false
-------------------------------------
When the query cannot run, this reports ``in_progress=None`` rather than
``False``. A check that could not run must not be read as "no deploy is in
flight" — that is the same shape of silent pass this issue is about.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from autobot_shared.logging_manager import get_logger
from services.playbook_executor import SELF_UPDATE_DETACH_UNIT_PREFIX, SELF_UPDATE_LOG_PATH
from services.self_update_log_reader import read_self_update_verdict

logger = get_logger(__name__)

#: Wall-clock ceiling for the systemctl query. The drift endpoint must answer
#: even on a host where systemd is slow or absent, so this is short and a
#: timeout degrades to "unknown" rather than hanging the request.
DEPLOY_ACTIVITY_QUERY_TIMEOUT_S: float = float(os.getenv("SLM_DEPLOY_ACTIVITY_TIMEOUT_S", "3.0"))

#: Unit pattern for the detached self-update run. Derived from the executor's
#: own prefix rather than restated, so renaming the unit cannot leave this
#: matching a name nothing is created under (which would read as "never
#: deploying" forever).
SELF_UPDATE_UNIT_PATTERN: str = f"{SELF_UPDATE_DETACH_UNIT_PREFIX}-*.service"


@dataclass(frozen=True)
class DeployActivity:
    """Whether a self-update play is executing, and when one last finished."""

    #: True while a detached self-update unit is active. ``None`` when the
    #: question could not be answered — never collapsed into False.
    in_progress: bool | None
    #: Why the value is what it is, in terms an operator can act on.
    reason: str
    #: ISO-8601 UTC time the last *completed* play was last written, or None
    #: when no completed run is on record. Populated only when the log shows a
    #: PLAY RECAP, so it never dates a run that was cut short.
    last_completed_play_at: str | None

    @property
    def readings_are_unstable(self) -> bool:
        """True only when a deploy is known to be running.

        Deliberately not true for the unknown case: an unknown signal is a
        reason to say so in the response, not a reason to assert instability
        that has not been observed.
        """
        return self.in_progress is True


async def _self_update_unit_active() -> bool | None:
    """True/False if systemd could be asked, None if it could not.

    ``list-units`` with an explicit pattern lists nothing (exit 0, empty
    stdout) when no matching unit exists, so an empty result is a real answer.
    A non-zero exit, a missing binary, or a timeout is not.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "list-units",
            "--type=service",
            "--state=running",
            "--no-legend",
            "--plain",
            SELF_UPDATE_UNIT_PATTERN,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        logger.warning("deploy activity: systemctl unavailable (%s)", exc)
        return None

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=DEPLOY_ACTIVITY_QUERY_TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning("deploy activity: systemctl query timed out after %ss", DEPLOY_ACTIVITY_QUERY_TIMEOUT_S)
        proc.kill()
        await proc.wait()
        return None

    if proc.returncode != 0:
        logger.warning("deploy activity: systemctl exited %s", proc.returncode)
        return None

    return bool(stdout.decode("utf-8", errors="replace").strip())


def _last_completed_play_at(log_path: Path) -> str | None:
    """Modification time of the self-update log, only if a run completed there.

    A completed run's final write is its PLAY RECAP, so the log's mtime dates
    the completion closely enough for a freshness judgement. An incomplete log
    yields None rather than a timestamp that would read as a completion.
    """
    verdict = read_self_update_verdict(log_path)
    if not verdict.complete:
        return None
    try:
        from datetime import datetime, timezone

        return datetime.fromtimestamp(log_path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        # #13125: the verdict may have come from the rotated log, in which case
        # the live path can be unreadable. Report the completion without a time
        # rather than failing the caller.
        return None


async def read_deploy_activity(log_path: Path | None = None) -> DeployActivity:
    """Report whether a self-update is in flight. Never raises.

    A drift or status endpoint must still answer when this signal cannot be
    read, so every failure path degrades to ``in_progress=None`` with a reason.
    """
    path = log_path if log_path is not None else SELF_UPDATE_LOG_PATH
    active = await _self_update_unit_active()

    try:
        completed_at = _last_completed_play_at(path)
    except Exception as exc:  # pragma: no cover - defensive; reader never raises
        logger.warning("deploy activity: could not date the last completed play (%s)", exc)
        completed_at = None

    if active is None:
        reason = "deploy state unknown — the self-update unit could not be queried; treat this reading as unverified"
    elif active:
        reason = "a self-update play is running — source and deployed trees differ because files are mid-write"
    else:
        reason = "no self-update play is running"

    return DeployActivity(in_progress=active, reason=reason, last_completed_play_at=completed_at)
