# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Priority tiers for background Celery workers (GH#11262).

Background work shares the default queue, so a burst of low-value cleanup could
delay a critical audit. Redis honours per-message priority only when the queue is
priority-enabled (``task_queue_max_priority``) and the worker drains high-priority
sub-queues first (``queue_order_strategy="priority"``). Higher number = drained
first (0..10).

This module holds the policy as plain data so it can be unit-tested without
importing the full ``celery_app`` (which pulls Redis/heavy deps and is stubbed
under pytest, issue #7766). ``celery_app`` imports and applies it.
"""

# Priority levels (0..10; higher drains first).
PRIORITY_CRITICAL = 9  # security/audit sweeps
PRIORITY_NORMAL = 5  # default — memory consolidation, analytics
PRIORITY_LOW = 2  # nightly cleanup / retention (yield to everything else)

MAX_PRIORITY = 10

# Per-task priority overrides merged into celery_app's task_routes. Tasks stay on
# their existing queue; only the drain order changes.
PRIORITY_TASK_ROUTES = {
    # Critical — security/audit sweeps jump ahead of maintenance.
    "workers.audit_testgaps": {"priority": PRIORITY_CRITICAL},
    "workers.audit_dead_code": {"priority": PRIORITY_CRITICAL},
    "workers.audit_claims": {"priority": PRIORITY_CRITICAL},
    # Normal — memory consolidation (#11263 attaches its beat entry).
    "memory.consolidate_trajectories": {"priority": PRIORITY_NORMAL},
    "memory.consolidate_facts": {"priority": PRIORITY_NORMAL},  # A3 (#12554)
    # Low — nightly cleanup / retention yields to everything else.
    "tasks.cleanup_orphan_documents": {"priority": PRIORITY_LOW},
    "tasks.cleanup_generated_files": {"priority": PRIORITY_LOW},
    "tasks.prune_sync_queue_done": {"priority": PRIORITY_LOW},
    "tasks.cleanup_stale_workspaces": {"priority": PRIORITY_LOW},
    "tasks.cleanup_stale_mobile_devices": {"priority": PRIORITY_LOW},
    "tasks.cleanup_expired_snapshots": {"priority": PRIORITY_LOW},
    "tasks.cleanup_expired_chats": {"priority": PRIORITY_LOW},
    "tasks.cleanup_expired_files": {"priority": PRIORITY_LOW},
    "tasks.cleanup_expired_audit_logs": {"priority": PRIORITY_LOW},
    "tasks.cleanup_expired_kb_entries": {"priority": PRIORITY_LOW},
}

__all__ = [
    "PRIORITY_CRITICAL",
    "PRIORITY_NORMAL",
    "PRIORITY_LOW",
    "MAX_PRIORITY",
    "PRIORITY_TASK_ROUTES",
]
