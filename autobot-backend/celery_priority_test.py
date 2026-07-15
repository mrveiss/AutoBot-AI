# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Priority tiers for background Celery workers (GH#11262)."""

import celery_priority as cp


def test_priority_levels_ordered():
    assert cp.PRIORITY_CRITICAL > cp.PRIORITY_NORMAL > cp.PRIORITY_LOW
    assert 0 <= cp.PRIORITY_LOW and cp.PRIORITY_CRITICAL <= cp.MAX_PRIORITY


def test_audit_tasks_are_critical_priority():
    for name in ("workers.audit_testgaps", "workers.audit_dead_code", "workers.audit_claims"):
        assert cp.PRIORITY_TASK_ROUTES[name]["priority"] == cp.PRIORITY_CRITICAL, name


def test_cleanup_tasks_are_low_priority():
    for name in (
        "tasks.cleanup_expired_chats",
        "tasks.cleanup_expired_files",
        "tasks.cleanup_stale_workspaces",
        "tasks.cleanup_orphan_documents",
    ):
        assert cp.PRIORITY_TASK_ROUTES[name]["priority"] == cp.PRIORITY_LOW, name


def test_consolidation_slot_reserved_at_normal_priority():
    # #11263 attaches the consolidation beat entry; its route is reserved here.
    assert cp.PRIORITY_TASK_ROUTES["memory.consolidate_trajectories"]["priority"] == cp.PRIORITY_NORMAL


def test_audit_outranks_cleanup():
    routes = cp.PRIORITY_TASK_ROUTES
    assert routes["workers.audit_testgaps"]["priority"] > routes["tasks.cleanup_expired_chats"]["priority"]
