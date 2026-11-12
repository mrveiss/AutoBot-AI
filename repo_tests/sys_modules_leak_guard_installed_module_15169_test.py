# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The leak guard tells a package's own spec-less module from a stub a test built (#15169).

Split from ``sys_modules_leak_guard_test.py``, which sits at the file-size ceiling.  The happy
path is ``kombu``'s shape: an instance of a ``ModuleType`` subclass whose code lives in an
installed file and whose ``__module__`` is its own name.  The rest are stub shapes that must stay
reported.  Each says which earlier rule it fails on: *any-outside-file* (exempt a spec-less module
whose ``__file__`` exists outside the repo) and *owner-lookup* (trust ``type(m).__module__``).
"""

from __future__ import annotations

import importlib.util
import os
import types
from pathlib import Path

import pytest
from repo_tests._sys_modules_leak_guard_support import (
    LLC_CONFTEST,
    OTHER_MODULE,
    fresh_guard,
    guard_factory,
    install_module,
    leaks_for,
)

make_guard = pytest.fixture(guard_factory, name="make_guard")
guard = pytest.fixture(fresh_guard, name="guard")

_CLASS_SOURCE = """import types


class LazyModule(types.ModuleType):
    def __dir__(self):
        return []
"""


def _lazy_class(where: Path, owner_name: str) -> type:
    """A ``ModuleType`` subclass defined by a real file at *where*, whose ``__module__`` is *owner_name*."""
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(_CLASS_SOURCE, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(owner_name, where)
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    return owner.LazyModule


def _installed_class(tmp_path: Path, owner_name: str) -> type:
    return _lazy_class(tmp_path / "site-packages" / owner_name / "__init__.py", owner_name)


def _file_in(directory: Path) -> str:
    """A ``__file__`` value naming a file that exists under *directory*."""
    target = directory / "knowledge" / "__init__.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    return str(target)


def _report_new(guard, module: types.ModuleType) -> list[str]:
    install_module("knowledge", module)
    guard.attribute(LLC_CONFTEST)
    return leaks_for(guard, OTHER_MODULE)


def test_an_installed_packages_own_lazy_module_is_not_a_stub_15169(guard, tmp_path):
    """The kombu shape: installed class, ``__module__`` == ``__name__`` == key, real installed file.

    Fails on main (no rule).
    """
    lazy = _installed_class(tmp_path, "knowledge")("knowledge")
    lazy.__file__ = _file_in(tmp_path / "site-packages")

    assert _report_new(guard, lazy) == []


def test_a_plain_module_type_naming_an_existing_outside_file_is_still_a_stub_15169(guard):
    """``os.__file__`` exists outside the repo; a plain ``ModuleType`` is what a test builds.

    Fails on any-outside-file.
    """
    stub = types.ModuleType("knowledge")
    stub.__file__ = os.__file__

    assert _report_new(guard, stub) == ["knowledge"]


def test_a_plain_module_type_copying_an_installed_packages_file_is_still_a_stub_15169(guard):
    """Copying a real package's ``__file__`` onto a fake is the classic shadowing idiom.

    Fails on any-outside-file.
    """
    stub = types.ModuleType("knowledge")
    stub.__file__ = pytest.__file__

    assert _report_new(guard, stub) == ["knowledge"]


def test_a_subclass_defined_inside_the_repo_is_still_a_stub_15169(make_guard, tmp_path):
    """A test's own ``ModuleType`` subclass is repo code even when it points at an outside file.

    Fails on any-outside-file.
    """
    repo = tmp_path / "repo"
    stub = _lazy_class(repo / "stubs" / "lazy_stub.py", "lazy_stub_15169")("knowledge")
    stub.__file__ = _file_in(tmp_path / "site-packages")

    assert _report_new(make_guard(root=repo), stub) == ["knowledge"]


def test_a_repo_subclass_claiming_the_packages_module_name_is_still_a_stub_15169(make_guard, tmp_path):
    """``__module__`` is an assignable string; the class's code files are not.

    Fails on owner-lookup, which resolved the claimed name to the registered module itself.
    """
    repo = tmp_path / "repo"
    cls = _lazy_class(repo / "stubs" / "lazy_stub.py", "lazy_stub_15169")
    cls.__module__ = "knowledge"
    stub = cls("knowledge")
    stub.__file__ = _file_in(tmp_path / "site-packages")

    assert _report_new(make_guard(root=repo), stub) == ["knowledge"]


def test_an_installed_class_instantiated_under_another_name_is_still_a_stub_15169(guard, tmp_path):
    """Importing the real class and building a module for a different key is a stub.

    Fails on any-outside-file and on owner-lookup.
    """
    stub = _installed_class(tmp_path, "lazy_owner_15169")("knowledge")
    stub.__file__ = _file_in(tmp_path / "site-packages")

    assert _report_new(guard, stub) == ["knowledge"]


def test_an_installed_subclass_naming_a_missing_file_is_still_a_stub_15169(guard, tmp_path):
    """The instance's file must exist, whoever defined its class. Pins ``_has_real_file``; fails on neither."""
    stub = _installed_class(tmp_path, "knowledge")("knowledge")
    stub.__file__ = str(tmp_path / "site-packages" / "elsewhere" / "__init__.py")

    assert _report_new(guard, stub) == ["knowledge"]


def test_a_repo_subclass_borrowing_an_installed_function_is_still_a_stub_15169(make_guard, tmp_path):
    """A function assigned into the class keeps the donor's ``__module__`` (and its own qualname), so it is not the class's.

    Fails on the code-filename-only rule, which accepted a class whose every function is installed code.
    """
    repo = tmp_path / "repo"
    donor = _installed_class(tmp_path, "donor_15169").__dir__
    cls = _lazy_class(repo / "stubs" / "lazy_stub.py", "knowledge")
    cls.__dir__ = donor
    stub = cls("knowledge")
    stub.__file__ = _file_in(tmp_path / "site-packages")

    assert _report_new(make_guard(root=repo), stub) == ["knowledge"]
