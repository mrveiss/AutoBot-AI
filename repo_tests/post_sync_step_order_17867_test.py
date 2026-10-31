# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The code-sync post-sync branches run their steps in a safe order (#17867).

Every builtin update funnels through one of four branch functions in
``autobot-slm-backend/api/code_sync.py``, and each hard-codes its sequence
imperatively. The order is correct today. **Nothing held it there.**

The sibling path is protected: ``roles.py`` builds its action list through
``ordered_post_sync_plan`` and ``test_post_sync_plan_order.py`` pins
``install -> schema -> build -> restart`` with a negative control. The
code-sync path never calls that helper -- it is a different mechanism, so
that contract does not reach it. The only ordering fact pinned here before
this guard was "a failed pip install short-circuits before reconcile"
(``test_venv_reconcile_wiring_15063.py``), which covers the first link of
the chain and none of the rest.

So a change that moved the restart ahead of the alembic migration, or
uninstalled packages before installing them, would have passed CI.

Why these orderings and not others:

* **install before remove** -- reconciliation computes removals against the
  *declared* set. Removing first means removing against a set the venv has
  not been brought to yet.
* **remove before migrate** -- a migration runs in that venv. If reconcile
  removed something it needed, the migration must be what fails, loudly and
  with a rollback, rather than the service discovering it after restart.
* **migrate before restart** -- new code must never start against an
  un-migrated schema.
