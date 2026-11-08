# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Patching an attribute of a conftest module stub must leave that attribute usable (#19878).

pytest 9.2's ``monkeypatch.setattr`` records ``target.__dict__.get(name)`` as the old
value and undoes by deleting the name when that was absent. On a plain ``MagicMock``
stub that delete made the name raise ``AttributeError`` for the rest of the process
(``tests/_module_stub.py``). This guard fails if the conftest's stub factory goes back
to a plain ``MagicMock`` or if ``ModuleStub`` stops surviving a patch/undo.

It reads neither ``sys.modules`` at collection nor any live stub: other tests replace
stubs with real modules mid-run, so which stubs exist when this runs depends on order.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from _slm_module_stub import ModuleStub

_CONFTEST = Path(__file__).resolve().parent.parent / "conftest.py"
_PROBE = "slm_module_stub_probe_19878"
_ATTR = "attribute_patched_by_a_test_19878"


def _stub_factory_constructors() -> set[str]:
    """Names called inside the conftest's ``_stub`` function, e.g. ``{"ModuleStub", ...}``."""
    tree = ast.parse(_CONFTEST.read_text(encoding="utf-8"))
    factory = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_stub")
    return {c.func.id for c in ast.walk(factory) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}


def test_the_conftest_stub_factory_builds_module_stubs() -> None:
    called = _stub_factory_constructors()
    assert "ModuleStub" in called and "MagicMock" not in called, called


def test_a_module_stub_survives_monkeypatch_and_patch_undo(monkeypatch) -> None:
    stub = ModuleStub(unsafe=True)
    monkeypatch.setitem(sys.modules, _PROBE, stub)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(stub, _ATTR, lambda: "patched")
        assert getattr(stub, _ATTR)() == "patched"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(f"{_PROBE}.{_ATTR}", lambda: "by dotted path")  # the form that failed in CI
    with patch(f"{_PROBE}.{_ATTR}", return_value=1):
        assert getattr(stub, _ATTR)() == 1

    assert callable(getattr(stub, _ATTR))  # still auto-created on demand, not remembered as deleted


def test_a_plain_magicmock_is_the_contrast_that_breaks() -> None:
    """The control: a plain MagicMock really does lose the name after an undo, so the test above is not vacuous."""
    plain = MagicMock()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(plain, _ATTR, lambda: "patched")
    if hasattr(plain, _ATTR):
        pytest.skip("this pytest restores MagicMock children; the 9.2 undo path is not in play")
    with pytest.raises(AttributeError):
        getattr(plain, _ATTR)
