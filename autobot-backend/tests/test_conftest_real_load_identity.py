# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`_real_load_and_bind` must never duplicate an already-real module (#12839).

Re-executing a module that is already loaded builds a *second* set of class
objects and swaps them into ``sys.modules``, while every module that imported
the first set keeps referencing it. The result is the confusing failure this
test exists to prevent:

    assert isinstance(result, Claim)
    E   AssertionError: assert False
    E    +  where False = isinstance(Claim(claim_text=...), Claim)

— an object whose repr says it IS a Claim, rejected by isinstance, because the
two Claim classes come from two executions of the same file.
"""

import sys

import pytest


@pytest.fixture
def loader():
    """The real helper from the backend root conftest.

    Loaded by path rather than ``import conftest``: pytest imports conftest
    files under its own machinery, so a plain import can resolve to a different
    conftest (or none) depending on rootdir.
    """
    import importlib.util
    import sys as _sys
    from pathlib import Path

    conftest_path = Path(__file__).parent.parent / "conftest.py"
    mod = _sys.modules.get("_conftest_under_test")
    if mod is None:
        spec = importlib.util.spec_from_file_location("_conftest_under_test", conftest_path)
        mod = importlib.util.module_from_spec(spec)
        _sys.modules["_conftest_under_test"] = mod
        spec.loader.exec_module(mod)
    return mod._real_load_and_bind


def test_already_real_module_is_not_re_executed(loader, tmp_path):
    """A second call must return the SAME module object, not a fresh execution."""
    mod_file = tmp_path / "identity_probe.py"
    mod_file.write_text("class Marker:\n    pass\n", encoding="utf-8")

    loader("identity_probe_mod", mod_file)
    first = sys.modules["identity_probe_mod"]
    first_marker = first.Marker

    loader("identity_probe_mod", mod_file)
    second = sys.modules["identity_probe_mod"]

    try:
        assert second is first, "module was re-executed and replaced"
        assert (
            second.Marker is first_marker
        ), "class object was rebuilt — isinstance() against the original would now fail"
    finally:
        sys.modules.pop("identity_probe_mod", None)


def test_isinstance_survives_a_repeat_load(loader, tmp_path):
    """The concrete symptom: an instance made before the second load stays valid."""
    mod_file = tmp_path / "iso_probe.py"
    mod_file.write_text("class Thing:\n    pass\n", encoding="utf-8")

    loader("iso_probe_mod", mod_file)
    instance = sys.modules["iso_probe_mod"].Thing()

    loader("iso_probe_mod", mod_file)
    Thing = sys.modules["iso_probe_mod"].Thing

    try:
        assert isinstance(instance, Thing)
    finally:
        sys.modules.pop("iso_probe_mod", None)


def test_a_stub_is_still_replaced_by_the_real_module(loader, tmp_path):
    """The guard must not defeat the loader's actual purpose.

    Replacing a MagicMock package stub with the real module is why this helper
    exists (#11532/#11618); only an already-*real* module is skipped.
    """
    from unittest.mock import MagicMock

    mod_file = tmp_path / "stubbed_probe.py"
    mod_file.write_text("REAL = True\n", encoding="utf-8")

    sys.modules["stubbed_probe_mod"] = MagicMock()
    loader("stubbed_probe_mod", mod_file)

    try:
        assert getattr(sys.modules["stubbed_probe_mod"], "REAL", None) is True
    finally:
        sys.modules.pop("stubbed_probe_mod", None)


def test_parent_bind_is_applied_on_the_skip_path(loader, tmp_path):
    """patch("pkg.mod.NAME") resolves via getattr(pkg, "mod") — the bind is load-bearing.

    Skipping re-execution must not skip the bind, or patch() would silently
    patch a mock instead of the real module (#11532).
    """
    from types import ModuleType

    pkg = ModuleType("bindpkg_probe")
    sys.modules["bindpkg_probe"] = pkg

    mod_file = tmp_path / "child.py"
    mod_file.write_text("VALUE = 1\n", encoding="utf-8")

    loader("bindpkg_probe.child", mod_file)
    delattr(pkg, "child")  # simulate a stub clobbering the attribute
    loader("bindpkg_probe.child", mod_file)  # skip path — must re-bind anyway

    try:
        assert getattr(pkg, "child", None) is sys.modules["bindpkg_probe.child"]
    finally:
        sys.modules.pop("bindpkg_probe.child", None)
        sys.modules.pop("bindpkg_probe", None)
