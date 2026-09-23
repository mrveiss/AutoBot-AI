# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The vocabulary a node's service status may take (#16019).

Extracted from ``models/database.py`` because that file sits at its
grandfathered size ceiling (#14236): adding the three states below pushed it
over, and a grandfathered file may not grow. `SERVICE_PORT_MAP` left
`api/services.py` for the same reason.

**Top-level, deliberately not under ``models/``.** ``from models.x import ...``
imports the models PACKAGE, and ``models/__init__.py`` pulls in
``user_management`` and thence ``autobot_shared``. The migration runner has
neither on its path, so placing this under ``models/`` turned a flat module
import into a package import and broke `SLM migration runner — Postgres 16`
with ``ModuleNotFoundError: No module named 'autobot_shared'``.

Re-exported from ``models.database`` so the six existing importers are
unaffected.

**``UNKNOWN`` means the probe got no usable answer.** It must never mean
"systemd reported something this mapping has no branch for" -- those are
opposite situations that render identically, and conflating them made a healthy
oneshot on every node indistinguishable from a node nobody could reach.
"""

import enum
from typing import Dict


class ServiceStatus(str, enum.Enum):
    """Systemd service status enumeration."""

    RUNNING = "running"
    #: `active (exited)` -- a oneshot that succeeded. Neither RUNNING (nothing
    #: is resident) nor STOPPED, and emphatically not UNKNOWN: `slm-admin-ui`
    #: and the `postgresql` wrapper are in this state on every healthy node.
    COMPLETED = "completed"
    STARTING = "starting"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    CRASH_LOOP = "crash-loop"  # Issue #1604: activating/auto-restart
    #: See the module docstring: no reachable systemd state maps here.
    UNKNOWN = "unknown"


#: Healthy for the operator's counts (#16019): COMPLETED is a succeeded oneshot.
_HEALTHY_STATUSES = (ServiceStatus.RUNNING.value, ServiceStatus.COMPLETED.value)


def bucket_service_counts(rows) -> Dict[str, int]:
    """`(status, count)` rows -> `{"running": n, "failed": n}` (#16019).

    One implementation for both aggregates -- they had drifted apart once.
    """
    counts = {"running": 0, "failed": 0}
    for row in rows:
        if row.status in _HEALTHY_STATUSES:
            counts["running"] += row.count
        elif row.status == ServiceStatus.FAILED.value:
            counts["failed"] += row.count
    return counts
