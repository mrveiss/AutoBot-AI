# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Code-indexer registration (#21317).

A sibling of ``env_registry_backend_services.py``, which has no room left under the 600-line ceiling.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CODE_INDEX_MAX_CALL_SITES_PER_EDGE",
        type=int,
        default=50,
        range=(1, 10000),
        description=(
            "Most call-site lines one code-graph call edge records. Calls past the cap are counted in the "
            "edge's dropped_call_sites rather than lost silently; raising it stores more lines per edge "
            "in the vector store's metadata (services/knowledge/code_call_sites.py)."
        ),
        component="knowledge",
    )
)
