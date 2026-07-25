# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Explicit, logged reconciliation of the persisted Beat scheduler state (#12354).

Background
----------
Celery's default ``PersistentScheduler`` already merges ``app.conf.beat_schedule``
into its on-disk shelve store on every clean process startup
(``celery.beat.Scheduler.merge_inplace``), popping any persisted entry whose
*name* is no longer a key in ``beat_schedule``. That merge is silent
(debug-level logging only), so when a renamed/removed task keeps firing in
production — e.g. #10337->#10666 renamed the ``reconcile-unified-credentials-
hourly`` entry (task ``tasks.reconcile_unified_credentials``) to
``reconcile-credentials-hourly`` (task ``tasks.reconcile_credentials``), yet
workers kept logging "Received unregistered task of type
tasks.reconcile_unified_credentials" (#12354) — there is no log evidence of
whether the running Beat process ever actually re-merged, and nothing catches
the case where a scheduler entry's *task* string alone drifts from
``beat_schedule`` while its *name*/key is reused.

``reconcile_schedule`` makes that reconciliation explicit, loud, and testable:
given the live scheduler's ``schedule`` mapping and the set of task names
declared in ``celery_app.conf.beat_schedule``, prune (and return) every entry
whose ``task`` is not in that set. Wired into celery_app.py's ``beat_init``
signal handler so it runs — and logs — on every Beat startup, self-healing a
stale persisted entry even if the process that produced it never restarts
cleanly.
"""

from __future__ import annotations

import logging
from typing import Mapping, MutableMapping, Protocol

logger = logging.getLogger(__name__)


class _ScheduleEntryLike(Protocol):
    task: str


def reconcile_schedule(
    schedule: MutableMapping[str, _ScheduleEntryLike],
    valid_tasks: Mapping[str, object] | set,
) -> list[str]:
    """Prune persisted schedule entries whose task is not in ``valid_tasks``.

    Args:
        schedule: A live, mutable mapping of entry name -> object exposing a
            ``.task`` attribute (a Celery ``ScheduleEntry``, or any stand-in
            with the same shape for testing). Mutated in place.
        valid_tasks: The set of task names ``celery_app.conf.beat_schedule``
            currently declares. Accepts a set or any container supporting
            ``in`` (a dict of task->entry works too).

    Returns:
        The sorted list of entry names that were pruned (empty when the
        persisted schedule already matches ``beat_schedule``).
    """
    stale = sorted(name for name, entry in schedule.items() if entry.task not in valid_tasks)
    for name in stale:
        logger.warning(
            "Beat startup reconciliation: pruning stale persisted schedule entry "
            "%r (task=%r not in current beat_schedule) — GH#12354",
            name,
            schedule[name].task,
        )
        del schedule[name]
    return stale
