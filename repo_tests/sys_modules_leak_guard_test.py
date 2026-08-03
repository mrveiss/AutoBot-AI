# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit cover for the repo-wide sys.modules leak guard (#13337, #13398).

The guard's whole value is that it fires on a real leak and stays silent on
everything else, so both halves are pinned here.  The classifier and the
escape rule are exercised directly against a throwaway ``sys.modules`` — no
nested pytest session, so every test finishes in milliseconds.

The baseline ratchet is covered at both ends: the bookkeeping that decides
whether a listed owner was given a chance to leak, and the verdict that turns
that plus the leak records — the workers' included — into an exit status.  The
end-to-end transitions live in the nested-session tests next door.
"""

from __future__ import annotations

import sys
import types
import warnings
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from repo_tests import sys_modules_leak_guard as guard_module
from repo_tests.sys_modules_leak_guard import _DISK_CACHE, _Baseline, _LeakGuard, _load_baseline

_ROOT = Path("/repo")
_LLC_CONFTEST = _ROOT / "backend" / "llc" / "tests" / "conftest.py"
_OTHER_MODULE = _ROOT / "backend" / "initialization" / "lifespan_test.py"

# The same conftest as the guard displays it: repo-relative, the form a
# baseline line holds.
_LLC_OWNER = "backend/llc/tests/conftest.py"


@pytest.fixture
def make_guard(monkeypatch):
    """Build guards over an isolated ``sys.modules`` copy.

    ``_DISK_CACHE`` is pre-seeded so the tests never depend on what happens to
    be installed on the machine running them.
    """
    monkeypatch.setattr(sys, "modules", dict(sys.modules))
    monkeypatch.setattr(
        "repo_tests.sys_modules_leak_guard._DISK_CACHE",
        dict(_DISK_CACHE, agents=True, autobot_shared=True, celery=True, knowledge=True, _sodium=False),
    )

    def build(removal_candidates: frozenset[str] = frozenset()) -> _LeakGuard:
        instance = _LeakGuard(_ROOT, removal_candidates)
        instance.snapshot()
        return instance

    return build


@pytest.fixture
def guard(make_guard):
    """A guard with an empty baseline: nothing is listed, every leak is new."""
    return make_guard()


def _install(name: str, module: object) -> None:
    sys.modules[name] = module  # type: ignore[assignment]


def _leaks_for(guard: _LeakGuard, path: Path) -> list[str]:
    """Run a check with warnings suppressed and return the leaked keys."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        guard.check(path, f"the import of {path.name}")
    return [leak.mutation.key for leak in guard.leaks]


# ---------------------------------------------------------------------------
# It fires on the three leak shapes that actually happened
# ---------------------------------------------------------------------------


def test_reports_a_synthetic_top_level_stub_reaching_a_sibling(guard):
    """The #13337 shape: an ``agents`` stub live while a sibling is imported."""
    _install("agents", types.ModuleType("agents"))
    guard.attribute(_LLC_CONFTEST)

    assert _leaks_for(guard, _OTHER_MODULE) == ["agents"]


def test_reports_a_replaced_real_module(guard):
    """The #13324 shape: ``autobot_shared`` swapped for a bare MagicMock."""
    _install("autobot_shared", types.ModuleType("autobot_shared"))
    guard.snapshot()
    _install("autobot_shared", MagicMock())
    guard.attribute(_LLC_CONFTEST)

    assert _leaks_for(guard, _OTHER_MODULE) == ["autobot_shared"]


def test_the_message_names_the_key_the_owner_and_the_importer(guard):
    """A silent or vague guard is worthless — the report must be actionable."""
    _install("agents", types.ModuleType("agents"))
    guard.attribute(_LLC_CONFTEST)
    _leaks_for(guard, _OTHER_MODULE)

    described = guard.leaks[0].describe()
    assert "'agents'" in described
    assert "backend/llc/tests/conftest.py" in described
    assert "lifespan_test.py" in described


def test_a_leak_raises_a_pytest_warning(guard):
    """The warning is the machine-readable half of "report loudly"."""
    _install("agents", types.ModuleType("agents"))
    guard.attribute(_LLC_CONFTEST)

    with pytest.warns(pytest.PytestWarning, match="agents"):
        guard.check(_OTHER_MODULE, "the import of lifespan_test.py")


