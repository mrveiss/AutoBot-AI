# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""Compatibility shim — canonical hybrid scorer lives in autobot_memory_graph (#3612, #12650).

This module implemented the Phase 2 hybrid scorer (#3384) for the
now-retired parallel `knowledge/memory_graph/` package. #3612 folded that
capability into `autobot_memory_graph/semantic_search.py` precisely so this
package would never be needed, but the concrete implementation here was left
behind instead of being repointed. The #12650 caller audit found zero
production callers of this module (only its own now-updated test).

Kept as a re-export shim rather than deleted — never delete code, wire it
in. Import from `autobot_memory_graph.semantic_search` directly for new code.
"""

from autobot_memory_graph.semantic_search import (  # noqa: F401
    HybridScorer,
    SearchResult,
)
