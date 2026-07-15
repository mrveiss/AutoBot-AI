# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Celery Tasks Package

Contains all Celery task definitions for AutoBot IaC platform.

Note: Deployment tasks removed - now managed by SLM server (#729)
System tasks (RBAC, updates) maintained as stubs for backward compatibility.
"""

from .analytics_tasks import (
    run_bug_prediction_analysis,
    run_dashboard_analysis,
    run_dependency_analysis,
    run_duplicate_analysis,
    run_import_tree_analysis,
    run_pattern_analysis,
    run_security_analysis,
)
from .audit_log_retention import cleanup_expired_audit_logs
from .chat_retention import cleanup_expired_chats
from .credential_reconcile import reconcile_credentials
from .file_retention import cleanup_expired_files
from .knowledge_retention import cleanup_expired_kb_entries
from .knowledge_tasks import (
    cleanup_generated_files,
    cleanup_orphan_documents,
    full_man_page_index,
    prune_sync_queue_done,
    refresh_system_knowledge,
    reindex_knowledge_base,
    scan_man_page_changes,
)
from .memory_tasks import (
    compact_snapshot_task,
    extract_facts_task,
    update_graph_task,
    write_verbatim_task,
)
from .mobile_device_tasks import cleanup_stale_mobile_devices
from .snapshot_cleanup import cleanup_expired_snapshots
from .system_tasks import check_available_updates, initialize_rbac, run_system_update
from .transcriber_tasks import transcribe_recording
from .workspace_cleanup import cleanup_stale_workspaces

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
    # analytics tasks (GH#6505)
    "run_import_tree_analysis",
    "run_duplicate_analysis",
    "run_dependency_analysis",
    "run_pattern_analysis",
    "run_bug_prediction_analysis",
    "run_security_analysis",
    "run_dashboard_analysis",
    # workspace cleanup (GH#6471)
    "cleanup_stale_workspaces",
    # memory tasks
    "write_verbatim_task",
    "extract_facts_task",
    "update_graph_task",
    "compact_snapshot_task",
    # GH#8995: data-hygiene retention tasks
    "cleanup_expired_chats",
    "cleanup_expired_files",
    "cleanup_expired_audit_logs",
    "cleanup_expired_kb_entries",
    # Previously unregistered: worker never imported these modules, so their
    # @celery_app.task decorators never ran and beat-scheduled runs raised
    # "Received unregistered task of type ...".
    "reconcile_credentials",
    "cleanup_expired_snapshots",
    "cleanup_stale_mobile_devices",
    "transcribe_recording",
]
