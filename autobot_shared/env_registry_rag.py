# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""RAG, KB-ingest and LLM-call budget AUTOBOT_* environment variable registrations (#18141, #18826, #16924).

Sibling of ``env_registry_ai.py`` (which sits at the 600-line ceiling), imported by
``env_registry`` itself like every split module, so registration happens whenever it loads.
The LLM-call budgets (transcript-analysis output tokens, the spend-record wait) are the
ai-component overflow that would otherwise belong in ``env_registry_ai.py``.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RAG_GRAPH_WEIGHT",
        type=float,
        default=0.3,
        description="Graph-signal weight in the one pre-rerank vector+graph blend (RAGConfig.graph_weight, #18141).",
        component="rag",
        range=(0.0, 1.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RAG_SCORE_THRESHOLD",
        type=float,
        default=0.3,
        description=(
            "Minimum relevance score a knowledge-retrieval result needs to be kept "
            "(constants.rag_graph_constants.RAG_SCORE_THRESHOLD, the one default, #19354)."
        ),
        component="rag",
        range=(0.0, 1.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RAG_GRAPH_TIMEOUT_SECONDS",
        type=float,
        default=10.0,
        description="Default graph-RAG search deadline in seconds (RAGConfig.graph_timeout_seconds, #18141).",
        component="rag",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DOC_HASH_CACHE_TTL_SECONDS",
        type=float,
        default=60.0,
        description="Seconds the shared stale filter reuses the doc hash cache before re-reading it (#4723, #19280).",
        component="rag",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_HTML_EXTRACT_MAX_BYTES",
        type=int,
        default=10 * 1024 * 1024,
        description=(
            "Largest HTML input, in UTF-8 bytes, the one HTML extractor parses; a longer page is "
            "truncated at a character and tag boundary and yields its leading content "
            "(media/document/html_extraction.py, #18826)."
        ),
        component="knowledge",
        range=(64 * 1024, 256 * 1024 * 1024),
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_HTML_TITLE_MAX_CHARS",
        type=int,
        default=300,
        description=(
            "Longest page title, in characters, the HTML extractor keeps from `og:title` or `<title>` "
            "(media/document/html_extraction.py, #18826)."
        ),
        component="knowledge",
        range=(40, 4096),
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_HTML_STYLE_MAX_CHARS",
        type=int,
        default=4096,
        description=(
            "Longest inline style attribute, in characters, the HTML extractor parses for hiding rules; "
            "a longer one is treated as hiding its element (fail closed) "
            "(media/document/inline_style.py, #18826)."
        ),
        component="knowledge",
        range=(256, 65536),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TRANSCRIPT_ANALYSIS_MAX_TOKENS",
        type=int,
        default=4096,
        description=(
            "Output-token budget for one transcript analysis: the transcripts analysis WebSocket "
            "and the transcriber ai/ask route (transcriber/ai/prompts.py, #16924). Set explicitly "
            "because LLMService.stream() otherwise applies the general task default of 1024, which "
            "cut long summaries and protocols off mid-answer."
        ),
        component="ai",
        range=(256, 32768),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_BUDGET_CHECK_TIMEOUT_SECONDS",
        type=float,
        default=2.0,
        description=(
            "How long the pre-call chat budget check (services/chat_budget_bounds.py, #16845) may take before "
            "the budget store counts as unavailable. What that does is decided in one place, "
            "STORE_OUTAGE_ALLOWS_REQUEST."
        ),
        component="ai",
        range=(0.1, 30.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_BUDGET_SPEND_CACHE_TTL_SECONDS",
        type=float,
        default=5.0,
        description=(
            "Seconds a scope's spend reading is reused by the chat budget gate (#16845), so a tool loop does "
            "not re-read up to 31 daily keys per iteration. Spend can exceed a limit by at most this long "
            "before a refusal. 0 disables the cache."
        ),
        component="ai",
        range=(0.0, 300.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_BUDGET_OUTAGE_LOG_INTERVAL_SECONDS",
        type=float,
        default=60.0,
        description=(
            "Minimum seconds between logged chat budget store failures (#16845); failures inside the interval "
            "are counted, not logged, so an outage does not flood the log."
        ),
        component="ai",
        range=(1.0, 3600.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LLM_SPEND_RECORD_TIMEOUT_SECONDS",
        type=float,
        default=10.0,
        description=(
            "How long an ended LLM stream waits for its spend record to be stored before letting "
            "go (services/llm_usage_recording.py, #16924). The record keeps running in the "
            "background past this, and a failure is still logged; only the wait is bounded."
        ),
        component="ai",
        range=(0.1, 120.0),
    )
)
