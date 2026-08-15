# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Co-located ``services/*_test.py`` must not depend on collection order (#14307).

The root conftest stubs ``services`` as a MagicMock so the ``api/*`` tests
import without heavy dependencies. Four test modules live *inside*
``services/`` and import real submodules; nothing arranged that for them. They
passed only when something under ``tests/services/`` — whose conftest swaps the
stub for a hollow package — happened to be collected first **in the same
process**, which pytest-split decides by shard composition.

So adding or removing an unrelated test file anywhere in the repo could move
them into a shard where ``services`` is still a MagicMock, and every
``from services.x import y`` silently yielded a mock:

    AssertionError: assert 'mynode-42' in <MagicMock name=
    'mock.inventory_builder.build_registry_inventory()...'>

— an assertion failure in a file the change never touched.

The fix follows the pattern already in the conftest for ``ssh_utils`` (#11793)
and ``deploy_artifacts`` (#14231): load the module from its file spec and bind
it onto the parent stub. These tests check that the list stays honest, because
its whole value is being complete.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_DIR = _BACKEND_ROOT / "services"


def _declared_real_modules() -> tuple[str, ...]:
    """``_REAL_SERVICE_MODULES`` as the conftest declares it.

    Read from source rather than imported: importing the conftest a second time
    would re-run its global stub installation.
    """
    tree = ast.parse((_BACKEND_ROOT / "conftest.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "_REAL_SERVICE_MODULES":
            return tuple(ast.literal_eval(node.value))
    raise AssertionError("_REAL_SERVICE_MODULES not found in conftest.py")


def _colocated_test_subjects() -> set[str]:
    """Modules a ``services/*_test.py`` imports, in any of the three forms.

    Review finding: matching only ``from services.X import Y`` meant a future
    test written as ``import services.foo`` or ``from services import foo``
    would never enter this set, so the rule below would pass over it — the
    exact silence this file exists to prevent.
    """
    subjects: set[str] = set()
    for test_file in _SERVICES_DIR.glob("*_test.py"):
        tree = ast.parse(test_file.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            # `from services.X import Y`
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("services."):
                subjects.add(node.module.split(".", 1)[1])
            # `from services import X` — the submodule is the imported name
            elif isinstance(node, ast.ImportFrom) and node.module == "services":
                subjects.update(alias.name for alias in node.names)
            # `import services.X`
            elif isinstance(node, ast.Import):
                subjects.update(
                    alias.name.split(".", 1)[1] for alias in node.names if alias.name.startswith("services.")
                )
    return subjects


def test_the_scan_finds_the_colocated_tests():
    """An empty scan reads exactly like a clean one."""
    assert _colocated_test_subjects(), "no co-located services test imports services.* — the scan is broken"


def test_every_colocated_subject_is_loaded_for_real():
    """The rule, not the four instances.

    A fifth co-located test added tomorrow, importing a fifth real submodule,
    fails here rather than passing until the shards happen to shift.
    """
    declared = set(_declared_real_modules())
    missing = _colocated_test_subjects() - declared

    assert not missing, (
        "co-located tests import these, but conftest does not real-load them, so they "
        f"resolve to MagicMocks depending on shard order: {sorted(missing)}"
    )


@pytest.mark.parametrize("name", _declared_real_modules())
def test_each_declared_module_exists(name):
    """A name that no longer matches a file exempts nothing, silently.

    The conftest raises on a missing file at import time; this states the same
    rule as a test so the failure names the entry rather than aborting
    collection for the whole directory.
    """
    assert (_SERVICES_DIR / f"{name}.py").is_file(), f"_REAL_SERVICE_MODULES names services/{name}.py, which is gone"


@pytest.mark.parametrize("name", _declared_real_modules())
def test_each_declared_module_is_actually_real_in_this_process(name):
    """The point of the whole change, asserted on the object.

    Reading the conftest's source proves it *intends* to load the module. This
    proves it did — a MagicMock here is the bug, and it is the one thing the
    structural rules above cannot see.
    """
    module = sys.modules.get(f"services.{name}")

    assert module is not None, f"services.{name} was never loaded"
    assert type(module).__name__ == "module", f"services.{name} is a {type(module).__name__}, not a real module"
    assert getattr(module, "__file__", None), f"services.{name} has no __file__ — it is not the real module"


def test_the_parent_never_exposes_a_different_object_than_sys_modules():
    """``patch("services.x.Y")`` and ``from services.x import Y`` must agree.

    #9780: a child bound on the parent that is *not* the object in
    ``sys.modules`` makes those two resolve differently, and a patch then
    affects neither the code under test nor the assertion.

    Asserted as "never disagrees" rather than "is always present". Two
    conftests legitimately swap ``sys.modules["services"]`` — the root one
    installs a stub, ``tests/services/conftest.py`` replaces it with a hollow
    package — so whether a given attribute survives depends on which ran last
    in this shard. That ordering is not what #9780 is about, and requiring
    presence made this test fail in a shard where nothing was actually wrong.
    A *divergent* binding is always a bug, whatever the order.
    """
    parent = sys.modules.get("services")
    assert parent is not None

    checked = 0
    for name in _declared_real_modules():
        bound = getattr(parent, name, None)
        if bound is None:
            continue
        assert bound is sys.modules[f"services.{name}"], (
            f"services.{name} is bound on the parent as a different object than sys.modules holds — "
            "patch() and import would resolve to different modules (#9780)"
        )
        checked += 1

    # Not an assertion on `checked`: in a shard where the parent was swapped
    # after binding, zero is the correct answer and the rule above still holds
    # vacuously. `test_each_declared_module_is_actually_real_in_this_process`
    # is what guarantees the modules themselves, and it is not order-dependent.
