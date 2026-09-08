# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The vocabulary a node's service status may take (#16019).

Extracted from ``models/database.py`` because that file sits at its
grandfathered size ceiling (#14236): adding the three states below pushed it
over, and a grandfathered file may not grow. The ceiling is doing what it is
for -- new material goes somewhere new rather than accreting in a file nobody
can read. `SERVICE_PORT_MAP` left `api/services.py` for the same reason.

Re-exported from ``models.database`` so the six existing importers are
unaffected.

**``UNKNOWN`` means the probe got no usable answer.** It must never mean
"systemd reported something this mapping has no branch for" -- those are
opposite situations that render identically, and conflating them made a healthy
oneshot on every node indistinguishable from a node nobody could reach.
"""

import enum


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
