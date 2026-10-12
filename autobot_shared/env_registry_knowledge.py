# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Knowledge-indexing AUTOBOT_* environment variable registrations.

Split out of ``env_registry_backend_services.py`` when the KB ingestion variables
(#17830, #17986) took it past the 600-line ceiling; imported by ``env_registry`` itself like
every split module, so registration happens whenever it loads.

Registration contract (import side effect, ordering): see ``env_registry`` (#16415).
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CODE_INDEX_GIT_TIMEOUT_SECONDS",
        type=int,
        default=10,
        description=(
            "Ceiling on each read-only git call the code indexer's "
            "provenance lookups make. Raising it tolerates a slower git "
            "history walk on a large repo; lowering it fails a stalled git "
            "call faster, at the risk of a false timeout on a legitimately "
            "slow repo (services/knowledge/code_indexer.py)."
        ),
        component="knowledge",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_COGNIFIER_BATCH_MAX_TOKENS_PER_CHUNK",
        type=int,
        default=1024,
        description=(
            "Per-chunk token budget used to scale max_tokens with the number "
            "of chunks packed into one batched cognifier extraction call "
            "(#11012). Raising it reduces truncation risk for large chunks; "
            "lowering it caps per-chunk cost, at the risk of truncating "
            "longer chunks (knowledge/pipeline/cognifiers/llm_utils.py)."
        ),
        component="knowledge",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_COGNIFIER_BATCH_MAX_TOKENS_CAP",
        type=int,
        default=8192,
        description=(
            "Absolute ceiling on the max_tokens sent for a batched cognifier "
            "extraction call, regardless of batch size (#11012). Raising it "
            "allows a larger batched response before truncation; lowering it "
            "protects against an oversized request to the LLM provider "
            "(knowledge/pipeline/cognifiers/llm_utils.py)."
        ),
        component="knowledge",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_VECTORIZE_CHECK_INTERVAL_SECONDS",
        type=int,
        default=300,
        description=(
            "Seconds between vector-reconciler wakes (#17548). The reconciler finds knowledge "
            "facts that were stored but never vectorised -- the declared half of the projection "
            "contract that previously never ran. Env-backed rather than a literal because the "
            "cadence suiting a KB with a handful of facts is not the one suiting a large one, and "
            "floored at 30s so a misconfiguration cannot turn it into a busy loop against Redis. "
            "Prefixed AUTOBOT_ deliberately: the registry's sweep is keyed on that prefix, so an "
            "unprefixed name is not reported as unregistered, it is invisible (#17751)."
        ),
        component="knowledge",
    )
)


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
