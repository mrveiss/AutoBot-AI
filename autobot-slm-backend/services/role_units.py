# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The systemd unit a role's service runs under — one source (#16060).

Separate module because `role_registry.py` is at its grandfathered size ceiling
(#14236) and a grandfathered file may not grow. Same reason `ServiceStatus` and
`SERVICE_PORT_MAP` left their original homes.

**Why one source was needed.** `roles/redis` installs `redis-stack-server`, and
`systemctl show -p LoadState` reports `not-found` for both `redis` and
`redis-server` on a provisioned node. Two hardcoded copies had drifted to those
absent names: `services/reconciler.py` could not find the service it manages,
and `services/backup.py` issued `systemctl stop redis-server` against nothing —
then discarded the result, so a restore replaced the RDB under a live server.

Callers needing to tolerate a pre-Stack node state the fallback explicitly.
What this returns is what the role installs today.
"""

from services.role_registry import DEFAULT_ROLES


def systemd_unit_for_role(role_name: str) -> str | None:
    """The `systemd_service` a role declares, or None."""
    for role in DEFAULT_ROLES:
        if role.get("name") == role_name:
            return role.get("systemd_service") or None
    return None


#: The unit `roles/redis` installs. `redis` and `redis-server` are absent on a
#: provisioned node (`LoadState=not-found`), so anything issuing `systemctl`
#: against them fails — silently, where the result is not checked (#16060).
REDIS_UNIT = systemd_unit_for_role("redis") or "redis-stack-server"
