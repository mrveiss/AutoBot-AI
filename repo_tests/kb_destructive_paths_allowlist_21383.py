# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Data for ``kb_destructive_paths_guard_21383_test.py``: files that drop an index or flush a database.

Keyed repo-relative file -> reason. Reasons: ``GATED`` (the executor behind the #17038 approval gate),
``NOT_KNOWLEDGE`` (cache or graph state, never knowledge-base facts), ``TRACKED_GAP #21383`` (a knowledge
delete with no proposal; the issue's script criterion removes the entry). THIS MAPPING ONLY SHRINKS.
"""

from __future__ import annotations

_GAP = "TRACKED_GAP #21383: drops or deletes knowledge-base data with no #17038 proposal and no dry run"
_CACHE = "NOT_KNOWLEDGE: flushes cache/session databases, never the knowledge database"

ALLOWLIST: dict[str, str] = {
    "autobot-backend/services/kb_wipe_redis.py": "GATED: the executor run only after a #17038 approval (#21048)",
    "autobot-backend/api/cache_redis_databases.py": _CACHE,
    "autobot-infrastructure/shared/scripts/cache/clear-all-caches.sh": _CACHE,
    "autobot-infrastructure/shared/scripts/cache/clear-backend-cache.sh": _CACHE,
    "autobot-infrastructure/shared/scripts/utilities/init_memory_graph_redis.py": (
        "NOT_KNOWLEDGE: rebuilds the memory-graph entity indexes without deleting documents"
    ),
    "autobot-infrastructure/shared/scripts/create_kb_index.py": _GAP,
    "autobot-infrastructure/shared/scripts/kb_dimension_utility.py": _GAP,
    "autobot-infrastructure/shared/scripts/reset_kb_dimensions.py": _GAP,
    "autobot-infrastructure/shared/scripts/reset_knowledge_base.py": _GAP,
    "autobot-infrastructure/shared/scripts/database/reindex_claude_md.sh": _GAP,
}
