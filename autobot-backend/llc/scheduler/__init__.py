# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC scheduler package.

Split import policy (#13332) — read this before adding an import here.

This package has two kinds of member and they must be imported differently:

1. **Celery task modules — EAGER, and they must stay eager (GH#12318).**
   ``celery_app.autodiscover_tasks([... "llc.scheduler"], related_name=None)``
   imports this ``__init__`` and nothing else in the package.  The
   ``@shared_task`` decorators in ``project_disposal_sweep`` and
   ``sprint_autoclose`` only run if this module imports them, so a PEP 562
   conversion of these two would unregister both beat jobs and reproduce the
   original defect: beat dispatching ``llc.scheduler.sprint_autoclose.
   run_daily_check`` to a worker that logs "Received unregistered task of type
   ..." and drops it, with no other symptom.  ``celery_beat_registration_test``
   fails if either import is removed from this module.

2. **Scheduler classes — LAZY (PEP 562), as ``llc.services`` already is (#13057).**
   ``BudgetWatchdog``/``LivenessMonitor``/``SessionCheckpointer`` drag in
   ``llc.services.*``, ``user_management.database`` and the SQLAlchemy model
   tree.  Python initialises a parent package before any submodule, so importing
   *only* ``llc.scheduler.base`` — three stdlib imports and one helper — used to
   pay for all of them.  Every call site in this repo already imports the
   concrete submodule directly (``from llc.scheduler.liveness_monitor import
   LivenessMonitor``), so nothing imports these names from the package today;
   the re-export contract is preserved regardless.

The eager half is not free, and the remaining cost is deliberate rather than
overlooked: ``sprint_autoclose`` still reaches ``user_management.database`` and
``utils.celery_reliability``, because ``@shared_task`` needs
``DeadLetterTask`` at decoration time.  What it no longer reaches is the
expensive tail — see ``sprint_autoclose``'s own note on deferring
``SprintAutoCloseService`` (``llc.kb.sprint_summarizer`` -> ``llm_shared.types``,
which probes PyTorch/CUDA at import, and ``llc.kb.collections``).  That chain was
the measured symptom in #13332.
"""

from typing import Any

# EAGER — Celery task registration depends on these two lines (GH#12318).
# Do not convert them to lazy attributes; see the module docstring.
from .project_disposal_sweep import run_disposal_sweep
from .sprint_autoclose import run_daily_check

__all__ = [
    "PollLoopScheduler",
    "BudgetWatchdog",
    "LivenessMonitor",
    "SessionCheckpointer",
    "run_disposal_sweep",
    "run_daily_check",
]

# name -> submodule it lives in, so __getattr__ imports exactly one module.
_LAZY_ATTRS: dict[str, str] = {
    "PollLoopScheduler": "base",
    "BudgetWatchdog": "budget_watchdog",
    "LivenessMonitor": "liveness_monitor",
    "SessionCheckpointer": "session_checkpointer",
}


def __getattr__(name: str) -> Any:
    """PEP 562 lazy attribute resolution — one submodule import per name."""
    module_name = _LAZY_ATTRS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    import importlib

    module = importlib.import_module(f".{module_name}", __name__)
    value = getattr(module, name)
    globals()[name] = value  # cache: subsequent access skips __getattr__ entirely
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
