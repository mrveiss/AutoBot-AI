# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Ports for services the fleet identifies by systemd unit name (#16019).

Extracted from ``api/services.py`` because that file sits at its grandfathered
size ceiling (#14236): adding the ``redis-stack-server`` entry below pushed it
over, and a grandfathered file may not grow. The ceiling is doing exactly what
it is for -- new material goes somewhere new rather than accreting in a file
nobody can read.

**Name the unit the node actually runs.** The fleet installs
``redis-stack-server`` (``roles/redis/tasks/main.yml`` installs that package and
pins the repo to jammy on Noble, which ships no Redis Stack build). Neither
``redis`` nor ``redis-server`` is a unit on a provisioned node -- measured, both
report ``LoadState=not-found``.

That measurement carries the transferable part: **``systemctl`` answers
``ActiveState=inactive`` for a unit that does not exist**, which is the same
answer it gives for one that is merely stopped. Only ``LoadState`` separates
them. Reading ``inactive`` as "installed but stopped" is what made the per-node
view report a service the node does not have, and render it as ``unknown``.

The two legacy names stay: ``roles/redis`` records that a host with no Redis
Stack build falls back to the stock ``redis-server`` package, and a node
provisioned that way must still be identified.
"""

SERVICE_PORT_MAP = {
    "autobot-frontend": 5173,
    "autobot-backend": 8001,
    "slm-backend": 8000,
    "slm-admin-ui": 5174,
    "redis-stack-server": 6379,
    "redis-server": 6379,
    "redis": 6379,
    "grafana-server": 3000,
    "prometheus": 9090,
    "nginx": 80,
}
