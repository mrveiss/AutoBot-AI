# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit cover for the repo-wide sys.modules leak guard (#13337).

The guard's whole value is that it fires on a real leak and stays silent on
everything else, so both halves are pinned here.  The classifier and the
escape rule are exercised directly against a throwaway ``sys.modules`` — no
nested pytest session, so every test finishes in milliseconds.
"""

from __future__ import annotations

import sys
import types
import warnings
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from repo_tests.sys_modules_leak_guard import _DISK_CACHE, _LeakGuard

_ROOT = Path("/repo")
_LLC_CONFTEST = _ROOT / "backend" / "llc" / "tests" / "conftest.py"
_OTHER_MODULE = _ROOT / "backend" / "initialization" / "lifespan_test.py"


@pytest.fixture
def guard(monkeypatch):
    """A guard over an isolated ``sys.modules`` copy.

    ``_DISK_CACHE`` is pre-seeded so the tests never depend on what happens to
    be installed on the machine running them.
    """
    monkeypatch.setattr(sys, "modules", dict(sys.modules))
    monkeypatch.setattr(
        "repo_tests.sys_modules_leak_guard._DISK_CACHE",
        dict(_DISK_CACHE, agents=True, autobot_shared=True, celery=True, knowledge=True, _sodium=False),
    )
    instance = _LeakGuard(_ROOT)
    instance.snapshot()
    return instance


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
