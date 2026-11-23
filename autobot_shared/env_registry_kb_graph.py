# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Knowledge-graph bucket-section AUTOBOT_* environment variable registrations (#20945), plus the Chroma
write-lease ones (#20992) and the category quarantine index rebuild one (#21957).

Sibling of ``env_registry_knowledge`` (which sits at the 600-line ceiling), imported by
``env_registry`` itself like every split module, so registration happens whenever it loads.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_GRAPH_SECTION_SAMPLE_LIMIT",
        type=int,
        default=25,
        description="Records sampled per knowledge-graph section; the response reports total vs returned.",
        component="knowledge",
        range=(1, 500),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_GRAPH_PREVIEW_CHARS",
        type=int,
        default=160,
        description="Characters of a bucket record shown as its knowledge-graph node name.",
        component="knowledge",
        range=(20, 1000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_GRAPH_MAX_OFFSET",
        type=int,
        default=100000,
        description="Upper bound of the knowledge-graph offset parameter (facts and bucket records to skip).",
        component="knowledge",
        range=(0, 10000000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_GRAPH_SCAN_LIMIT",
        type=int,
        default=5000,
        description="Records scanned per fact listing or bucket collection to count and page what the caller may see.",
        component="knowledge",
        range=(100, 100000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_GRAPH_RAW_SCAN_BUDGET",
        type=int,
        default=50000,
        description=(
            "Raw records one bucket collection read may scan per request to find readable ones; "
            "past it the section reports the budget exhausted."
        ),
        component="knowledge",
        range=(100, 10000000),
    )
)

# Chroma per-collection write lease (#20992); readers: autobot_shared/coordination/collection_lease.py.
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

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHROMA_LEASE_RENEW_RETRY_S",
        type=int,
        default=5,
        description=(
            "Seconds before a Chroma write lease's renew is retried after the lease registry was unreachable "
            "(never longer than the normal renew interval)."
        ),
        component="knowledge",
        range=(1, 60),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_CATEGORY_INDEX_REBUILD_BATCH",
        type=int,
        default=500,
        description=(
            "Categorised facts whose metadata is read per pipeline round trip while the category "
            "quarantine index is rebuilt (knowledge/category_quarantine.py, #21957)."
        ),
        component="knowledge",
        range=(1, 5000),
    )
)
