# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for testkit.module_stubs (#13451).

Each test pins one of the five rules the helper exists to enforce, and each rule
came from a defect during the #13162 campaign. The rule numbers match the
module docstring.

Run: python3 -m pytest autobot-backend/testkit/module_stubs_test.py
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from testkit.module_stubs import StubSet

_REAL_DIR = Path(__file__).resolve().parent


@pytest.fixture
def clean_modules():
    """Remove the scratch names before and after, so tests cannot leak into each other."""
    names = ["scratchpkg", "scratchpkg.child", "scratchpkg.leaf"]
    saved = {n: sys.modules[n] for n in names if n in sys.modules}
    for n in names:
        sys.modules.pop(n, None)
    yield names
    for n in names:
        sys.modules.pop(n, None)
    sys.modules.update(saved)


# ------------------------------------------------------- rule 1: real __path__


def test_installed_package_keeps_a_real_path(clean_modules):
    stubs = StubSet()
    module = stubs.install_package("scratchpkg", _REAL_DIR)
    assert module.__path__ == [str(_REAL_DIR)], "an empty __path__ blocks every real submodule (#13383)"
    stubs.restore()


def test_a_real_submodule_imports_through_the_hollow_package(clean_modules, tmp_path):
    """The point of rule 1, asserted on behaviour rather than on __path__.

    The package's own __init__.py is bypassed — here it raises, to prove it was
    never executed — while a genuine sibling submodule still imports (#13383).
    """
    (tmp_path / "__init__.py").write_text("raise AssertionError('__init__ must be bypassed')\n", encoding="utf-8")
    (tmp_path / "leaf.py").write_text("VALUE = 'imported through the stub'\n", encoding="utf-8")

    stubs = StubSet()
    stubs.install_package("scratchpkg", tmp_path)
    leaf = importlib.import_module("scratchpkg.leaf")

    assert leaf.VALUE == "imported through the stub"
    stubs.restore()


# --------------------------------------- rule 2: never displace a real module


def test_refuses_to_displace_a_real_module():
    stubs = StubSet()
    with pytest.raises(RuntimeError, match="refusing to stub"):
        stubs.install_package("json", _REAL_DIR)


def test_a_module_level_getattr_shim_is_not_mistaken_for_a_real_module(clean_modules):
    """A PEP-562 module-level __getattr__ answers dunders too, so __file__ comes
    back a truthy MagicMock and a truthiness test would read the shim as real.

    A bare MagicMock is deliberately NOT the case under test: Mock.__getattr__
    rejects dunder names, so its __file__ is None and either check classifies it
    correctly. Only the module-level shim distinguishes the two.
    """
    placeholder = types.ModuleType("scratchpkg")
    placeholder.__getattr__ = lambda _name: MagicMock()  # type: ignore[attr-defined]
    assert getattr(placeholder, "__file__", None), "premise: the shim answers __file__ truthily"
    assert getattr(MagicMock(), "__file__", None) is None, "premise: a bare mock does not"
    sys.modules["scratchpkg"] = placeholder

    stubs = StubSet()
    stubs.install_package("scratchpkg", _REAL_DIR)  # must not raise
    assert sys.modules["scratchpkg"] is not placeholder
    stubs.restore()
    assert sys.modules["scratchpkg"] is placeholder


