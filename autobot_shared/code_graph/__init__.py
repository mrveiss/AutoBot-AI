# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical code-graph node identity and callee resolver (#13470).

Single-sourced so ``services/knowledge/code_indexer.py`` (#13469) and
``api/codebase_analytics/endpoints/call_graph.py`` (#713) resolve callees and
name nodes the same way instead of maintaining incompatible schemes.
"""

from autobot_shared.code_graph.identity import (
    compute_node_id,
    module_path_from_rel_path,
    project_relative_path,
)
from autobot_shared.code_graph.resolver import (
    COMMON_THIRD_PARTY,
    INTERNAL_MODULE_PREFIXES,
    STDLIB_MODULES,
    ImportContext,
    ResolvedCall,
    is_external_module,
    resolve_call,
    resolve_callee,
    resolve_callee_by_suffix,
)

__all__ = [
    "compute_node_id",
    "module_path_from_rel_path",
    "project_relative_path",
    "COMMON_THIRD_PARTY",
    "INTERNAL_MODULE_PREFIXES",
    "STDLIB_MODULES",
    "ImportContext",
    "ResolvedCall",
    "is_external_module",
    "resolve_call",
    "resolve_callee",
    "resolve_callee_by_suffix",
]