# ---------------------------------------------------------------------------
# It stays silent on everything that is not a leak
# ---------------------------------------------------------------------------


def test_a_stub_used_only_inside_its_own_directory_is_not_a_leak(guard):
    """Scoped stubs are the correct pattern and must never be reported."""
    _install("agents", types.ModuleType("agents"))
    guard.attribute(_LLC_CONFTEST)

    sibling = _LLC_CONFTEST.parent / "test_something.py"
    assert _leaks_for(guard, sibling) == []


def test_a_parent_directorys_stub_covers_its_whole_subtree(guard):
    """``autobot-backend/conftest.py`` legitimately stubs for everything below."""
    backend_conftest = _ROOT / "backend" / "conftest.py"
    _install("celery", types.ModuleType("celery"))
    guard.attribute(backend_conftest)

    assert _leaks_for(guard, _OTHER_MODULE) == []


def test_an_ordinary_import_is_never_reported(guard, tmp_path):
    """A module the import system loaded has a ``__spec__`` and is left alone."""
    real = types.ModuleType("some_real_module")
    real.__spec__ = object()  # type: ignore[assignment]
    real.__file__ = str(tmp_path / "some_real_module.py")
    _install("some_real_module", real)
    guard.attribute(_LLC_CONFTEST)

    assert _leaks_for(guard, _OTHER_MODULE) == []


def test_extension_pseudo_submodules_are_not_stubs(guard):
    """``_sodium.lib``/``xml.parsers.expat.errors`` have no spec but are real."""
    parent = types.ModuleType("_sodium")
    parent.__spec__ = object()  # type: ignore[assignment]
    _install("_sodium", parent)
    guard.snapshot()
    _install("_sodium.lib", types.ModuleType("_sodium.lib"))
    guard.attribute(_LLC_CONFTEST)

    assert _leaks_for(guard, _OTHER_MODULE) == []


def test_a_cffi_pseudo_module_is_not_a_stub(guard):
    """``_openssl`` is specless, loaderless and fileless — and not a stub.

    Nothing named ``_openssl`` exists on ``sys.path``, so it shadows nothing
    and reporting it would be pure noise.
    """
    _install("_openssl", types.ModuleType("_openssl"))
    guard.attribute(_LLC_CONFTEST)

    assert _leaks_for(guard, _OTHER_MODULE) == []


def test_a_synthetic_child_of_a_real_package_is_still_a_stub(guard):
    """Stubbing one submodule of real code is a leak like any other."""
    parent = types.ModuleType("knowledge")
    parent.__spec__ = object()  # type: ignore[assignment]
    _install("knowledge", parent)
    guard.snapshot()
    _install("knowledge.utils", types.ModuleType("knowledge.utils"))
    guard.attribute(_LLC_CONFTEST)

    assert _leaks_for(guard, _OTHER_MODULE) == ["knowledge.utils"]


def test_a_restored_stub_stops_being_reported(guard):
    """Once the owner puts the real module back there is nothing to report."""
    _install("agents", types.ModuleType("agents"))
    guard.attribute(_LLC_CONFTEST)
    del sys.modules["agents"]

    assert _leaks_for(guard, _OTHER_MODULE) == []


class _MutatingModules(dict):
    """A ``sys.modules`` stand-in that grows while its live view is iterated.

    Reproduces deterministically what a background thread importing during a
    snapshot does: iterating the live view and inserting mid-way is exactly the
    condition CPython raises ``RuntimeError: dictionary changed size during
    iteration`` on.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.counter = 0

    def items(self):
        for index, pair in enumerate(super().items()):
            if index == 1:
                self.counter += 1
                super().__setitem__(f"late_import_{self.counter}", types.ModuleType("late"))
            yield pair


def _mutating_modules() -> _MutatingModules:
    return _MutatingModules({f"mod_{n}": types.ModuleType(f"mod_{n}") for n in range(6)})


def test_the_mutating_stand_in_really_reproduces_the_race():
    """Control: iterating this stand-in's live view must raise, or the next test proves nothing."""
    with pytest.raises(RuntimeError, match="changed size during iteration"):
        list(_mutating_modules().items())


