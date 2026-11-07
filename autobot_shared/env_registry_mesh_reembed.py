# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Mesh re-embed consumer lease registration (#20535).

A sibling of ``env_registry_knowledge.py``, which has no room left under the 600-line ceiling.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MESH_REEMBED_LEASE_TTL_MS",
        type=int,
        default=120000,
        description=(
            "Lifetime of the mesh re-embed leader lease; must exceed the drain interval plus the time one "
            "item takes, since the drain refreshes it per item. Unset: four drain intervals."
        ),
        component="mesh",
        range=(1000, 3600000),
    )
)
