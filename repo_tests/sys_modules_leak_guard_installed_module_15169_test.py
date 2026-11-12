# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The leak guard tells a package's own spec-less module from a stub a test built (#15169).

Split from ``sys_modules_leak_guard_test.py``, which sits at the file-size ceiling.  The
happy path is a ``ModuleType`` subclass defined by an installed file (``kombu``'s shape); the
controls are the stub shapes that must stay reported.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import warnings
from pathlib import Path

import pytest
from repo_tests.sys_modules_leak_guard import _DISK_CACHE, _LeakGuard

_ROOT = Path("/repo")
_LLC_CONFTEST = _ROOT / "backend" / "llc" / "tests" / "conftest.py"
_OTHER_MODULE = _ROOT / "backend" / "initialization" / "lifespan_test.py"


@pytest.fixture
def make_guard(monkeypatch):
    """Build guards over an isolated ``sys.modules`` copy, with ``knowledge`` known to exist on disk."""
    monkeypatch.setattr(sys, "modules", dict(sys.modules))
    monkeypatch.setattr("repo_tests.sys_modules_leak_guard._DISK_CACHE", dict(_DISK_CACHE, knowledge=True))

    def build(root: Path = _ROOT) -> _LeakGuard:
        instance = _LeakGuard(root)
        instance.snapshot()
        return instance

    return build


@pytest.fixture
def guard(make_guard):
    return make_guard()


def _install(name: str, module: object) -> None:
    sys.modules[name] = module  # type: ignore[assignment]


def _leaks_for(guard: _LeakGuard, path: Path) -> list[str]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        guard.check(path, f"the import of {path.name}")
    return [leak.mutation.key for leak in guard.leaks]


def _lazy_class(where: Path, owner_name: str) -> type:
    """A ``ModuleType`` subclass defined by a real file at *where*, loaded the way the import system would."""
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text("import types\n\n\nclass LazyModule(types.ModuleType):\n    pass\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location(owner_name, where)
    owner = importlib.util.module_from_spec(spec)
    sys.modules[owner_name] = owner
    spec.loader.exec_module(owner)
    return owner.LazyModule


def _file_in(directory: Path) -> str:
    """A ``__file__`` value naming a file that exists under *directory*."""
    target = directory / "knowledge" / "__init__.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    return str(target)


def _report_new(guard: _LeakGuard, module: types.ModuleType) -> list[str]:
    _install("knowledge", module)
    guard.attribute(_LLC_CONFTEST)
    return _leaks_for(guard, _OTHER_MODULE)


def test_a_spec_less_subclass_defined_by_installed_code_is_not_a_stub_15169(guard, tmp_path):
    """``kombu`` swaps in an instance of a ``ModuleType`` subclass it defines; that is not a stub.

    Fails on the unguarded classifier (the module is spec-less and new, so it is reported).
    """
    lazy = _lazy_class(tmp_path / "site-packages" / "lazy_owner" / "__init__.py", "lazy_owner_15169")("knowledge")
    lazy.__file__ = _file_in(tmp_path / "site-packages")

    assert _report_new(guard, lazy) == []


def test_a_plain_module_type_naming_an_existing_outside_file_is_still_a_stub_15169(guard):
    """Control: ``os.__file__`` exists outside the repo, and a plain ``ModuleType`` is what a test builds.

    Fails on the first fix (spec-less + third-party file + real file), which exempted it.
    """
    stub = types.ModuleType("knowledge")
    stub.__file__ = os.__file__

    assert _report_new(guard, stub) == ["knowledge"]


def test_a_plain_module_type_copying_an_installed_packages_file_is_still_a_stub_15169(guard):
    """Control: copying a real package's ``__file__`` onto a fake is the classic shadowing idiom.

    Fails on the first fix, for the same reason as the control above.
    """
    stub = types.ModuleType("knowledge")
    stub.__file__ = pytest.__file__

    assert _report_new(guard, stub) == ["knowledge"]


def test_a_subclass_defined_inside_the_repo_is_still_a_stub_15169(make_guard, tmp_path):
    """Control: a test's own ``ModuleType`` subclass is repo code even when it points at an outside file.

    Fails on the first fix, and on any rule that checks only the instance's ``__file__`` and its type.
    """
    repo = tmp_path / "repo"
    cls = _lazy_class(repo / "stubs" / "lazy_stub.py", "lazy_stub_15169")
    stub = cls("knowledge")
    stub.__file__ = _file_in(tmp_path / "site-packages")
    guard = make_guard(repo)

    assert _report_new(guard, stub) == ["knowledge"]


def test_a_subclass_of_installed_code_naming_a_missing_file_is_still_a_stub_15169(guard, tmp_path):
    """Control: the instance's file must exist, whoever defined its class."""
    stub = _lazy_class(tmp_path / "site-packages" / "lazy_owner" / "__init__.py", "lazy_owner_15169")("knowledge")
    stub.__file__ = str(tmp_path / "site-packages" / "knowledge" / "__init__.py")

    assert _report_new(guard, stub) == ["knowledge"]