def test_snapshotting_survives_a_concurrent_import(monkeypatch):
    """``snapshot``/``attribute`` must copy ``sys.modules`` before iterating.

    Iterating a live ``sys.modules`` view races with any import on another
    thread — the suite's analytics and celery task tests spawn them — and the
    loser gets ``RuntimeError`` raised inside a pytest hook.  Under xdist that
    kills the worker and takes the whole session down with ``INTERNALERROR``:
    observed as ``1 failed, 224 passed`` plus ``INTERNALERROR`` where the same
    run without the guard gives ``1 failed, 255 passed``.
    """
    mutating = _mutating_modules()
    monkeypatch.setattr(sys, "modules", mutating)

    instance = _LeakGuard(_ROOT)
    instance.snapshot()
    instance.attribute(_LLC_CONFTEST)


def test_each_leak_is_reported_once_not_once_per_test(guard):
    """Thousands of duplicate lines would bury the finding."""
    _install("agents", types.ModuleType("agents"))
    guard.attribute(_LLC_CONFTEST)

    _leaks_for(guard, _OTHER_MODULE)
    _leaks_for(guard, _OTHER_MODULE.parent / "another_test.py")

    assert [leak.mutation.key for leak in guard.leaks] == ["agents"]


# ---------------------------------------------------------------------------
# The baseline ratchet: who may be asked to leave the list (#13398)
# ---------------------------------------------------------------------------


def test_a_listed_owner_taken_outside_its_directory_counts_as_exercised(make_guard):
    """The evidence "this owner no longer leaks" is only collected here.

    The conftest is loaded and installs nothing, and the session then imports a
    sibling — the moment a stub would have been caught if there had been one.
    """
    guard = make_guard(frozenset({_LLC_OWNER}))
    guard.attribute(_LLC_CONFTEST)

    _leaks_for(guard, _OTHER_MODULE)

    assert guard.exercised_owners() == {_LLC_OWNER}


def test_a_listed_owner_is_not_exercised_by_its_own_subtree(make_guard):
    """``pytest backend/llc/tests`` proves nothing about that directory's stubs."""
    guard = make_guard(frozenset({_LLC_OWNER}))
    guard.attribute(_LLC_CONFTEST)

    _leaks_for(guard, _LLC_CONFTEST.parent / "test_something.py")

    assert guard.exercised_owners() == set()


def test_a_listed_owner_is_not_exercised_by_an_ancestor_directory(make_guard):
    """A ``Dir`` collector above the owner imports nothing, so it sees nothing.

    Pytest builds one for every level down to the rootdir on every session,
    which would otherwise make every run claim every entry was removable.
    """
    guard = make_guard(frozenset({_LLC_OWNER}))
    guard.attribute(_LLC_CONFTEST)

    _leaks_for(guard, _ROOT)

    assert guard.exercised_owners() == set()


def test_an_owner_the_session_never_loaded_is_not_exercised(make_guard):
    """``pytest repo_tests`` must conclude nothing about a backend conftest."""
    guard = make_guard(frozenset({_LLC_OWNER}))

    _leaks_for(guard, _OTHER_MODULE)

    assert guard.exercised_owners() == set()


def test_an_owner_that_is_not_listed_is_never_tracked_for_removal(make_guard):
    """Only listed owners are watched — the rest are judged on their leaks."""
    guard = make_guard(frozenset({"backend/other/conftest.py"}))
    guard.attribute(_LLC_CONFTEST)

    _leaks_for(guard, _OTHER_MODULE)

    assert guard.exercised_owners() == set()


def test_a_still_leaking_listed_owner_is_exercised_and_reported(make_guard):
    """Both signals fire; it is the verdict's subtraction that keeps it listed."""
    guard = make_guard(frozenset({_LLC_OWNER}))
    _install("agents", types.ModuleType("agents"))
    guard.attribute(_LLC_CONFTEST)

    assert _leaks_for(guard, _OTHER_MODULE) == ["agents"]
    assert guard.exercised_owners() == {_LLC_OWNER}


