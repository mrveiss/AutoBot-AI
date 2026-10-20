# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Knowledge-component AUTOBOT_* environment variable registrations.

Split out of ``env_registry_backend_services.py`` because adding these there
would push it past the file-size ceiling (600 lines).

Registration contract (import side effect, ordering): see ``env_registry``.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_CHUNK_MAX_TOKENS",
        type=int,
        default=800,
        description=(
            "Token budget (~4 chars per token) per stored chunk when KnowledgeBase.add_document "
            "splits a long document; read by knowledge/document_ingest.py (#17830)."
        ),
        component="knowledge",
        range=(50, 100000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_INGEST_RECORD_TTL_SECONDS",
        type=int,
        default=2592000,
        description=(
            "Seconds a per-document ingest status record (success/partial/timeout) is kept so a "
            "retry can resume after the last stored chunk; read by knowledge/document_ingest.py (#17986)."
        ),
        component="knowledge",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHROMA_REPAIR_LOCK_TIMEOUT_SECONDS",
        type=float,
        default=30.0,
        description=(
            "Total seconds to wait for the cross-process lock that guards the local ChromaDB "
            "store repairs before giving up; on timeout the store still opens and the repairs "
            "retry on the next open; read by utils/chromadb_store_repairs.py (#18789)."
        ),
        component="knowledge",
        range=(0.1, 3600.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_RETRY_COOLDOWN_SECONDS",
        type=int,
        default=60,
        description=(
            "Seconds after a failed knowledge-base initialization during which every access "
            "path returns None instead of retrying ChromaDB; force_refresh bypasses it; read "
            "by knowledge_factory.py (#3094, #18122)."
        ),
        component="knowledge",
        range=(1, 86400),
    )
)
