# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Data for ``kb_destructive_paths_guard_21383_test.py``: files that delete knowledge-base data.

Keyed repo-relative file -> reason. Reasons: ``GATED`` (the executor behind the #17038 approval gate),
``NOT_KNOWLEDGE`` (cache, graph or benchmark state, never knowledge-base facts), ``ADAPTER`` (a vector-store
backend's own method, reached only through callers classified here), ``UNWIRED`` (no caller; a future caller must
propose), ``ARCHIVE`` (copies before it deletes), ``TRACKED_GAP #21383`` (a knowledge delete with no proposal; the
issue's script criterion removes the entry). A new entry classifies a new detector hit; THIS MAPPING ONLY SHRINKS
otherwise.
"""

from __future__ import annotations

_GAP = "TRACKED_GAP #21383: drops or deletes knowledge-base data with no #17038 proposal and no dry run"
_CACHE = "NOT_KNOWLEDGE: flushes cache/session databases, never the knowledge database"

_ADAPTER = "ADAPTER: the vector-store backend's own delete_collection; callers are classified in this mapping"
_BENCH = "NOT_KNOWLEDGE: deletes a scratch benchmark collection it created, never the knowledge collection"

ALLOWLIST: dict[str, str] = {
    "autobot-backend/services/kb_wipe_redis.py": "GATED: the executor run only after a #17038 approval (#21048)",
    "autobot-backend/api/cache_redis_databases.py": _CACHE,
    "autobot-infrastructure/shared/scripts/cache/clear-all-caches.sh": _CACHE,
    "autobot-infrastructure/shared/scripts/cache/clear-backend-cache.sh": _CACHE,
    "autobot-infrastructure/shared/scripts/utilities/init_memory_graph_redis.py": (
        "NOT_KNOWLEDGE: rebuilds the memory-graph entity indexes without deleting documents"
    ),
    "autobot-backend/services/claude_md_reindex_action.py": (
        "GATED: the CLAUDE.md chunk executor, run only after a #17038 approval (#21383)"
    ),
    "autobot-backend/services/kb_collection_delete_action.py": (
        "GATED: the collection and bulk fact delete executor, run only after a #17038 approval (#21383)"
    ),
    "autobot-backend/knowledge/index.py": (
        "UNWIRED: rebuild_chromadb_index deletes the caller-named target collection; refuses the live collection; "
        "no caller today (a new caller is not detected by this guard); one must propose through "
        "services.kb_collection_delete_action (#21383)"
    ),
    "autobot-backend/knowledge/backends/async_chromadb_adapter.py": _ADAPTER,
    "autobot-backend/knowledge/backends/async_memory_adapter.py": _ADAPTER,
    "autobot-backend/knowledge/backends/chromadb_adapter.py": _ADAPTER,
    "autobot-backend/utils/async_chromadb_client.py": _ADAPTER,
    "autobot-backend/utils/leased_chroma.py": _ADAPTER,
    "autobot-backend/utils/advanced_cache_manager.py": (
        "NOT_KNOWLEDGE: deletes cache keys (knowledge query/embedding caches)"
    ),
    "autobot-backend/api/codebase_analytics/chromadb_storage.py": (
        "NOT_KNOWLEDGE: drops and rebuilds the codebase-analytics ChromaDB collection and its cache keys"
    ),
    "autobot-backend/api/knowledge_rag.py": _BENCH,
    "autobot-backend/knowledge/rag_benchmarks.py": _BENCH,
    "autobot-infrastructure/shared/scripts/utilities/migrate_redis_to_chromadb.py": (
        "NOT_KNOWLEDGE: deletes only the <collection>_migration_test collection of a dry run"
    ),
    "autobot-backend/llc/kb/collections.py": (
        "TRACKED_GAP #21383: drop_collection deletes an entity's KB collection with no copy and no proposal (callers "
        "llc/api/work_items.py, sprints.py, companies.py, llc/services/project_disposal.py; entity lifecycle, needs a "
        "decision); the archive path in the same file is ARCHIVE (copies, then removes the original)"
    ),
    "autobot-backend/services/knowledge/doc_index_orphans.py": _GAP,
    "autobot-backend/services/knowledge/doc_indexer.py": _GAP,
}
