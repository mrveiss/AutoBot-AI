# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Mesh re-embed consumer lease registration (#20535).

A sibling of ``env_registry_knowledge.py``, which has no room left under the 600-line ceiling.
"""

from __future__ import annotations

#: The ONE default for ``AUTOBOT_MESH_REEMBED_INTERVAL_S`` (#21102): seconds between drain passes.
REEMBED_INTERVAL_DEFAULT_S = 30

#: How many drain intervals the leader lease lives when ``AUTOBOT_MESH_REEMBED_LEASE_TTL_MS`` is unset.
REEMBED_LEASE_INTERVALS = 4


def reembed_lease_ttl_default_ms(interval_s: int) -> int:
    """The ONE rule for the unset lease TTL (#21102): ``REEMBED_LEASE_INTERVALS`` drain intervals, in ms.

    The registry entry below and ``reembed_consumer.LEASE_TTL_MS`` both call it, so a changed interval
    moves the consumer's effective default and the registry default cannot name a different one. Defined
    above the registry import (as ``env_registry_tls`` does) so the consumer can import it while
    ``env_registry`` is still loading this module and the registry stays importable on a bare interpreter.
    """
    return interval_s * REEMBED_LEASE_INTERVALS * 1000


from autobot_shared.env_registry import EnvVarSpec, register_env_var  # noqa: E402 -- constants first, see above

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MESH_REEMBED_LEASE_TTL_MS",
        type=int,
        default=reembed_lease_ttl_default_ms(REEMBED_INTERVAL_DEFAULT_S),
        description=(
            "Lifetime of the mesh re-embed leader lease; must exceed the drain interval plus the time one "
            "item takes, since the drain refreshes it per item. Unset: four drain intervals."
        ),
        component="mesh",
        range=(1000, 3600000),
    )
)

# --- mesh re-embed consumer (#20535) ---
register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MESH_REEMBED_ENABLED",
        type=bool,
        default=True,
        description=(
            "Run the consumer that drains mesh:reembed_queue into the document re-index "
            "queue. Turning it off lets the queue grow unread "
            "(services/mesh_brain/reembed_consumer.py)."
        ),
        component="mesh",
    )
)
register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MESH_REEMBED_INTERVAL_S",
        type=int,
        default=REEMBED_INTERVAL_DEFAULT_S,
        description="Seconds between drain passes of mesh:reembed_queue by the lease-holding worker.",
        component="mesh",
        range=(1, 3600),
    )
)
register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MESH_REEMBED_BATCH",
        type=int,
        default=100,
        description="Maximum items taken from mesh:reembed_queue in one drain pass.",
        component="mesh",
        range=(1, 10000),
    )
)
register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MESH_REEMBED_MAX_ATTEMPTS",
        type=int,
        default=3,
        description=(
            "Attempts per mesh:reembed_queue item before it is moved to the mesh:reembed_dead dead-letter list."
        ),
        component="mesh",
        range=(1, 20),
    )
)