* **symlink before restart** -- ``autobot_shared`` has to resolve at import
  time or the process crash-loops (#11611).
* **build before restart** -- nginx must not be reloaded onto a half-built
  asset tree.
* **health after restart** -- it is the gate that triggers rollback.

The check is syntactic (AST, no imports): it must run without the app, a
database or a deployed host.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_ROOT = repo_root()
_CODE_SYNC = Path("autobot-slm-backend/api/code_sync.py")

#: Branch functions, and the step order each must preserve. A name absent from
#: a branch is simply not constrained there; a name present must appear in
#: this relative order.
_REQUIRED_ORDER: dict[str, tuple[str, ...]] = {
    "_run_post_sync_backend_branch": (
        "_deploy_constraints_dir",
        "_deploy_repo_root_requirements",
        "_ensure_target_python_installed",
        "_ensure_venv_python",
        "_install_pip_deps_for_component",
        "reconcile_component",
        "_run_alembic_migrations",
        "_ensure_autobot_shared_symlink",
        "_restart_component_services",
        "_wait_component_healthy",
    ),
    "_run_post_sync_frontend_branch": (
        "_build_npm_frontend_for_component",
        "_restart_component_services",
        "_wait_component_healthy",
    ),
    "_run_post_sync_worker_branch": (
        "_install_pip_deps_for_component",
        "reconcile_component",
        "_restart_component_services",
        "_wait_component_healthy",
    ),
    "_run_post_sync_shared_branch": (
        "_ensure_autobot_shared_symlink",
        "_restart_dependents_with_health",
    ),
}

#: Steps that mutate the deployed tree, the venv or the schema. Every one of
#: them must happen BEFORE the first restart in its branch -- that is the
#: invariant the individual orderings above add up to, stated once so a new
#: step cannot be appended after the restart without tripping it.
_MUTATING = frozenset(
    {
        "_deploy_constraints_dir",
        "_deploy_repo_root_requirements",
        "_ensure_target_python_installed",
        "_ensure_venv_python",
        "_install_pip_deps_for_component",
        "reconcile_component",
        "_run_alembic_migrations",
        "_ensure_autobot_shared_symlink",
        "_build_npm_frontend_for_component",
    }
)

_RESTARTS = frozenset({"_restart_component_services", "_restart_dependents_with_health"})

#: The ONLY awaited calls permitted after a restart. An ALLOW-list, not a
#: deny-list, and the difference is the whole point: `_MUTATING` can only catch
#: names it already knows, so a newly added step slips past it silently. The
#: docstring above claimed this invariant catches steps "the guard does not yet
#: know about" -- with a deny-list that claim was simply false, which CodeRabbit
#: caught (#17867). Inverted, an unknown name after a restart fails until
#: somebody states why it is safe there.
_POST_RESTART_ALLOWED = frozenset({"_wait_component_healthy", "_rollback_component"})

#: Steps that MUST be present, not merely in the right place. The order check
#: drops absent names before comparing, so deleting one leaves the rest ordered
#: and green -- "absent" read as "fine", which is the failure this whole guard
#: family exists to stop, committed by the guard itself (#17867).
_MUST_EXIST: dict[str, frozenset[str]] = {
    "_run_post_sync_backend_branch": frozenset(
        {
            "_install_pip_deps_for_component",
            "_run_alembic_migrations",
            "_ensure_autobot_shared_symlink",
            "reconcile_component",
        }
    ),
    "_run_post_sync_frontend_branch": frozenset({"_build_npm_frontend_for_component"}),
    "_run_post_sync_worker_branch": frozenset({"_install_pip_deps_for_component", "reconcile_component"}),
    "_run_post_sync_shared_branch": frozenset({"_ensure_autobot_shared_symlink", "_restart_dependents_with_health"}),
}

#: Every branch must restart SOMETHING. The shared branch was the hole: it has
#: no `_wait_component_healthy` call at all, so `health_without_restart` had
#: nothing to fire on, and its `_MUST_EXIST` held only the symlink -- deleting
#: `_restart_dependents_with_health` passed every test, leaving a shared-code
#: sync that relinks and never restarts a dependent (review of #17867).
#:
#: A per-branch existence list could not express this, because the point is
#: "one of this set", not "this name".
_MUST_RESTART = frozenset(_REQUIRED_ORDER)


def _branch_names(root: Path | None = None) -> list[str]:
    """Branch functions actually present. Empty tree -> [], never a raise."""
    path = (root or _ROOT) / _CODE_SYNC
    if not path.is_file():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    return sorted(
        n.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name in _REQUIRED_ORDER
    )


REACH = declare(
    "post-sync-branch-functions",
    discover=_branch_names,
    floor=4,
    growth=4,
    skips=0,
    what="post-sync branch functions in code_sync.py whose step order is pinned",
)


def awaited_calls_in_source_order(fn: ast.AST) -> list[str]:
    """Awaited call names inside *fn*, in SOURCE order.

    Sorted by `lineno` deliberately. `ast.walk` yields breadth-first, which
    for this function returns a plausible-looking order that is NOT the
    source order -- it reported `reconcile_component` running after the
    rollback in the worker branch, and the shared branch restarting before
    its symlink restore. Both were artefacts of the traversal, and both read
    exactly like real sequencing bugs. A guard built on walk order would
    have failed on correct code and been "fixed" by reordering the source.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Await) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name:
            found.append((node.lineno, name))
    return [name for _, name in sorted(found)]


@lru_cache(maxsize=4)
def _branch_steps(root: Path | None = None) -> dict[str, tuple[str, ...]]:
    path = (root or _ROOT) / _CODE_SYNC
    if not path.is_file():
        return {}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return {}
    return {
        n.name: tuple(awaited_calls_in_source_order(n))
        for n in ast.walk(tree)
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name in _REQUIRED_ORDER
    }


def _first_index(steps: tuple[str, ...], name: str) -> int | None:
    return steps.index(name) if name in steps else None


# --------------------------------------------------------------------------
# The detectors, as pure functions over a step sequence.
#
# Extracted so the contrast tests drive THE SAME CODE the real tests do. The
# first version recomputed the post-restart rule inline inside its own
# "negative control", so it proved a copy of the logic could fail and said
# nothing about the logic (CodeRabbit, #17867) -- a negative control that does
# not call the thing it controls for is decoration.
# --------------------------------------------------------------------------


def missing_required_steps(branch: str, steps: tuple[str, ...]) -> list[str]:
    return sorted(_MUST_EXIST.get(branch, frozenset()) - set(steps))


def out_of_order_pairs(branch: str, steps: tuple[str, ...]) -> list[tuple[str, str]]:
    present = [(n, _first_index(steps, n)) for n in _REQUIRED_ORDER.get(branch, ())]
    present = [(n, i) for n, i in present if i is not None]
    return [(a, b) for (a, i), (b, j) in zip(present, present[1:]) if i >= j]


def disallowed_after_restart(steps: tuple[str, ...]) -> list[str]:
    at = next((i for i, s in enumerate(steps) if s in _RESTARTS), None)
    if at is None:
        return []
    return sorted(set(steps[at + 1 :]) - _POST_RESTART_ALLOWED - _RESTARTS)


def health_without_restart(steps: tuple[str, ...]) -> bool:
    """A health poll with no restart to gate is not a legal branch state.

    `restart=False` is legal in production, but every branch RETURNS before the
    health check in that case -- so a health call present with no restart means
    the restart was lost or renamed, not that it was skipped.
    """
    health = _first_index(steps, "_wait_component_healthy")
    restart = next((i for i, s in enumerate(steps) if s in _RESTARTS), None)
    return health is not None and restart is None


def health_before_restart(steps: tuple[str, ...]) -> bool:
    health = _first_index(steps, "_wait_component_healthy")
    restart = next((i for i, s in enumerate(steps) if s in _RESTARTS), None)
    return health is not None and restart is not None and restart > health


def install_after_reconcile(steps: tuple[str, ...]) -> bool:
    i = _first_index(steps, "_install_pip_deps_for_component")
    j = _first_index(steps, "reconcile_component")
    return i is not None and j is not None and i > j


# --------------------------------------------------------------------------


def test_every_pinned_branch_still_exists():
    """A renamed branch must fail here, not quietly stop being checked.

    Without this, deleting or renaming a branch function makes its ordering
    test vacuous -- the dictionary lookup finds nothing and every assertion
    below passes over an empty set.
    """
    REACH.verify_floor(_ROOT)
    found = _branch_names()
    REACH.completed(len(found))
    missing = sorted(set(_REQUIRED_ORDER) - set(found))
    assert not missing, f"pinned branch function(s) no longer in code_sync.py: {missing}"


@pytest.mark.parametrize("branch", sorted(_REQUIRED_ORDER))
def test_required_steps_are_present(branch):
    """Absent is not fine. The order check drops missing names before
    comparing, so a DELETED `_run_alembic_migrations` leaves the rest ordered
    and green (CodeRabbit, #17867)."""
    steps = _branch_steps().get(branch, ())
    assert steps, f"{branch}: no awaited calls found — the guard did not look"
    missing = missing_required_steps(branch, steps)
    assert not missing, f"{branch}: required step(s) no longer called at all: {missing}"


@pytest.mark.parametrize("branch", sorted(_REQUIRED_ORDER))
def test_branch_steps_run_in_the_required_order(branch):
    steps = _branch_steps().get(branch, ())
    assert steps, f"{branch}: no awaited calls found — the guard did not look"
    bad = out_of_order_pairs(branch, steps)
    assert not bad, f"{branch}: {bad[0][0]!r} must run before {bad[0][1]!r}; source order is {list(steps)}"


@pytest.mark.parametrize("branch", sorted(_REQUIRED_ORDER))
def test_nothing_unapproved_happens_after_the_first_restart(branch):
    """An ALLOW-list: anything after the restart that is not explicitly
    permitted fails, including a step this guard has never heard of."""
    steps = _branch_steps().get(branch, ())
    assert steps, f"{branch}: no awaited calls found"
    late = disallowed_after_restart(steps)
    assert not late, (
        f"{branch}: step(s) run AFTER the restart with no stated reason: {late}. "
        "If one is genuinely safe there, add it to _POST_RESTART_ALLOWED with a comment."
    )


@pytest.mark.parametrize("branch", sorted(_REQUIRED_ORDER))
def test_health_is_checked_after_a_restart_that_actually_exists(branch):
    steps = _branch_steps().get(branch, ())
    assert not health_without_restart(steps), (
        f"{branch}: a health check with no restart — the restart was lost or renamed. "
        "restart=False is legal, but the branch returns before the health call in that case."
    )
    assert not health_before_restart(steps), f"{branch}: health is polled BEFORE the restart it gates"


def test_install_precedes_removal_everywhere_both_appear():
    """Removals are computed against the declared set, so the venv must be
    brought to that set first."""
    for branch, steps in _branch_steps().items():
        assert not install_after_reconcile(
            steps
        ), f"{branch}: reconcile_component runs BEFORE the pip install it reconciles against"


@pytest.mark.parametrize("branch", sorted(_MUST_RESTART))
def test_every_branch_restarts_something(branch):
    """Deleting the restart must never be invisible.

    The shared branch polls no health URL, so the health-based checks cannot
    speak for it. Without this, losing `_restart_dependents_with_health` left
    a sync that relinks `autobot_shared` and restarts no dependent -- new
    shared code on disk, every consumer still running the old import.
    """
    steps = _branch_steps().get(branch, ())
    assert steps, f"{branch}: no awaited calls found"
    assert any(
        s in _RESTARTS for s in steps
    ), f"{branch}: performs no restart at all — new code would be deployed and never loaded"


def test_the_existence_check_itself_can_fail():
    """A self-test for `missing_required_steps`.

    Nothing guarded the existence check, so a refactor that made it always
    return [] would have silenced every `test_required_steps_are_present`
    case at once while they all still reported green (review of #17867).
    """
    assert missing_required_steps("_run_post_sync_shared_branch", ("_ensure_autobot_shared_symlink",)) == [
        "_restart_dependents_with_health"
    ]
    assert (
        missing_required_steps(
            "_run_post_sync_shared_branch",
            ("_ensure_autobot_shared_symlink", "_restart_dependents_with_health"),
        )
        == []
    )
    assert missing_required_steps("_no_such_branch", ()) == [], "an unknown branch must not invent requirements"


# --------------------------------------------------------------------------
# contrast pairs — each drives THE SAME helper the real test above calls
# --------------------------------------------------------------------------

_GOOD = (
    "_install_pip_deps_for_component",
    "reconcile_component",
    "_run_alembic_migrations",
    "_ensure_autobot_shared_symlink",
    "_restart_component_services",
    "_wait_component_healthy",
)

_BACKEND = "_run_post_sync_backend_branch"


@pytest.mark.parametrize(
    "name,detector,steps,expected",
    [
        # required-step presence
        (
            "migration deleted",
            lambda s: missing_required_steps(_BACKEND, s),
            tuple(x for x in _GOOD if x != "_run_alembic_migrations"),
            ["_run_alembic_migrations"],
        ),
        ("all present", lambda s: missing_required_steps(_BACKEND, s), _GOOD, []),
        # ordering
        (
            "restart before migrate",
            lambda s: out_of_order_pairs(_BACKEND, s),
            (
                "_install_pip_deps_for_component",
                "reconcile_component",
                "_restart_component_services",
                "_run_alembic_migrations",
            ),
            [("_run_alembic_migrations", "_restart_component_services")],
        ),
        ("ordered", lambda s: out_of_order_pairs(_BACKEND, s), _GOOD, []),
        # post-restart allow-list — an UNKNOWN name, not one in _MUTATING
        (
            "unknown step after restart",
            disallowed_after_restart,
            _GOOD + ("_some_future_step_nobody_listed",),
            ["_some_future_step_nobody_listed"],
        ),
        ("only approved after restart", disallowed_after_restart, _GOOD + ("_rollback_component",), []),
    ],
)
def test_each_detector_fires_on_its_own_defect(name, detector, steps, expected):
    assert detector(steps) == expected, name


@pytest.mark.parametrize(
    "name,detector,steps,expected",
    [
        (
            "health with no restart",
            health_without_restart,
            ("_install_pip_deps_for_component", "_wait_component_healthy"),
            True,
        ),
        ("health after restart", health_without_restart, _GOOD, False),
        (
            "health before restart",
            health_before_restart,
            ("_wait_component_healthy", "_restart_component_services"),
            True,
        ),
        ("health after restart", health_before_restart, _GOOD, False),
        (
            "reconcile before install",
            install_after_reconcile,
            ("reconcile_component", "_install_pip_deps_for_component"),
            True,
        ),
        ("install before reconcile", install_after_reconcile, _GOOD, False),
    ],
)
def test_each_boolean_detector_fires_on_its_own_defect(name, detector, steps, expected):
    assert detector(steps) is expected, name


# --------------------------------------------------------------------------
# negative controls — each proves an assertion above can actually fail
# --------------------------------------------------------------------------

_MUTATED_BRANCH = """
async def _run_post_sync_backend_branch(component, snapshot, steps, restart):
    pip_ok = await _install_pip_deps_for_component(component, steps)
    await _restart_component_services(component, steps)
    await _run_alembic_migrations(component, deployed_dir, steps)
    await _wait_component_healthy(component, steps)
"""


def _steps_of(src: str, name: str) -> tuple[str, ...]:
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree) if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == name)
    return tuple(awaited_calls_in_source_order(fn))


