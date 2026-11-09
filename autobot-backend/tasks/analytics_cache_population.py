# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Daily off-peak population of the analytics ``/cached`` stores (Issue #12365).

Six analytics modules (bug-prediction, security-score, anti-pattern,
dependencies, duplicates, import-tree) each expose ``analyze`` (live/slow),
``cached`` (read a store), and ``status`` -- but nothing ever populated the
store, so every ``/cached`` was empty (Part 1 of #12365 made that degrade
gracefully; this is Part 2: actually fill the store).

Design: reuse the EXISTING per-module Celery tasks in ``tasks.analytics_tasks``
(the same ones ``POST /api/.../analyze`` already dispatches on demand) rather
than reimplementing any analysis. For the five modules whose ``/cached``
reads via ``get_latest_task_result(prefix)`` (a Redis pointer to the latest
Celery task id), dispatching the task and recording it as latest IS the
store-write -- the task's own return value becomes the Celery result the
pointer resolves to. Anti-pattern is the exception: its detector writes
straight into its own Redis key inside ``analyze()``, so no pointer step is
needed for it.

Scope (#20513): dependencies, duplicates and import-tree are source-scoped tasks; they are
dispatched once per registered source that has a checkout, and each result is recorded under that
source's own task-id prefix. The other three analyse AutoBot's own project root, as on demand.
"""

from datetime import datetime, timezone
from pathlib import Path

from api.source_scope import source_scoped_prefix
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as ssot_config
from celery_app import celery_app
from tasks.analytics_tasks import _run_async, _wrap
from utils.celery_task_status import store_latest_task_id

logger = get_logger(__name__)

# Issue #12365: seconds between each module's dispatch so 6 analyses (one up
# to ~280s) don't all run at once and spike CPU/IO. Configurable via
# AUTOBOT_ANALYTICS_CACHE_POPULATION_STAGGER_SECONDS (ssot_config), not hardcoded.
_STAGGER_SECONDS = ssot_config.analytics_cache_population_stagger_seconds


async def _dispatch(task, args: tuple, prefix: str | None, countdown: int) -> str:
    """Enqueue *task* with *countdown* stagger; record it as latest for *prefix*.

    *prefix* is the Redis key prefix ``get_latest_task_result`` reads to
    resolve the pointer to this dispatch's Celery result. Anti-pattern passes
    ``prefix=None`` -- its detector writes its own cache directly inside
    ``analyze()``, so no pointer is needed.
    """
    result = task.apply_async(args=args, countdown=countdown)
    if prefix is not None:
        await store_latest_task_id(prefix, result.id)
    return result.id


def _build_modules(project_root: str, source_ids: tuple[str, ...] = ()) -> list[tuple]:
    """Build the (name, task, args, redis_prefix) tuples for all modules.

    The three source-scoped modules (dependencies, duplicates, import_tree) get one entry per id
    in *source_ids*, named ``<module>:<id>`` and recorded under that source's own prefix (#20513).

    Imported lazily inside the task body (not module scope) to avoid a
    heavy-import chain at Celery worker/beat startup, matching the existing
    lazy-import convention in tasks/analytics_tasks.py's ``_work`` closures.
    """
    from api.analytics_bug_prediction import _REDIS_PREFIX as _BUG_PREFIX
    from api.code_intelligence import _REDIS_PREFIX as _SEC_PREFIX
    from api.codebase_analytics.endpoints.dependencies import _REDIS_PREFIX as _DEP_PREFIX
    from api.codebase_analytics.endpoints.duplicates import _REDIS_PREFIX as _DUP_PREFIX
    from api.codebase_analytics.endpoints.import_tree import _REDIS_PREFIX as _IMPORT_PREFIX
    from tasks.analytics_tasks import (
        run_anti_pattern_analysis,
        run_bug_prediction_analysis,
        run_dependency_analysis,
        run_duplicate_analysis,
        run_import_tree_analysis,
        run_security_analysis,
    )

    scoped = [
        (f"{name}:{sid}", task, (sid,), source_scoped_prefix(prefix, sid))
        for name, task, prefix in (
            ("dependencies", run_dependency_analysis, _DEP_PREFIX),
            ("duplicates", run_duplicate_analysis, _DUP_PREFIX),
            ("import_tree", run_import_tree_analysis, _IMPORT_PREFIX),
        )
        for sid in source_ids
    ]
    return scoped + [
        ("bug_prediction", run_bug_prediction_analysis, (project_root, "*.py", 10000), _BUG_PREFIX),
        ("security_score", run_security_analysis, (project_root,), _SEC_PREFIX),
        # No redis_prefix: AntiPatternDetector.analyze() writes its own cache directly.
        ("anti_pattern", run_anti_pattern_analysis, (project_root,), None),
    ]


async def _sources_with_checkout() -> tuple[str, ...]:
    """Ids of the registered sources whose checkout directory exists (#20513)."""
    from api.codebase_analytics.source_storage import list_sources

    return tuple(
        str(source.id) for source in await list_sources() if source.clone_path and Path(source.clone_path).is_dir()
    )


async def _populate_all(project_root: str, source_ids: tuple[str, ...] = ()) -> dict:
    """Dispatch all 6 modules' background analyze tasks, staggered.

    Each module is wrapped independently: one module failing to dispatch does
    not prevent the others from being scheduled. Extracted from the Celery
    task body so it's directly unit-testable with ``asyncio.run`` (no Celery
    eager-mode machinery needed).
    """
    modules = _build_modules(project_root, source_ids)

    results: dict = {}
    for i, (name, task, args, prefix) in enumerate(modules):
        countdown = i * _STAGGER_SECONDS
        try:
            task_id = await _dispatch(task, args, prefix, countdown)
            results[name] = {"status": "dispatched", "task_id": task_id, "countdown": countdown}
            logger.info(
                "populate_all_caches: dispatched %s (task_id=%s, countdown=%ds)",
                name,
                task_id,
                countdown,
            )
        except Exception as e:
            logger.error("populate_all_caches: failed to dispatch %s: %s", name, e, exc_info=True)
            results[name] = {"status": "failed", "error": str(e)}

    return results


@celery_app.task(bind=True, name="analytics.populate_all_caches")
def populate_all_caches(self) -> dict:
    """Daily off-peak dispatch of all 6 analytics modules' background analyze
    tasks, staggered so they don't all run simultaneously (Issue #12365)."""
    started = datetime.now(tz=timezone.utc).isoformat()

    async def _work():
        from api.codebase_analytics.endpoints.shared import resolve_git_repo_root

        return await _populate_all(resolve_git_repo_root(), await _sources_with_checkout())

    return _wrap(_run_async(_work()), started)
