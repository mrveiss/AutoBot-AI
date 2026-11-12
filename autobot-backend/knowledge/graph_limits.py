# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Env-backed bounds of the knowledge graph's paging (#20945); registered in ``env_registry_knowledge``."""

from autobot_shared.env_utils import env_int_clamped

# Records per bucket section when a caller does not page (the route pages by ``max_facts``).
SECTION_SAMPLE_LIMIT = env_int_clamped("AUTOBOT_KB_GRAPH_SECTION_SAMPLE_LIMIT", 25, min_v=1, max_v=500)
SECTION_PREVIEW_CHARS = env_int_clamped("AUTOBOT_KB_GRAPH_PREVIEW_CHARS", 160, min_v=20, max_v=1000)
# The largest ``offset`` a request may carry: it is a scan depth over Redis and ChromaDB.
GRAPH_MAX_OFFSET = env_int_clamped("AUTOBOT_KB_GRAPH_MAX_OFFSET", 100000, min_v=0, max_v=10000000)
# Records scanned per listing to filter by permission first, then count and page what the caller can see.
GRAPH_SCAN_LIMIT = env_int_clamped("AUTOBOT_KB_GRAPH_SCAN_LIMIT", 5000, min_v=100, max_v=100000)
SCAN_BATCH = 500
# Raw records one bucket collection read scans per request while looking for readable ones (the cap above counts
# readable records); a scan that reaches it with the collection still going reports the budget exhausted.
GRAPH_RAW_SCAN_BUDGET = env_int_clamped("AUTOBOT_KB_GRAPH_RAW_SCAN_BUDGET", 50000, min_v=100, max_v=10000000)
