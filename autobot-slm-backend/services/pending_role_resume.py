# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pending-role provisioning that survives the SLM's own restart (#22211).

A self-update that restarts the SLM runs ``update-all-nodes.yml`` detached and cuts its waiter with the
restart, so the provisioning step ``run_update_all_nodes`` does afterwards would run in the process that is
being replaced and never happen. The same design the update-all resume uses applies: the intent is persisted
(a Settings row, like the resume plan) before the run, and the restarted process picks it up on startup.

* ``mark_provision_after_restart`` records the node and the time, before the detached run.
* ``clear_provision_marker`` drops it when the run was not cut by the restart (it ended in this process,
  where provisioning already ran or the update failed).
* ``provision_marked_nodes`` (startup) takes the markers -- read and deleted before anything runs, so each is
  provisioned ONCE -- waits for the detached unit to finish, and provisions only when it completed.

Provisioning failures are warnings in the log; nothing here raises.
"""

import asyncio
import json
import time
from typing import Dict

from sqlalchemy import select

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp
from models.database import Setting
from services.database import db_service

logger = get_logger(__name__)

#: Settings key the markers are stored under: {node_id: marked_at}.
MARKER_KEY = "slm_pending_role_provision_nodes"
#: Strong references to the fire-and-forget startup tasks (a bare task can be garbage collected).
_TASKS: set = set()


async def _row(db):
    return (await db.execute(select(Setting).where(Setting.key == MARKER_KEY))).scalar_one_or_none()


def _decode(row) -> Dict[str, str]:
    try:
        data = json.loads(row.value) if row is not None and row.value else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


async def mark_provision_after_restart(node_id: str) -> None:
    """Persist that `node_id`'s pending roles are to be provisioned by the restarted process."""
    try:
        async with db_service.session() as db:
            row = await _row(db)
            data = _decode(row)
            data[node_id] = utc_timestamp()
            if row is None:
                db.add(Setting(key=MARKER_KEY, value=json.dumps(data), value_type="json"))
            else:
                row.value = json.dumps(data)
            await db.commit()
    except Exception as exc:  # noqa: BLE001 - the update itself must go on
        logger.warning("could not persist the pending-role marker for %s: %s", node_id, exc)


async def clear_provision_marker(node_id: str) -> None:
    """Drop `node_id`'s marker: the run ended in this process, so nothing is left for a restart to do."""
    try:
        async with db_service.session() as db:
            row = await _row(db)
            data = _decode(row)
            if row is None or node_id not in data:
                return
            data.pop(node_id)
            if data:
                row.value = json.dumps(data)
            else:
                await db.delete(row)
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not clear the pending-role marker for %s: %s", node_id, exc)


async def take_markers() -> Dict[str, str]:
    """Read AND delete every marker in one transaction, so a marker is acted on once."""
    async with db_service.session() as db:
        row = await _row(db)
        data = _decode(row)
        if row is not None:
            await db.delete(row)
            await db.commit()
        return data


async def _update_completed_since(since: str) -> bool:
    """Wait for the detached self-update unit to end; True when it completed after `since`."""
    from api._resume_wait import resolve_completion_time
    from api.code_sync import _SELF_UPDATE_WATCH_POLL_SECONDS, _SELF_UPDATE_WATCH_TIMEOUT_SECONDS
    from services.deploy_activity import read_deploy_activity

    deadline = time.monotonic() + _SELF_UPDATE_WATCH_TIMEOUT_SECONDS
    while True:
        activity = await read_deploy_activity()
        if activity.in_progress is False:
            return resolve_completion_time(activity, since) is not None
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(_SELF_UPDATE_WATCH_POLL_SECONDS)


async def provision_marked_nodes() -> None:
    """Startup step: provision the nodes a restarted self-update left marked, once, when the update completed."""
    from services.pending_role_provisioning import provision_pending_roles

    try:
        marked = await take_markers()
        for node_id, since in marked.items():
            if not await _update_completed_since(since):
                logger.warning("pending roles of %s not provisioned: the self-update did not complete", node_id)
                continue
            logger.info(
                "pending roles of %s after restart: %s", node_id, await provision_pending_roles(node_id) or "none"
            )
    except Exception as exc:  # noqa: BLE001 - a warning; the startup path must never fail on this
        logger.warning("could not provision the nodes marked before the restart: %s", exc)


def schedule_marked_provisioning() -> None:
    """Run ``provision_marked_nodes`` in the background: provisioning takes minutes and must not hold startup."""
    task = asyncio.get_running_loop().create_task(provision_marked_nodes())
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