def test_a_reordered_branch_is_caught_end_to_end_in_real_source():
    """The section header's claim, finally asserted (#17868 review).

    Every other end-to-end run in this file is against the REAL source, where
    every detector correctly returns clean — so the catching direction was only
    ever exercised in the passing case. The detectors are covered on synthetic
    tuples by the parametrized contrast tests, and the extraction path is
    covered by the real-file tests. What nothing asserted until now is the
    whole chain on text that is genuinely out of order: source -> ast ->
    extraction -> verdict. `_MUTATED_BRANCH` and `_steps_of` were written for
    exactly this and left unwired, which made the header above a claim the
    section did not support.
    """
    steps = _steps_of(_MUTATED_BRANCH, _BACKEND)

    assert out_of_order_pairs(_BACKEND, steps) == [("_run_alembic_migrations", "_restart_component_services")]


@pytest.mark.parametrize("branch", ["_run_post_sync_backend_branch", "_run_post_sync_worker_branch"])
def test_a_branch_missing_reconcile_is_reported(branch):
    """The new `reconcile_component` entry fires, rather than merely being present.

    Both branches await it (verified by AST against the real source: backend at
    2874-2916, worker at 2944-2971); neither listed it. It matters that this is
    `_MUST_EXIST` and not an ordering entry -- `out_of_order_pairs` drops absent
    names before comparing, so every ordering and boolean detector in this file is
    presence-blind by construction. `_MUST_EXIST` is the only absence detector,
    which makes omission from it silent rather than merely untidy.
    """
    steps = tuple(n for n in sorted(_MUST_EXIST[branch]) if n != "reconcile_component")

    assert missing_required_steps(branch, steps) == ["reconcile_component"]


def test_source_order_differs_from_walk_order_on_the_real_file():
    """The bug this guard was nearly built on.

    `ast.walk` is breadth-first, so an `await` inside an `if` body surfaces
    after one at the function's top level regardless of line. On the real
    worker branch that reports `reconcile_component` running after the
    rollback. If this ever stops differing the lru_cache and the sort are
    still correct — but the comment above would have lost its evidence, so
    assert the difference exists rather than trusting the recollection.
    """
    path = _ROOT / _CODE_SYNC
    tree = ast.parse(path.read_text(encoding="utf-8"))
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == "_run_post_sync_worker_branch"
    )
    walk_order = [
        (f.id if isinstance(f, ast.Name) else getattr(f, "attr", None))
        for node in ast.walk(fn)
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call)
        for f in [node.value.func]
    ]
    assert walk_order != awaited_calls_in_source_order(fn), (
        "walk order now matches source order; the sort is still right, but this "
        "test's premise needs re-checking rather than silently passing"
    )
