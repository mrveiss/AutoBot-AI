# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The vector reconciler must still be *reached* from the lifespan (#17548).

#17548 was a declared half of the projection contract that never ran: the
reconciler existed, nothing started it. The unit tests added with the fix call
``start_vector_reconciler(app)`` directly and prove it creates its task -- but
none of them goes through the lifespan, so deleting
``await start_background_workers(app)`` from ``lifespan.py`` leaves every one of
them green. That is the original defect one level up: a worker that exists, is
tested, and is not called.

This guard reads ``lifespan.py`` and ``background_workers.py`` by path and
asserts the chain, which is the part a static test *can* prove and the part that
quietly breaks. It deliberately does not import them: ``lifespan.py`` pulls in
``llc.scheduler.base``, which refuses to import below Python 3.11, so an
importing test cannot run on a 3.10 checkout at all -- and a guard that cannot
run where people work is a guard that only fails in CI.

Same shape as ``codeql_alert_ceiling_is_wired_15333_test.py``: the runtime
behaviour needs an environment this cannot have, so what is checked is that the
call site still exists.
"""

from __future__ import annotations

import ast
import pathlib

from repo_tests._paths import repo_root

_ROOT = repo_root()
_LIFESPAN = _ROOT / "autobot-backend/initialization/lifespan.py"
_WORKERS = _ROOT / "autobot-backend/initialization/background_workers.py"

#: The chain the fix relies on, in order. Each link is asserted separately so a
#: failure names which one broke rather than "the wiring".
_ENTRY_POINT = "start_background_workers"
_WORKERS_STARTED = ("start_doc_sync_queue_worker", "start_vector_reconciler")


def _tree(path: pathlib.Path) -> ast.AST:
    assert path.is_file(), f"{path.relative_to(_ROOT)} is gone; this guard's subject moved"
    return ast.parse(path.read_text(encoding="utf-8"))


def _called_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def test_the_lifespan_still_calls_the_one_entry_point():
    """The link the fix's own unit tests cannot cover, because they bypass it."""
    called = _called_names(_tree(_LIFESPAN))
    assert _ENTRY_POINT in called, (
        f"lifespan.py no longer calls {_ENTRY_POINT}() (#17548). Every unit test for the workers calls "
        "them directly, so they all still pass with this line deleted -- which is the defect #17548 "
        "reported, one level up."
    )


def test_the_lifespan_imports_it_from_the_module_that_defines_it():
    """A call to a name that is no longer imported is a NameError at startup.

    Asserted separately from the call: an import removed without the call, or a
    call moved to a different module's same-named function, are different
    breakages and should not share one failure message.
    """
    source = _LIFESPAN.read_text(encoding="utf-8")
    assert (
        f"from initialization.background_workers import {_ENTRY_POINT}" in source
    ), f"lifespan.py does not import {_ENTRY_POINT} from initialization.background_workers (#17548)"


def test_the_entry_point_starts_every_worker():
    """`start_background_workers` is one call precisely so a worker cannot be forgotten.

    Its docstring says the alternative -- one line per worker in
    `initialize_background_services` -- is a pressure "eventually paid by not
    adding the worker at all, which is how #17548 happened". This asserts the
    pressure stayed relieved.
    """
    tree = _tree(_WORKERS)
    entry = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == _ENTRY_POINT
        ),
        None,
    )
    assert entry is not None, f"{_ENTRY_POINT} is gone from background_workers.py (#17548)"

    started = _called_names(entry)
    missing = [w for w in _WORKERS_STARTED if w not in started]
    assert not missing, (
        f"{_ENTRY_POINT}() no longer starts {missing} (#17548). A worker dropped from here is a worker "
        "that exists, is unit-tested, and never runs."
    )


def test_the_reconciler_actually_creates_a_task():
    """A `start_*` that awaits nothing and schedules nothing is the #17548 shape.

    The unit tests assert this behaviourally and are the real coverage; this is
    the cheap version that still runs on an interpreter where they cannot even
    be collected.
    """
    tree = _tree(_WORKERS)
    fn = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "start_vector_reconciler"
        ),
        None,
    )
    assert fn is not None, "start_vector_reconciler is gone (#17548)"
    assert "create_task" in _called_names(fn), (
        "start_vector_reconciler no longer schedules anything (#17548) -- it would return cleanly and "
        "reconcile nothing, which is indistinguishable from working"
    )
