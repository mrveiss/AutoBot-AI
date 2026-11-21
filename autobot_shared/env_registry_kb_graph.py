# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Knowledge-graph bucket-section AUTOBOT_* environment variable registrations (#20945).

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
