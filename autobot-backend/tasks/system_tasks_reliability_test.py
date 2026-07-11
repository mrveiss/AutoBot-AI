# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests: reliability options on side-effectful queue tasks (#11586).

The tasks routed to the ``deployments``/``provisioning``/``services`` queues
must carry the idempotency guard, the canonical transient-error retry policy
(backoff + jitter, validation errors fail fast) and the dead-letter base so
broker redelivery cannot duplicate side effects and terminal failures are
parked instead of vanishing.

Infrastructure stubs (celery_app, Redis, logging) come from conftest.py in
this directory and the repository root — no live stack is needed.
"""

from __future__ import annotations


def _reliable_tasks():
    from tasks.system_tasks import check_available_updates, initialize_rbac, run_system_update

    return [initialize_rbac, run_system_update, check_available_updates]


def test_queue_tasks_use_dead_letter_base():
    """Terminal failures must be parked via the DeadLetterTask base."""
    from utils.celery_reliability import DeadLetterTask

    for task in _reliable_tasks():
        assert isinstance(task, DeadLetterTask), f"{task.name} missing DeadLetterTask base"


def test_queue_tasks_retry_policy():
    """Transient errors back off with jitter; retries are env-bounded."""
    from utils.celery_reliability import (
        CELERY_MAX_RETRIES,
        CELERY_RETRY_BACKOFF_MAX,
        CELERY_TRANSIENT_ERRORS,
    )

    for task in _reliable_tasks():
        assert task.autoretry_for == CELERY_TRANSIENT_ERRORS, task.name
        assert task.retry_backoff is True, task.name
        assert task.retry_jitter is True, task.name
        assert task.retry_backoff_max == CELERY_RETRY_BACKOFF_MAX, task.name
        assert task.max_retries == CELERY_MAX_RETRIES, task.name


def test_queue_tasks_never_retry_validation_errors():
    """ValueError/TypeError must not be in the autoretry set (#7010 split)."""
    for task in _reliable_tasks():
        assert ValueError not in task.autoretry_for, task.name
        assert TypeError not in task.autoretry_for, task.name


def test_queue_tasks_are_idempotency_guarded(monkeypatch):
    """Duplicate delivery of a claimed task_id must skip the task body."""
    import utils.celery_reliability as cr

    monkeypatch.setattr(cr, "_claim_task_id", lambda _task_id: False)

    for task in _reliable_tasks():
        result = task.apply(task_id="dup-guard-1").get()
        assert result == {
            "task_id": "dup-guard-1",
            "status": "skipped",
            "reason": "duplicate_delivery",
        }, f"{task.name} executed despite an existing dedup claim"