def test_reattach_refuses_to_displace_a_module_imported_while_detached(clean_modules, tmp_path):
    """Rule 2 enforced only in the safe window is rule 2 not enforced.

    install_package checks at conftest import, when nothing is imported yet.
    reattach runs after pytest has imported the whole session — it is the call
    that can actually find a real module in the slot, and overwriting it there
    would make restore() pop the real module for the rest of the process.
    """
    stubs = StubSet()
    stubs.install_package("scratchpkg", _REAL_DIR)
    stubs.detach()

    real = tmp_path / "scratchpkg.py"
    real.write_text("VALUE = 'the real one'\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("scratchpkg", str(real))
    genuine = importlib.util.module_from_spec(spec)
    sys.modules["scratchpkg"] = genuine
    spec.loader.exec_module(genuine)

    with pytest.raises(RuntimeError, match="refusing to stub"):
        stubs.reattach()
    assert sys.modules["scratchpkg"] is genuine, "the real module must survive"


def test_reattach_without_detach_is_refused(clean_modules):
    """A no-op reattach paired with a real teardown makes the stubs vanish after
    the first scope, silently. Better to say so than to half-work."""
    stubs = StubSet()
    stubs.install_package("scratchpkg", _REAL_DIR)
    with pytest.raises(RuntimeError, match="before detach"):
        stubs.reattach()
    stubs.restore()


def test_reinstall_after_detach_reuses_the_same_object(clean_modules):
    """reattach restores from _detached, so a second object built for the same
    name is silently discarded and anything patched onto it is never seen."""
    stubs = StubSet()
    first = stubs.install_package("scratchpkg", _REAL_DIR)
    stubs.detach()
    second = stubs.install_package("scratchpkg", _REAL_DIR)
    assert second is first
    second.marker = "patched by the caller"  # type: ignore[attr-defined]

    stubs.detach()
    stubs.reattach()
    assert getattr(sys.modules["scratchpkg"], "marker", None) == "patched by the caller"
    stubs.restore()


def test_real_load_leaves_nothing_behind_when_the_module_raises(clean_modules, tmp_path):
    """CPython removes a half-initialized module on import failure. A helper that
    leaves one behind is strictly worse than a plain import, and hands the leak
    guard a key nobody owns."""
    source = tmp_path / "boom.py"
    source.write_text("raise ValueError('boom')\n", encoding="utf-8")

    stubs = StubSet()
    stubs.install_package("scratchpkg", tmp_path)
    with pytest.raises(ValueError, match="boom"):
        stubs.real_load("scratchpkg.leaf", source)
    assert "scratchpkg.leaf" not in sys.modules
    stubs.restore()


# ----------------------------------------------- rule 3: bind on the parent


def test_child_is_bound_as_an_attribute_of_its_parent(clean_modules):
    """patch("pkg.mod.NAME") resolves via getattr, not a sys.modules lookup."""
    stubs = StubSet()
    parent = stubs.install_package("scratchpkg", _REAL_DIR)
    stubs.install_package("scratchpkg.child", _REAL_DIR)
    assert getattr(parent, "child", None) is sys.modules["scratchpkg.child"]
    stubs.restore()


# ------------------------------------------------ rule 4/5: lifecycle timing


def test_detach_removes_everything_then_reattach_restores_it(clean_modules):
    stubs = StubSet()
    stubs.install_package("scratchpkg", _REAL_DIR)
    stubs.install_package("scratchpkg.child", _REAL_DIR)

    stubs.detach()
    assert "scratchpkg" not in sys.modules
    assert "scratchpkg.child" not in sys.modules

    stubs.reattach()
    assert "scratchpkg" in sys.modules
    assert (
        getattr(sys.modules["scratchpkg"], "child", None) is sys.modules["scratchpkg.child"]
    ), "reattach must restore parent bindings, not just sys.modules entries"
    stubs.restore()


def test_reattach_installs_parents_before_children(clean_modules):
    """Reverse order silently skips the bind, surfacing later as AttributeError."""
    stubs = StubSet()
    stubs.install_package("scratchpkg", _REAL_DIR)
    stubs.install_package("scratchpkg.child", _REAL_DIR)
    stubs.detach()
    stubs.reattach()
    # The bug this pins: child reattached first finds no parent to bind on.
    assert hasattr(sys.modules["scratchpkg"], "child")
    stubs.restore()


def test_a_preexisting_key_is_never_absent(clean_modules):
    """The leak guard blames whichever file a key *appears* during, so a key that
    existed before must be swapped, not popped and re-added (#13361)."""
    original = types.ModuleType("scratchpkg")
    sys.modules["scratchpkg"] = original

    stubs = StubSet()
    stubs.install_package("scratchpkg", _REAL_DIR)
    stubs.detach()
    assert sys.modules.get("scratchpkg") is original, "detach must put the original back, not remove the key"
    stubs.restore()
    assert sys.modules.get("scratchpkg") is original


def test_restore_returns_sys_modules_to_its_prior_state(clean_modules):
    before = dict(sys.modules)
    stubs = StubSet()
    stubs.install_package("scratchpkg", _REAL_DIR)
    stubs.install_package("scratchpkg.child", _REAL_DIR)
    stubs.restore()
    assert "scratchpkg" not in sys.modules
    assert "scratchpkg.child" not in sys.modules
    assert set(sys.modules) == set(before)


# --------------------------------------------------------- rule 5: real_load


def test_real_load_executes_the_file_and_registers_it(clean_modules, tmp_path):
    source = tmp_path / "leaf.py"
    source.write_text("VALUE = 'loaded for real'\n", encoding="utf-8")

    stubs = StubSet()
    stubs.install_package("scratchpkg", tmp_path)
    module = stubs.real_load("scratchpkg.leaf", source)

    assert module is not None and module.VALUE == "loaded for real"
    assert sys.modules["scratchpkg.leaf"] is module
    assert getattr(sys.modules["scratchpkg"], "leaf", None) is module
    stubs.restore()
