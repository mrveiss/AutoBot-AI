# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Celery Tasks Package

Contains all Celery task definitions for AutoBot IaC platform.

Note: Deployment tasks removed - now managed by SLM server (#729)
System tasks (RBAC, updates) maintained as stubs for backward compatibility.
"""

from .knowledge_tasks import (
    cleanup_generated_files,
    cleanup_orphan_documents,
    full_man_page_index,
    prune_sync_queue_done,
    reindex_knowledge_base,
    refresh_system_knowledge,
    scan_man_page_changes,
)
from .memory_tasks import (
    compact_snapshot_task,
    extract_facts_task,
    update_graph_task,
    write_verbatim_task,
)
from .system_tasks import check_available_updates, initialize_rbac, run_system_update

__all__ = [
    # system tasks
    "initialize_rbac",
    "run_system_update",
    "check_available_updates",
    # knowledge tasks
    "refresh_system_knowledge",
    "reindex_knowledge_base",
    "scan_man_page_changes",
    "full_man_page_index",
    "cleanup_orphan_documents",
    "cleanup_generated_files",
    "prune_sync_queue_done",
    # memory tasks
    "write_verbatim_task",
    "extract_facts_task",
    "update_graph_task",
    "compact_snapshot_task",
]
