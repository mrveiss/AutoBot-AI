# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What "sync without restarting" passes to update-all-nodes.yml (#20743).

Ansible has no negation in ``--tags``: ``--tags !restart`` is a tag named "!restart", so such a
run executes only the ``always`` tasks and deploys nothing. Skipping is ``--skip-tags``. That
covers the restart tasks, which are tagged ``restart``. It does not cover handlers, because
Ansible ignores tags on handlers: a config change would still notify ``restart ai-stack``. So
every restart handler the updater can notify also checks ``autobot_restart_services``, which
this sets false. Unset, the variable defaults to true, so installs and normal syncs restart as
before.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from autobot_shared.backend_start_marker import BACKEND_UNIT, parse_unix_timestamp, write_marker
from autobot_shared.env_utils import env_int_clamped
from services.secrets_store_snapshot import BACKEND_DATA_DIR

logger = logging.getLogger(__name__)

#: How long the updater waits for ``systemctl show`` before it gives up recording the start.
SYSTEMCTL_TIMEOUT_S = env_int_clamped("SLM_BACKEND_START_PROBE_TIMEOUT_S", 10, min_v=1, max_v=120)

RESTART_TAG = "restart"
RESTART_VAR = "autobot_restart_services"


def no_restart_args(restart: bool) -> Dict[str, Any]:
    """``execute_playbook`` keyword arguments for a sync with or without restarts."""
    if restart:
        return {}
    return {"skip_tags": [RESTART_TAG], "extra_vars": {RESTART_VAR: "false"}}


def reject_negated_tags(tags: Optional[Iterable[str]]) -> None:
    """Raise ValueError for a ``!tag`` in ``--tags``: Ansible would read it as a tag name, not a skip."""
    negated = [t for t in tags or () if t.startswith("!")]
    if negated:
        raise ValueError(f"--tags cannot negate {negated}; pass them as skip_tags")


async def record_backend_start(services: Iterable[str]) -> None:
    """Just before the user backend restarts, record when the running one started (#17421).

    The new backend's plugin enable gate reads this on the upgrade boot as the previous start. It writes
    into the backend's data directory (``SLM_BACKEND_DATA_DIR``, as the secrets-store backup does), where
    the backend reads its own ``AUTOBOT_DATA_DIR``. Never raises and never waits past
    ``SYSTEMCTL_TIMEOUT_S``: a missing marker only makes the gate fall back to the backend log.
    """
    if BACKEND_UNIT not in services:
        return
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "show",
            "-p",
            "ActiveEnterTimestamp",
            "--value",
            "--timestamp=unix",
            BACKEND_UNIT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=SYSTEMCTL_TIMEOUT_S)
        started = parse_unix_timestamp(out.decode("utf-8", "replace"))
        if started is not None:
            await asyncio.to_thread(write_marker, started, Path(BACKEND_DATA_DIR))
    except Exception as exc:  # noqa: BLE001 -- nothing here may block or abort the restart
        logger.warning("could not record the previous %s start: %s", BACKEND_UNIT, exc)
    finally:
        if proc is not None and proc.returncode is None:
            proc.kill()
            await proc.wait()
