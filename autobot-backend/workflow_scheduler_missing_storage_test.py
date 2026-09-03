# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Fresh-install safety for the scheduler's storage file (#14479).

``data/scheduled_workflows.json`` was tracked runtime state and is now
untracked (PR #15514) -- a fresh checkout or a freshly provisioned host has
no such file on disk until the scheduler itself creates one via
``_save_workflows``. This pins the load path that makes that safe:
``WorkflowScheduler.__init__`` calls ``_load_workflows`` unconditionally,
and ``_load_workflows`` must treat a missing file as "start fresh", not as
an error that aborts construction.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from workflow_scheduler import WorkflowScheduler


def test_scheduler_starts_fresh_when_storage_file_is_absent(tmp_path: Path):
    """Constructing against a nonexistent storage path must not raise.

    This is the exact shape of a fresh install: no ``scheduled_workflows.json``
    exists anywhere under ``data/`` yet.
    """
    storage_path = tmp_path / "data" / "scheduled_workflows.json"
    assert not storage_path.exists()

    scheduler = WorkflowScheduler(storage_path=str(storage_path))

    assert scheduler.scheduled_workflows == {}
    assert scheduler.completed_workflows == {}
    # The missing file must not have been created merely by loading it.
    assert not storage_path.exists()


def test_scheduler_round_trips_through_save_and_reload(tmp_path: Path):
    """After a save, a fresh scheduler pointed at the same path sees the data.

    Proves the untracked, gitignored runtime file is still fully functional
    end to end -- write, then a second process (a restart) reads it back.
    """
    storage_path = tmp_path / "data" / "scheduled_workflows.json"
    first = WorkflowScheduler(storage_path=str(storage_path))
    first.schedule_workflow(
        user_message="fresh-install round trip",
        scheduled_time=datetime.now(timezone.utc) + timedelta(minutes=5),
        tags=["test"],
    )
    first._save_workflows()
    assert storage_path.exists()

    second = WorkflowScheduler(storage_path=str(storage_path))

    assert len(second.scheduled_workflows) == 1
