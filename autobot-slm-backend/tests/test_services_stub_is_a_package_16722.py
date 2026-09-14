# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The slm conftest's ``services`` stub is a hollow package over the real directory (#16722).

In importlib mode, pytest imports a test module's parent package first, and re-imports it
from disk whenever the object in ``sys.modules`` has no ``__path__``
(``_pytest.pathlib._import_module_using_spec``). The stub used to be a bare MagicMock, so
collecting any test module under ``autobot-slm-backend/services/`` ran the real
``services/__init__.py`` over it, and the sys.modules leak guard blamed whichever such test
was collected first.

A MagicMock *given* a ``__path__`` fails differently, because it invents every attribute:
- pytest's ``Package.setup`` read a mock ``pytest_plugins``, which raised a UsageError;
- ``from services import x`` bound a mock instead of importing the real submodule.

A hollow ``types.ModuleType`` package has neither problem. Test modules under
``tests/services/`` install their own hollow package under the same key at import time, so
these tests check the shape that matters, not one object's identity.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

from _pytest.pathlib import ImportMode, import_path

_SLM_ROOT = Path(__file__).resolve().parents[1]


def test_services_is_a_hollow_package_over_the_real_directory():
    pkg = sys.modules["services"]
    assert isinstance(pkg, types.ModuleType) and not isinstance(pkg, MagicMock), type(pkg)
    assert [Path(p).resolve() for p in pkg.__path__] == [(_SLM_ROOT / "services").resolve()]
    assert not hasattr(pkg, "pytest_plugins")  # nothing invented for pytest to trip on


def test_from_services_import_loads_the_real_submodule():
    """A MagicMock parent answered this with an invented attribute, not the module."""
    from services import purge_playbook

    assert isinstance(purge_playbook, types.ModuleType) and not isinstance(purge_playbook, MagicMock)
    assert Path(purge_playbook.__file__).resolve() == (_SLM_ROOT / "services" / "purge_playbook.py").resolve()


def test_pytest_sets_up_the_services_package(pytestconfig):
    """Package.setup imports services/__init__.py via importtestmodule: #16728's first CI run failed here."""
    from _pytest.python import importtestmodule

    pkg = sys.modules["services"]
    assert importtestmodule(_SLM_ROOT / "services" / "__init__.py", pytestconfig) is pkg


def _import_inner_test(tmp_path: Path, parent: object) -> object:
    """Have pytest import ``<pkg>/inner_test.py`` with *parent* in sys.modules; returns the parent after."""
    pkg = tmp_path / "stubbed_pkg_16722"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("MARK = 'real package ran'\n", encoding="utf-8")
    (pkg / "inner_test.py").write_text("VALUE = 1\n", encoding="utf-8")
    ours = [k for k in sys.modules if k == pkg.name or k.startswith(pkg.name + ".")]
    assert not ours, ours
    sys.modules[pkg.name] = parent
    try:
        module = import_path(
            pkg / "inner_test.py", mode=ImportMode.importlib, root=tmp_path, consider_namespace_packages=False
        )
        assert module.VALUE == 1
        return sys.modules[pkg.name]
    finally:
        for key in [k for k in sys.modules if k == pkg.name or k.startswith(pkg.name + ".")]:
            del sys.modules[key]


def test_pytest_keeps_a_hollow_parent_package(tmp_path):
    """The fix's premise, pinned against pytest itself on a scratch package."""
    hollow = types.ModuleType("stubbed_pkg_16722")
    hollow.__path__ = [str(tmp_path / "stubbed_pkg_16722")]
    assert _import_inner_test(tmp_path, hollow) is hollow


def test_pytest_replaces_a_parent_stub_without_a_path(tmp_path):
    """The mechanism #16722 hit. If pytest stops doing this, the hollow package is no longer needed."""
    stub = MagicMock()
    parent = _import_inner_test(tmp_path, stub)
    assert parent is not stub and parent.MARK == "real package ran"
