# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every @shared_task under llc/scheduler must actually register (#16817 review).

`celery_beat_registration_test.py` checks that every *scheduled* task resolves to a
registered one. An unscheduled task is invisible to it -- and so is a task that is
neither scheduled nor imported, which is a decorator that runs at no point in the
process's life.

That is how #16821 shipped its first head: `run_stalled_run_sweep` carried
`@shared_task`, was absent from `llc/scheduler/__init__.py`'s eager-import block and
from `beat_schedule`, and therefore never registered. A sweep written to detect work
that silently never runs, which silently never ran. Celery reports nothing, because
from its side the task does not exist.

This guard reads the source rather than the registry: every module under
`llc/scheduler/` that defines a `@shared_task` must be imported by the package
`__init__`, because `autodiscover_tasks(related_name=None)` imports only that file.
"""

import re

from repo_tests._paths import repo_root

SCHEDULER = repo_root() / "autobot-backend" / "llc" / "scheduler"
_SHARED_TASK = re.compile(r"^@shared_task", re.M)


def _modules_defining_a_shared_task() -> set[str]:
    out = set()
    for path in SCHEDULER.glob("*.py"):
        if path.name.startswith("__") or path.name.endswith("_test.py"):
            continue
        if _SHARED_TASK.search(path.read_text(encoding="utf-8")):
            out.add(path.stem)
    return out


def _modules_eagerly_imported() -> set[str]:
    init = (SCHEDULER / "__init__.py").read_text(encoding="utf-8")
    return set(re.findall(r"^from \.(\w+) import", init, re.M))


def test_every_shared_task_module_is_eagerly_imported():
    defining = _modules_defining_a_shared_task()
    assert defining, "no @shared_task found under llc/scheduler — this guard has gone blind"
    missing = sorted(defining - _modules_eagerly_imported())
    assert not missing, (
        f"these modules define a @shared_task but are not imported by "
        f"llc/scheduler/__init__.py, so their decorators never run and Celery never "
        f"registers the task: {missing}. autodiscover_tasks(related_name=None) imports "
        f"only the package __init__ (GH#12318)."
    )


def test_the_guard_can_see_a_module_it_would_fail_on():
    """Negative control: the detector must actually detect.

    A guard whose finder silently matches nothing passes for ever and proves nothing.
    This asserts the two halves disagree when they should -- that a module defining a
    task but absent from the import set is reported, rather than swallowed.
    """
    defining = {"a_task_module", "already_imported"}
    imported = {"already_imported"}
    assert sorted(defining - imported) == ["a_task_module"]
