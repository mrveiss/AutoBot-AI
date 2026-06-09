# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Backward-compatibility shim — real implementation moved to knowledge_eval.py.
This file is excluded from Docker images by .dockerignore (*_test.py pattern).
The live router is registered from api.knowledge_eval; this shim keeps test
imports of `from api import knowledge_test` working in the test suite.
"""

from api.knowledge_eval import (  # noqa: F401
    get_fresh_kb_stats,
    router,
    test_rebuild_search_index,
)
