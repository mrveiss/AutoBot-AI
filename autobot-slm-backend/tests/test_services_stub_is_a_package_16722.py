# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Collecting a test inside ``services/`` keeps the conftest's ``services`` stub (#16722).

In importlib mode, pytest imports a test module's parent package first, and re-imports it
from disk whenever the object in ``sys.modules`` has no ``__path__``
(``_pytest.pathlib._import_module_using_spec``). A bare MagicMock stub has none, so
collecting any test module under ``autobot-slm-backend/services/`` ran the real
``services/__init__.py`` over the stub. The sys.modules leak guard then blamed whichever
such test was collected first: a CI shard's alphabetically first file, which sits on the
baseline, or, under pre-push's two-file selection, a file that doesn't.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

from _pytest.pathlib import ImportMode, import_path

_SLM_ROOT = Path(__file__).resolve().parents[1]


def test_the_services_stub_is_a_package_pointing_at_the_real_directory():
    stub = sys.modules["services"]
    assert isinstance(stub, MagicMock), "the real services package replaced the conftest stub"
    assert stub.__path__ == [str(_SLM_ROOT / "services")]


def test_pytest_sets_up_the_services_package_with_the_stub_in_place(pytestconfig):
    """Package.setup imports services/__init__.py through importtestmodule.

    importlib mode returns the stub already in sys.modules, and pytest then reads
    pytest_plugins and the xunit module hooks off it. On a bare MagicMock, the invented
    pytest_plugins was a UsageError: #16728's first CI run, on services/slm_unit_refresh_test.py.
    """
    from _pytest.python import importtestmodule

    stub = sys.modules["services"]
    assert importtestmodule(_SLM_ROOT / "services" / "__init__.py", pytestconfig) is stub
    for hook in ("setUpModule", "setup_module", "tearDownModule", "teardown_module"):
        assert getattr(stub, hook) is None, hook


def _import_inner_test(tmp_path: Path, stub: MagicMock) -> object:
    """Have pytest import ``<pkg>/inner_test.py`` with *stub* as the parent; returns the parent after."""
    pkg = tmp_path / "stubbed_pkg_16722"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("MARK = 'real package ran'\n", encoding="utf-8")
    (pkg / "inner_test.py").write_text("VALUE = 1\n", encoding="utf-8")
    ours = [k for k in sys.modules if k == pkg.name or k.startswith(pkg.name + ".")]
    assert not ours, ours
    sys.modules[pkg.name] = stub
    try:
        module = import_path(
            pkg / "inner_test.py", mode=ImportMode.importlib, root=tmp_path, consider_namespace_packages=False
        )
        assert module.VALUE == 1
        return sys.modules[pkg.name]
    finally:
        for key in [k for k in sys.modules if k == pkg.name or k.startswith(pkg.name + ".")]:
            del sys.modules[key]


def test_pytest_keeps_a_package_stub_that_has_a_path(tmp_path):
    """The fix's premise, pinned against pytest itself on a scratch package."""
    stub = MagicMock()
    stub.__path__ = [str(tmp_path / "stubbed_pkg_16722")]
    assert _import_inner_test(tmp_path, stub) is stub


def test_pytest_replaces_a_package_stub_without_a_path(tmp_path):
    """The mechanism #16722 hit. If pytest stops doing this, the fix above is no longer needed."""
    stub = MagicMock()
    parent = _import_inner_test(tmp_path, stub)
    assert parent is not stub and parent.MARK == "real package ran"
