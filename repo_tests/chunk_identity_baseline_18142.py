# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Sites that still read `chunk_id` inline instead of calling `resolve_chunk_id` (#18142). SHRINK-ONLY.

Each entry is a repo-relative path and how many inline reads it holds. The guard fails when a file
is missing from here, holds more than listed, or holds fewer (lower the number -- never raise it).
"""

BASELINE: dict[str, int] = {
    # Reads a request payload / a stored fact record's own `chunk_id` field, not a search hit's identity.
    "autobot-backend/agents/knowledge_extraction_agent.py": 2,
    "autobot-backend/models/atomic_fact.py": 1,
}
