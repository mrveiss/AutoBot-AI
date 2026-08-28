# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ratchet over ``test_*`` methods in classes pytest will not collect.

The collection model this rests on is ``uncollected_class_model``; see its
docstring for why an AST sweep has to model pytest rather than ``python_classes``
alone. This file holds only the measured numbers and the assertions that keep
them turning one way.

WHAT IS DELIBERATELY NOT COUNTED
--------------------------------
A private stand-in implementing a production interface that happens to declare
a ``test_*`` method. ``AbstractConnector.test_connection`` is such an interface:
``_MinimalConnector`` and ``_DummyConnector`` must implement it under that
name, and renaming it is not available. They are not tests and pytest is right
not to collect them. The exemption is pinned at its exact measured size below
rather than left open, so a third one cannot arrive unnoticed.

THE RATCHET
-----------
Keyed on the top-level tree, never on a filename -- an exemption keyed on a path
is stranded by the first rename, and a stranded exemption exempts nothing while
looking authoritative. Every tree not named in ``_KNOWN_OFFENDERS`` is pinned at
zero by derivation. The named trees may only shrink, and an entry reaching zero
must be deleted rather than left at ``0``.

The population floors are the half that matters most. A sweep that quietly stops
matching finds no offenders, and "no offenders" is indistinguishable from
finished work -- so the collapse is checked *first*, and it fails telling the
reader to fix the sweep rather than to write the zero down.
"""

from __future__ import annotations

import ast

from repo_tests.uncollected_class_model import (
    _init_state,
    _offenders_by_tree,
    _parsed,
    _population_by_tree,
    _pytest_option,
    _REPO_ROOT,
    _scan,
    _test_modules,
)

# Measured on this branch, per top-level tree:
#   tree: (uncollected test_* methods that must not be exceeded,
#          collectable test functions that must STILL be found in that tree)
#
# The second number is not decoration. Without it, a walk that breaks and finds
# nothing looks identical to a tree somebody finished draining, and this file
# would record the collapse as a triumph and lock it in.
#
# Nearly every remaining offender is a live-service validation driver: a class
# with `__init__`, a `run_all_*` loop and a `main()`, whose methods dial a
# running backend and return bool. A bare rename is actively harmful -- a
# `Test*` class keeping its `__init__` collects zero while looking fixed -- so
# they are filed with per-file counts, and this ceiling stops the population
# growing back. "Nearly": #14979 found two that dialled nothing at all.
_KNOWN_OFFENDERS = {
    # 77 -> 59 (#14927): takeover_manager_e2e_test.py, temporal_invalidation_test.py
    # 59 -> 8  (#14979): the eight remaining backend drivers from the issue's table
    #   (hardware_metrics, comprehensive_system_validation, chat_knowledge_system_e2e,
    #   monitoring_and_alerts, multi_agent_workflow_validation, npu_integration_e2e,
    #   async_baseline_performance, knowledge_performance).
    # The 8 left are NOT from that table -- they are whatever else in this tree
    # still puts test_* methods in a class pytest will not collect. Nothing in
    # #14979 was meant to reach them, and the ceiling now pins them exactly.
    "autobot-backend": (8, 18000),
    # autobot-frontend and autobot-infrastructure are gone from this dict rather
    # than left at 0: both drained to zero in #14979, and the ratchet requires a
    # drained entry be deleted so the tree is pinned at zero by derivation. A
    # budget left behind after the work is done is spendable, and it will be spent.
    #
    # Deleting them also drops their population floors (10 and 250). That is the
    # documented trade and it is the smaller loss: with no entry, EVERY uncollected
    # test method in either tree now fails
    # `test_no_tree_outside_the_known_set_holds_an_uncollected_test_method`
    # outright, which is strictly stronger than a floor plus a spendable budget.
}

# Floors under the whole population, for the same reason as the per-tree ones.
_MIN_MODULES = 1800
_MIN_TEST_FUNCTIONS = 25000

# Private stand-ins implementing a production interface that declares a `test_*`
# method. Pinned at the exact measured count: the exemption is a convention rule
# ("a leading underscore means a helper"), and a convention rule with no ceiling
# is a bypass waiting to be used.
_INTERFACE_STUBS = 2


def test_the_population_is_present_and_large_enough_to_mean_anything() -> None:
    """Floors on the subject, not on the findings. Zero of zero is not clean."""
    modules = _test_modules()
    assert len(modules) >= _MIN_MODULES, (
        f"only {len(modules)} modules match pytest's python_files "
        f"{_pytest_option('python_files')} — expected at least {_MIN_MODULES}. "
        "The sweep has stopped matching and would call every tree clean."
    )
    total = sum(_population_by_tree().values())
    assert total >= _MIN_TEST_FUNCTIONS, (
        f"only {total} collectable test functions found across {len(modules)} modules "
        f"— expected at least {_MIN_TEST_FUNCTIONS}; the collector model has drifted "
        "from pytest's and this guard is looking at the wrong population"
    )


def test_no_tree_outside_the_known_set_holds_an_uncollected_test_method() -> None:
    """The hard zero, derived — no list to go stale."""
    offenders = _offenders_by_tree()
    surprises = {
        tree: sites for tree, sites in offenders.items() if tree not in _KNOWN_OFFENDERS
    }
    detail = "\n".join(
        f"  {tree}:\n    " + "\n    ".join(sorted(sites))
        for tree, sites in sorted(surprises.items())
    )
    assert not surprises, (
        "these test_* methods sit in a class pytest will not collect, in a tree "
        f"that was clean:\n{detail}\n"
        "Nothing runs them and they contribute zero to the suite total. Give the "
        "class a Test* name AND no __init__ (use setup_method), or derive it from "
        "unittest.TestCase, or move the methods to module level. If the class is a "
        "helper, rename the methods out of the test_* namespace (#14927)."
    )


def test_the_known_offender_budgets_only_ever_shrink() -> None:
    """Ratchet, both directions — a recorded shrink must be locked in (#14498).

    There is no sanctioned route to raise a number, and that is deliberate. A
    ``test_*`` method that nothing collects is never the right thing to write:
    every reader is told a check exists where none runs. Lowering a number needs
    no permission at all — fix a class and the assertion below names the new
    figure.
    """
    offenders = _offenders_by_tree()
    populations = _population_by_tree()

    collapsed = {
        tree: (populations.get(tree, 0), floor)
        for tree, (_, floor) in _KNOWN_OFFENDERS.items()
        if populations.get(tree, 0) < floor
    }
    assert not collapsed, (
        "the sweep no longer finds the tests it is supposed to be scanning "
        f"(found, floor): {collapsed}. Every count below is therefore untrusted — "
        "a scan that finds nothing reports a clean tree and a drop to zero reads "
        "as progress. Fix the sweep; do NOT lower these numbers to match it."
    )

    over = {
        tree: (len(offenders.get(tree, [])), budget)
        for tree, (budget, _) in _KNOWN_OFFENDERS.items()
        if len(offenders.get(tree, [])) > budget
    }
    assert not over, (
        "these trees gained a test_* method in a class pytest cannot collect "
        f"(actual, budget): {over}. The budgets are ceilings and there is no "
        "route to raise one (#14927)."
    )
    drained = sorted(tree for tree in _KNOWN_OFFENDERS if not offenders.get(tree))
    assert not drained, (
        f"{drained} no longer hold any uncollected test method — delete the entry "
        "from _KNOWN_OFFENDERS so the tree is pinned at zero by derivation. A "
        "budget left behind after the work is done is spendable, and it will be spent."
    )
    spent = {
        tree: (len(offenders.get(tree, [])), budget)
        for tree, (budget, _) in _KNOWN_OFFENDERS.items()
        if len(offenders.get(tree, [])) < budget
    }
    assert not spent, (
        "these trees are now BELOW their recorded budget (actual, budget): "
        f"{spent}. Lower the number here in the same commit, or the methods a fix "
        "collected can be spent back inside a stale tolerance."
    )


def test_the_interface_stub_exemption_has_not_grown() -> None:
    """The one exemption, pinned at its exact size.

    ``_MinimalConnector`` and ``_DummyConnector`` implement
    ``AbstractConnector.test_connection``; the production interface dictates the
    name, so neither renaming the method nor collecting the class is available.
    Exempting them is right. Leaving the exemption open-ended is not — "starts
    with an underscore" is a convention, and a convention with no ceiling is a
    bypass. A third stand-in must be looked at rather than absorbed.
    """
    stubs = _scan()[2]
    assert len(stubs) == _INTERFACE_STUBS, (
        f"the interface-stub exemption now covers {len(stubs)} methods, not "
        f"{_INTERFACE_STUBS}: {sorted(stubs)}. Each one is a test_* method nothing "
        "collects, exempted only because a production interface dictates its name. "
        "Confirm that is still true of every entry before changing this number."
    )


def test_no_test_class_inherits_init_from_an_unresolvable_base() -> None:
    """The explicit decision #14984 asks for, made loud instead of silent.

    A base this model cannot locate -- third-party, dynamically built, supplied
    by a star-import -- has an unknown ``__init__``. Unknown is not clean:
    ``_init_state`` reads it as ``__init__``-present, so the class's methods
    already count as offenders above. That is the safe direction but a confusing
    message, so every such class is named here as well, with the base that could
    not be reached. Measured zero on this branch.
    """
    unresolved = _scan()[3]
    assert not unresolved, (
        f"{len(unresolved)} Test* class(es) inherit from a base this guard cannot "
        "resolve, so whether pytest collects them is unknown:\n  "
        + "\n  ".join(sorted(unresolved))
        + "\npytest asks cls.__init__ is not object.__init__, which walks the MRO, so "
        "a constructor anywhere up the chain means the class is never collected and "
        "its test_* methods never run. Resolve it: import the base by a path this "
        "repo can follow, or give the class a base whose module is in the repo. The "
        "counts above treat these as uncollected on purpose -- an unreadable base is "
        "not a base that has been cleared (#14984)."
    )


def test_an_init_inherited_from_another_module_is_actually_followed() -> None:
    """The cross-module walk must be live, not merely written down.

    Two real classes reach their base through an absolute import
    (``ConnectorAcceptanceTest``, one package over). If the resolver silently
    returned "unknown" for every import, the assertion above would still pass by
    treating them as uncollected -- so the positive direction is pinned here: the
    base is found, and found to declare no constructor.
    """
    subclasses = [
        module
        for module in _test_modules()
        if "ConnectorAcceptanceTest" in module.read_text(encoding="utf-8")
        and "class Test" in module.read_text(encoding="utf-8")
    ]
    assert subclasses, (
        "no module inherits from ConnectorAcceptanceTest any more — this test pins "
        "the cross-module base walk to a real subject and now has none. Point it at "
        "another Test* class with an imported base, or the walk is unchecked (#14984)."
    )
    for module in subclasses:
        classes = {n.name: n for n in _parsed(module).body if isinstance(n, ast.ClassDef)}
        for name, node in classes.items():
            if not name.startswith("Test"):
                continue
            assert _init_state(node, classes, module) is False, (
                f"{module.relative_to(_REPO_ROOT)}::{name} — the base walk did not reach "
                "ConnectorAcceptanceTest through its import and settle its __init__ state"
            )


