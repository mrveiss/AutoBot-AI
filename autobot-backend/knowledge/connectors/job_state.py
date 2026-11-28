# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A connector's live sync job, as a poller sees it (#8149, #20755).

The run writes its job state only once change detection returns, which is slow for a remote
source, and the last run's state stays for a day after it ends. So the stored state alone can't
say whether a sync is in flight. The sync lease can: every run holds it from the moment it is
claimed (the Sync button claims it before answering) until it ends (#20556).

- Lease held: a sync is in flight. Its own ``running`` state is shown; anything else (none yet,
  or the previous run's result) reads as ``starting``.
- Lease free: no sync is in flight. A finished state is shown; a ``running`` one is left over
  from a run that crashed, and reads as no job.

So a poller keeps polling while the status is ``starting`` or ``running``, and stops on anything
else. No guessed wait is needed.
"""

import json

from autobot_shared.datetime_utils import datetime_now
from knowledge.connectors.sync_lease import sync_lease_held

JOB_KEY_SUFFIX = ":job:current"
IN_FLIGHT_STATUSES = ("starting", "running")


def job_key(connector_id: str) -> str:
    """The one Redis key a connector's job state lives under."""
    return "connector:%s%s" % (connector_id, JOB_KEY_SUFFIX)


def _starting(connector_id: str) -> dict:
    now = datetime_now().isoformat()
    return {"job_id": "", "started_at": now, "status": "starting", "last_updated": now}


async def read_job_state(redis, connector_id: str) -> dict | None:
    """The job a poller should see, or None when no sync is in flight and none has finished.

    Raises ``ConnectorSyncUnavailable`` when the lease can't be checked, and ``ValueError`` on a
    malformed stored state.
    """
    raw = await redis.get(job_key(connector_id))
    state = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw) if raw is not None else None
    if await sync_lease_held(connector_id):
        return state if state and state.get("status") == "running" else _starting(connector_id)
    if state and state.get("status") in IN_FLIGHT_STATUSES:
        return None
    return state
