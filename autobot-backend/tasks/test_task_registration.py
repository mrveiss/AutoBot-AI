# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Regression test for Celery task registration (Issue #7766).

Background
----------
While fixing MVA-341 (KeyError on ``tasks.prune_sync_queue_done``), it was
discovered that ALL tasks in ``knowledge_tasks.py`` and ``memory_tasks.py``
were unregistered because their imports were missing from ``tasks/__init__.py``.
The fix added the missing imports, but without a regression guard the same
mistake can silently reappear.

What this test does
-------------------
After the tasks package is imported, every task that the application expects
to dispatch or schedule must be present in the Celery task registry.

The infrastructure stubs (celery_app, redis, logging) are set up in
``conftest.py`` and the tasks-directory ``conftest.py`` so that no live
Redis / config stack is needed.

Failure mode
------------
If a developer moves a task to a new file and forgets to add the
corresponding import to ``tasks/__init__.py``, the missing task will
silently be unavailable on production workers.  This test makes that
failure loud and immediate.
"""

from __future__ import annotations

import sys

# ---------------------------------------------------------------------------
# Expected task names — update this list whenever a task is added or renamed.
# ---------------------------------------------------------------------------

EXPECTED_TASKS: list[str] = [
    # knowledge_tasks.py  (registered as "tasks.*")
    "tasks.cleanup_orphan_documents",
    "tasks.cleanup_generated_files",
    "tasks.refresh_system_knowledge",
    "tasks.reindex_knowledge_base",
    "tasks.scan_man_page_changes",
    "tasks.full_man_page_index",
    "tasks.prune_sync_queue_done",
    # memory_tasks.py  (registered as "memory.*")
    "memory.write_verbatim",
    "memory.extract_facts",
    "memory.update_graph",
    "memory.compact_snapshot",
    # workspace_cleanup.py  (GH#6471)
    "tasks.cleanup_stale_workspaces",
]


def test_all_expected_tasks_registered():
    """Every name in EXPECTED_TASKS must appear in the Celery task registry.

    The ``celery_app`` module injected by ``conftest.py`` holds the
    lightweight in-process app that the task decorators registered against
    when the tasks package was imported during test collection.
    """
    # Retrieve the Celery app instance that conftest.py injected.
    celery_app_mod = sys.modules.get("celery_app")
    assert celery_app_mod is not None, (
        "celery_app module not found in sys.modules — " "check that conftest.py injected the stub correctly."
    )
    app = celery_app_mod.celery_app
    registered = set(app.tasks.keys())

    missing = [name for name in EXPECTED_TASKS if name not in registered]
    assert not missing, (
        f"The following tasks are NOT registered in Celery and will be "
        f"unavailable on workers: {missing!r}\n"
        f"Fix: ensure the task module is imported in tasks/__init__.py "
        f"(or listed in celery_app.autodiscover_tasks)."
    )