# ---------------------------------------------------------------------------
# Reading the file, and turning findings into a verdict
# ---------------------------------------------------------------------------


def test_the_baseline_file_ignores_comments_and_blank_lines(tmp_path):
    """The file carries its own instructions, so comments have to be free."""
    path = tmp_path / "baseline.txt"
    path.write_text("# header\n\nbackend/conftest.py\n  backend/x/conftest.py  \n", encoding="utf-8")

    baseline = _load_baseline(path)

    assert baseline.owners == frozenset({"backend/conftest.py", "backend/x/conftest.py"})
    assert baseline.removal_checked == baseline.owners


def test_a_run_phase_entry_is_listed_but_never_checked_for_removal(tmp_path):
    """It still cannot fail as new; it just cannot be delisted by a shard."""
    path = tmp_path / "baseline.txt"
    path.write_text("backend/a_test.py run-phase\nbackend/b_test.py\n", encoding="utf-8")

    baseline = _load_baseline(path)

    assert baseline.owners == frozenset({"backend/a_test.py", "backend/b_test.py"})
    assert baseline.removal_checked == frozenset({"backend/b_test.py"})


def test_a_missing_baseline_file_allows_nothing(tmp_path):
    """A deleted or mistyped path must not quietly turn the gate into an allowlist."""
    baseline = _load_baseline(tmp_path / "nope.txt")

    assert baseline == _Baseline(frozenset(), frozenset())


def _verdict_over(monkeypatch, listed, *, checked=None, leaking=(), exercised=()):
    """Drive ``_verdict`` with worker-shaped input and no live guard."""
    checked = listed if checked is None else checked
    monkeypatch.setattr(guard_module, "_GUARD", None)
    monkeypatch.setattr(guard_module, "_BASELINE", _Baseline(frozenset(listed), frozenset(checked)))
    monkeypatch.setattr(guard_module, "_WORKER_RECORDS", [{"owner": owner} for owner in leaking])
    monkeypatch.setattr(guard_module, "_WORKER_EXERCISED", set(exercised))
    return guard_module._verdict()


def test_an_unlisted_leak_is_a_regression(monkeypatch):
    """The transition the previous report/error pair could not gate at all."""
    verdict = _verdict_over(monkeypatch, listed={"a/conftest.py"}, leaking=("b/conftest.py",))

    assert verdict.new_owners == ["b/conftest.py"]
    assert verdict.failed


def test_a_listed_leak_is_known_debt(monkeypatch):
    """#13361's owners keep the suite green while they are worked through."""
    verdict = _verdict_over(monkeypatch, listed={"a/conftest.py"}, leaking=("a/conftest.py",))

    assert verdict.known_owners == ["a/conftest.py"]
    assert not verdict.failed


def test_a_listed_owner_that_was_exercised_and_stayed_silent_must_be_delisted(monkeypatch):
    """Shrink-only: the fix and the deletion land together or not at all."""
    verdict = _verdict_over(monkeypatch, listed={"a/conftest.py"}, exercised=("a/conftest.py",))

    assert verdict.fixed_owners == ["a/conftest.py"]
    assert verdict.failed


def test_one_worker_meeting_the_stub_keeps_the_entry_for_every_other(monkeypatch):
    """The xdist shape: exercised in one worker, caught leaking in another.

    Each worker only sees its own share of the nodes, so a worker that met no
    stub proves nothing on its own.  Deciding per worker would have deleted
    entries that are still leaking — and under ``--dist loadscope``, which is
    the only shape CI runs, there is always more than one.
    """
    verdict = _verdict_over(
        monkeypatch,
        listed={"a/conftest.py"},
        leaking=("a/conftest.py",),
        exercised=("a/conftest.py",),
    )

    assert verdict.fixed_owners == []
    assert verdict.known_owners == ["a/conftest.py"]
    assert not verdict.failed


def test_a_run_phase_entry_is_exempt_from_the_removal_check(monkeypatch):
    """Eleven of twelve CI shards never run such a module — silence means nothing."""
    verdict = _verdict_over(
        monkeypatch,
        listed={"a_test.py"},
        checked=set(),
        exercised=("a_test.py",),
    )

    assert verdict.fixed_owners == []
    assert not verdict.failed
