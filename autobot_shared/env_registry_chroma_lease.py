# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Chroma per-collection write-lease AUTOBOT_* registrations (#20992).

A sibling of ``env_registry_knowledge``, which sits at the file-size ceiling; the readers are in
``autobot_shared/coordination/collection_lease.py``.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHROMA_WRITE_LEASE_TTL_S",
        type=int,
        default=60,
        description=(
            "How long a Chroma collection's write lease survives without a renew. The holder renews at a "
            "third of it while its write runs, so this bounds how long a crashed writer keeps the collection "
            "from an approved empty-collection delete; it does not limit a write's duration."
        ),
        component="knowledge",
        range=(10, 600),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHROMA_DELETE_LEASE_TTL_S",
        type=int,
        default=60,
        description=(
            "How long the exclusive lease taken by the approved empty-collection delete survives without a "
            "renew. The delete re-checks the lease between the count and the delete and does nothing if it "
            "lapsed, so a lower value only makes a slow delete give up sooner."
        ),
        component="knowledge",
        range=(10, 600),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHROMA_WRITE_LEASE_WAIT_S",
        type=int,
        default=30,
        description=(
            "Seconds a Chroma write waits for a running collection delete before it raises. A delete holds "
            "the collection for one count and one delete, so the wait is normally milliseconds; a write is "
            "never dropped silently, it lands or raises."
        ),
        component="knowledge",
        range=(1, 600),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHROMA_LEASE_POLL_MS",
        type=int,
        default=50,
        description=(
            "Milliseconds between a waiting Chroma writer's attempts to take the collection's write lease "
            "while a delete holds it."
        ),
        component="knowledge",
        range=(5, 5000),
    )
)
