# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A test that returns a value instead of asserting cannot fail (#14920).

pytest discards whatever a test function returns. A function ending in
``return False`` therefore passes, and so does the same function ending in
``return True`` — the two branches are indistinguishable to the runner. The
function reads like a check, is collected, is counted, and is reported green
whichever way it went. That is worse than an absent test, because an absent
test does not appear in the total.

WHY A CONFIG SETTING IS NOT THE WHOLE FIX
-----------------------------------------
``filterwarnings = error::pytest.PytestReturnNotNoneWarning`` in ``pytest.ini``
does turn the warning into a failure — verified against pytest 9.0.2 — and it
belongs there the moment the collected trees are clean. It is not a substitute
for this file, for two reasons:

* it only ever sees tests that **run**. Of the returns measured on this branch,
  141 of 277 are in trees no pytest invocation collects, so the warning would
  never be emitted for them and the config would report a clean tree while more
  than half the population sat outside its reach. #14928 covers the related
  hazard: ``pytest`` is unpinned, so the flip arrives on a release nobody chose.
* it fires per test execution, so a test skipped in a shard, deselected by a
  marker, or living behind a collection error contributes nothing.

An AST sweep has neither limit: it reaches every module on disk whether or not
anything runs it.

HOW A RETURN IS ATTRIBUTED
--------------------------
To the test function that **directly** encloses it. A naive ``ast.walk``
descends into nested helper functions and closures defined inside a test and
counts their returns as the test's own; on this branch that inflates 277 to
1870, a number nearly seven times too large that would make any ratchet
meaningless.

WHAT IS DELIBERATELY NOT COUNTED, AND WHY
-----------------------------------------
Measured on this branch, each derived from the code rather than from a list:

* returns in ``test_*`` methods of classes pytest does not collect — they are
  ordinary methods that happen to be named like tests, so converting their
  ``return`` to ``assert`` would change nothing until something runs them. That
  is its own defect, tracked by **#14927** and guarded by
  ``repo_tests/test_methods_in_uncollected_classes_test.py``.

  This exclusion used to be described here as "152 returns in classes that do
  not match ``python_classes``", citing #14927's figure of 120 methods in 23
  classes including 13 in an IDOR hotfix suite. That description was wrong, and
  wrong in a way worth recording: ``python_classes`` is only one of pytest's
  three collection rules. ``unittest.TestCase`` subclasses are collected
  whatever they are called — which is why all 13 of the IDOR tests were
  collecting, running and passing the entire time — and a base class is
  collected through any ``Test*`` subclass that inherits it. Pulling the other
  way, a class WITH ``__init__`` is not collected however it is named, which hid
  41 further methods that neither #14927 nor this file could see. The corrected
  figure was settled by running ``--collect-only``, not by matching names.
* **11** returns in ``test_*`` functions decorated with ``@pytest.fixture`` —
  a fixture is *supposed* to return; its name is the only thing test-shaped
  about it.
* generator tests (``yield``), whose ``return`` sets StopIteration rather than
  a value pytest would read. There are none today, and the branch is exercised
  by the self-test below rather than left unproven.
* a bare ``return`` and an explicit ``return None`` — pytest does not warn on
  either, because neither returns a value.

WHEN AN ASSERT DOES NOT COUNT AS PROTECTION (#15195)
----------------------------------------------------
The exemption above spends itself only on assertions that can actually FIRE.
One sitting in the body of a ``try`` whose handler catches ``Exception``,
``BaseException`` or ``AssertionError`` without re-raising is inert: the test
returns on both branches and cannot fail, while reading as defended to a sweep
that only looked for the node. Nine of the ten functions in #15189 were exactly
that. ``propagating_guards`` in ``repo_tests/collected_test_model`` decides it,
and carries the full rule and its deliberate narrowness.

``_SWALLOWED_ASSERTIONS`` below is the general form of the same defect — an
inert assertion in a test that does NOT return a value, which the returns
ceiling structurally cannot see.

THE RATCHET
-----------
Keyed on the top-level tree, never on a filename: an exemption keyed on a path
is stranded by the first rename, and a stranded exemption exempts nothing while
looking authoritative. Every tree not named in ``_KNOWN_OFFENDERS`` is pinned at
**zero** by derivation, so a new offender anywhere in the eleven clean trees
fails on arrival without anyone maintaining a list. The named trees may only
shrink, and an entry that reaches zero must be deleted rather than left at
``0`` — a budget nobody can spend is still a budget somebody will.

Two properties the ratchet has to get right, both of which have bitten this
repository's other baseline guards:

* **a broken scan must not read as progress.** Each named tree carries a floor
  on its own test-function population as well as a ceiling on its offenders. A
  walk that quietly stops matching collapses the offender count to zero, which
  is indistinguishable from finished work — so the collapse is checked first,
  and it fails telling the reader to fix the sweep rather than to write the
  zero down.
* **there is no sanctioned route to raise a number, on purpose.** A test that
  returns a value instead of asserting is never the right thing to write, so no
  reviewer override is offered and none is implied. #14919 exists because a
  guard promised a route its code never implemented; this one promises nothing
  it does not do.
"""

from __future__ import annotations

import ast

import pytest

from repo_tests.collected_test_model import (
    REPO_ROOT,
    collectable_tests,
    is_fixture,
    own_nodes,
    parse_module,
    propagating_guards,
    pytest_option,
    swallowed_assertions_in,
    test_functions_by_tree,
    test_modules,
)


# Measured on this branch, per top-level tree:
#   tree: (return statements that must not be exceeded,
#          test functions that must STILL be found in that tree)
#
# The second number is not decoration. Without it, a walk that breaks and
# returns nothing looks identical to a tree somebody finished draining, and the
# ratchet would record the collapse as a triumph and lock it in. A tree may
# only be declared drained while its own population is still demonstrably
# there. Delete an entry once its budget genuinely reaches zero.
_KNOWN_OFFENDERS = {
    # Lowered in the same commit that changed the definition, as this file's own
    # ratchet requires: 136 -> 78 and 134 -> 126.
    #
    # Be precise about WHY these moved, because the obvious reading is wrong.
    # The drop is NOT the nine driver-consumed functions that commit fixed —
    # none of those are in `autobot-backend`, yet that tree fell 58. The whole
    # movement is a side effect of the exemption in `offending_returns`: a test
    # that asserts AND returns is no longer counted, because it can fail and its
    # return value is a separate driver contract (#14920). That tree-wide change
    # un-flags 39 pre-existing functions in `autobot-backend` and 4 in
    # `autobot-infrastructure` that neither commit touched.
    #
    # Those 43 were checked rather than assumed: every one carries real
    # assertions (1-24 apiece) alongside its return, so none is a vacuous assert
    # masking a test that cannot fail.
    #
    # The drop is not a sweep collapse — the population floors below are
    # untouched and still pass, which is what tells the two apart.
    # 78 -> 75 with #14941 (test_celery_worker_status stopped returning a verdict
    # pytest discards) and #14927 (three classes converted to collect, which moves
    # their methods into this file's population as well).
    #
    # 126 -> 121 with #14518: the inline-python and driver scripts under
    # `shared/scripts` (test_phase5_cleanup, verify_backend_config,
    # verify_ssh_manager, test_redis_comparison) now assert instead of handing a
    # verdict back to a caller that discards it. Measured, not estimated — the
    # sweep reports 121 and the population floor below is unmoved, which is what
    # separates a real drain from a sweep that stopped matching.
    #
    # 75 -> 73 with #14989: api/simple_terminal_e2e_test.py's own new
    # early-return offender was converted to an assert in the same commit that
    # added it, and merging Dev_new_gui landed one further pre-existing fix
    # elsewhere in the tree.
    #
    # Both reductions survive together: the ratchet only turns down, so where
    # two branches each lowered a budget the merge keeps the lower of the two,
    # never the more permissive one.
    #
    # 73 -> 71 with #14979: cache/cache_consolidation_p4_test.py's ten functions
    # each wrapped their asserts in `except Exception: return False`, so the bare
    # except swallowed AssertionError and not one of the ten could fail. All ten
    # returns are gone and the assertions now propagate.
    #
    # Only 2 of the 10 move this number, and the reason is worth recording:
    # `_offending_returns` skips any test containing an `assert` or `raise`,
    # because "returning instead of asserting" is the defect and a test that does
    # both can still fail. Nine of the ten HAD asserts -- inert ones, neutralised
    # by the bare except, but present -- so this sweep passed over them. Only
    # `test_migrated_files_import`, whose body was `pass` plus prints with no
    # assert at all, was ever counted (2 returns, lines 281 and 288).
    #
    # So this guard is blind to an assert that cannot fire. That gap is #15195.
    #
    # 71 -> 86 and 121 -> 127 with #15195: A DELIBERATE RE-MEASUREMENT, NOT A
    # RATCHET VIOLATION, AND THE ONLY ONE THIS FILE SANCTIONS.
    #
    # The ceilings above are down-only against a FIXED definition of the defect.
    # #15195 changed the definition: an assertion neutralised by a handler that
    # catches AssertionError no longer buys the assert/raise exemption, because
    # such a test cannot fail — which is the whole subject of this sweep. The
    # population did not grow; the detector stopped missing part of it. Nothing
    # was written, nothing regressed, and no offending line is new.
    #
    # The distinction that keeps this from being a loophole: a re-baseline is
    # legitimate only when the sweep is made STRICTER and the delta is
    # enumerated. Both hold here. The 21 newly-counted returns are 8 functions
    # in 3 files, every one of them pre-existing:
    #
    #   autobot-backend/config/config_consolidation_p2_test.py        11 returns
    #     (test_config_consolidation — ten `try: assert…/except Exception:
    #      return False` sections in one function)
    #   autobot-backend/tests/integration/
    #     test_causal_framework_integration.py                         4 returns
    #     (four *_full_pipeline methods that catch AssertionError into a
    #      scenario report and return it)
    #   autobot-infrastructure/shared/scripts/test_configuration.py    6 returns
    #     (three driver functions consumed by the module's own main())
    #
    # No previously-counted site stopped being counted (the base set is a strict
    # subset of the new one, verified site-by-site), and no tree outside this
    # dict gained an offender — the hard zero below is unmoved. Those 8 are
    # reported, not converted, under #15189: two of the three files are large
    # live-service drivers where unwrapping the swallow is its own piece of
    # work, and half-converting a population is how a ratchet gets stuck.
    #
    # A number here may be raised again ONLY on the same terms: the detector got
    # stricter, and the delta is enumerated in this comment. Fixing tests still
    # requires no permission at all.
    # 127 -> 121 with #15189: the three swallowing driver functions in
    # shared/scripts/test_configuration.py lost their `except Exception:
    # return False` wrappers, so their assertions propagate — exempt by the
    # rule above, since a test with a LIVE assertion is no longer counted.
    # 86 -> 75 with #15189 (continued): config_consolidation_p2_test.py's ten
    # swallowing sections are now ten real tests; all 11 counted returns gone.
    "autobot-backend": (75, 18000),
    "autobot-infrastructure": (121, 250),
    "autobot-npu-worker": (7, 150),
}

# Test functions holding at least one assertion that cannot fire, per top-level
# tree, paired with the same population floor as above (#15195).
#
# The sibling defect, and the one that made this file blind: an `assert` under a
# handler catching Exception/BaseException/AssertionError. The ceiling above
# only sees it when the function ALSO returns a value; this one sees it whether
# or not it returns, which is what closes the general case. Nine functions
# today, and every tree not named here is pinned at zero by derivation.
#
# Down-only, on the same terms as every other ceiling in this file: there is no
# sanctioned route to raise one. Wrapping a test's own assertions in
# `except Exception` is never the right thing to write — if the test is meant to
# tolerate an error, catch the specific exception it tolerates; if it is meant
# to report one, `pytest.fail(...)` or `raise` in the handler, both of which
# this guard already recognises as reporting rather than swallowing.
#
# 9 -> 5 with #15189 (`autobot-infrastructure` deleted rather than left at zero): three
# driver functions in shared/scripts/test_configuration.py and
# `test_secrets_service_config_migration` in config_migration_integration_test.py were
# unwrapped. The five remaining, named in #15189, needed #15166-style restructuring: one
# in config_consolidation_p2_test.py, four aggregator methods in
# test_causal_framework_integration.py.
# 5 -> 4 (continued): config_consolidation_p2_test.py is now ten real tests, zero inert
# asserts, surfacing two drifts fixed in the same change: `_get_default_config()` never
# existed on `ConfigManager` (real fn: `config.defaults.get_default_config()`), and
# multimodal asserted the pre-#13207 `voice.confidence_threshold` of 0.8, not current
# 0.7 — the remaining four are the unchanged aggregator methods.
_SWALLOWED_ASSERTIONS = {
    "autobot-backend": (4, 18000),
}

# Floors under the whole population. A sweep that has silently stopped matching
# finds no offenders and reads exactly like a clean tree.
_MIN_MODULES = 1800
_MIN_TEST_FUNCTIONS = 25000


def offending_returns(source: str) -> list[tuple[str, int]]:
    """``(test name, line)`` for every value-return a collected test makes.

    A plain function over source text, so it can be driven with a synthetic
    module. A detector only ever pointed at the real tree cannot be told apart
    from one that has stopped detecting.
    """
    return _offending_returns(ast.parse(source))


def _offending_returns(tree: ast.Module) -> list[tuple[str, int]]:
    """The tree-driven half, so the repo sweep parses each module once."""
    found: list[tuple[str, int]] = []
    for function in collectable_tests(tree):
        if is_fixture(function) or own_nodes(function, (ast.Yield, ast.YieldFrom)):
            continue
        # The defect is returning *instead of* asserting — a test that cannot fail.
        # A test that asserts AND returns can fail, and its return value is a
        # separate contract: several drivers in this repo sum truthiness over
        # `result = test_func()`, so a bare assert there leaves a passing test
        # counted as failed. Both are needed, and neither is an offence (#14920).
        #
        # The exemption is spent only on assertions that can actually FIRE. One
        # sitting under a handler that catches AssertionError is inert, and a
        # test whose only assertions are inert cannot fail — which is precisely
        # the population this sweep exists to count (#15195).
        if propagating_guards(function):
            continue
        for node in own_nodes(function, (ast.Return,)):
            value = node.value
            if value is None or (isinstance(value, ast.Constant) and value.value is None):
                continue
            found.append((function.name, node.lineno))
    return found


def _swallowed_by_tree() -> dict[str, list[str]]:
    counts: dict[str, list[str]] = {}
    for module in test_modules():
        relative = module.relative_to(REPO_ROOT)
        for name, line in swallowed_assertions_in(parse_module(module)):
            counts.setdefault(relative.parts[0], []).append(f"{relative}:{line} {name}")
    return counts


def _offenders_by_tree() -> dict[str, list[str]]:
    counts: dict[str, list[str]] = {}
    for module in test_modules():
        relative = module.relative_to(REPO_ROOT)
        for name, line in _offending_returns(parse_module(module)):
            counts.setdefault(relative.parts[0], []).append(f"{relative}:{line} {name}")
    return counts


def test_the_population_is_present_and_large_enough_to_mean_anything() -> None:
    """Floors on the subject, not on the findings. Zero of zero is not clean."""
    modules = test_modules()
    assert len(modules) >= _MIN_MODULES, (
        f"only {len(modules)} modules match pytest's python_files "
        f"{pytest_option('python_files')} — expected at least {_MIN_MODULES}. "
        "The sweep has stopped matching and would call every tree clean."
    )
    total = sum(
        len(collectable_tests(parse_module(module)))
        for module in modules
    )
    assert total >= _MIN_TEST_FUNCTIONS, (
        f"only {total} collectable test functions found across {len(modules)} modules "
        f"— expected at least {_MIN_TEST_FUNCTIONS}; the collector model has drifted "
        "from pytest's and this guard is looking at the wrong population"
    )


def test_no_tree_outside_the_known_set_has_a_test_that_returns_a_value() -> None:
    """The hard zero. Eleven clean trees, derived — no list to go stale."""
    offenders = _offenders_by_tree()
    surprises = {
        tree: sites for tree, sites in offenders.items() if tree not in _KNOWN_OFFENDERS
    }
    detail = "\n".join(
        f"  {tree}:\n    " + "\n    ".join(sorted(sites))
        for tree, sites in sorted(surprises.items())
    )
    assert not surprises, (
        "these tests return a value instead of asserting, in a tree that was "
        f"clean:\n{detail}\n"
        "pytest discards the value, so the test passes whichever branch it takes. "
        "Use `assert`; if the value is consumed by another test it is a fixture, "
        "and if the function was never a test, move it behind a main() guard "
        "(#14920)."
    )


def test_the_known_offender_budgets_only_ever_shrink() -> None:
    """Ratchet, both directions — a recorded shrink must be locked in (#14498).

    THERE IS NO SANCTIONED ROUTE FOR AN INCREASE, and that is deliberate rather
    than an omission. A new test that returns a value instead of asserting is
    never the right thing to write: the value cannot reach pytest, so there is
    nothing an author could be trying to express that ``assert`` does not
    express better. If the value is consumed by another test the function is a
    fixture, and if the function was never a test it belongs behind a
    ``main()`` guard. Raising a number here is not a reviewer decision this
    guard offers — #14919 was filed because a guard advertised a route its code
    did not implement, so this one advertises none.

    Lowering a number, by contrast, needs no permission at all: fix a test and
    the assertion below tells you the new figure to write down.
    """
    offenders = _offenders_by_tree()
    populations = test_functions_by_tree()

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
        "these trees gained tests that return a value instead of asserting "
        f"(actual, budget): {over}. The budgets are ceilings and there is no "
        "route to raise one — use `assert` (#14920)."
    )
    drained = sorted(tree for tree, _ in _KNOWN_OFFENDERS.items() if not offenders.get(tree))
    assert not drained, (
        f"{drained} no longer contain any returning test — delete the entry from "
        "_KNOWN_OFFENDERS so the tree is pinned at zero by derivation. A budget "
        "left behind after the work is done is spendable, and it will be spent."
    )
    spent = {
        tree: (len(offenders.get(tree, [])), budget)
        for tree, (budget, _) in _KNOWN_OFFENDERS.items()
        if len(offenders.get(tree, [])) < budget
    }
    assert not spent, (
        "these trees are now BELOW their recorded budget (actual, budget): "
        f"{spent}. Lower the number here in the same commit, or the lines a fix "
        "removed can be spent back inside a stale tolerance."
    )


def test_no_test_smothers_its_own_assertions_under_a_swallowing_handler() -> None:
    """The general case of #15195, whether or not the function also returns.

    A ``try`` whose handler catches ``Exception``/``BaseException``/
    ``AssertionError`` and neither re-raises nor calls a pytest outcome absorbs
    the ``AssertionError`` its own body raises. Every assertion in that body is
    decoration: the test reports green on the failing branch and on the passing
    one alike. Nine functions carry that shape today; every other tree is pinned
    at zero by derivation, so the tenth fails on arrival.

    Down-only, and no route up. If the test is meant to tolerate an error, name
    the exception it tolerates; if it is meant to report one, ``pytest.fail`` or
    ``raise`` in the handler — both are read as reporting, not swallowing.
    """
    swallowed = _swallowed_by_tree()
    populations = test_functions_by_tree()

    collapsed = {
        tree: (populations.get(tree, 0), floor)
        for tree, (_, floor) in _SWALLOWED_ASSERTIONS.items()
        if populations.get(tree, 0) < floor
    }
    assert not collapsed, (
        "the sweep no longer finds the tests it is supposed to be scanning "
        f"(found, floor): {collapsed}. Fix the sweep; do NOT lower these numbers."
    )

    surprises = {
        tree: sites
        for tree, sites in swallowed.items()
        if tree not in _SWALLOWED_ASSERTIONS
    }
    detail = "\n".join(
        f"  {tree}:\n    " + "\n    ".join(sorted(sites))
        for tree, sites in sorted(surprises.items())
    )
    assert not surprises, (
        "these tests assert inside a `try` whose handler swallows the "
        f"AssertionError, in a tree that was clean:\n{detail}\n"
        "The assertion cannot fire, so the test passes whichever way it goes. "
        "Catch the specific exception the test tolerates, or re-raise / "
        "pytest.fail in the handler (#15195)."
    )

    over = {
        tree: (len(swallowed.get(tree, [])), budget)
        for tree, (budget, _) in _SWALLOWED_ASSERTIONS.items()
        if len(swallowed.get(tree, [])) > budget
    }
    assert not over, (
        "these trees gained a test whose assertions cannot fire "
        f"(actual, budget): {over}. The budgets are ceilings and there is no "
        "route to raise one (#15195)."
    )
    drained = sorted(tree for tree in _SWALLOWED_ASSERTIONS if not swallowed.get(tree))
    assert not drained, (
        f"{drained} no longer smother any assertion — delete the entry from "
        "_SWALLOWED_ASSERTIONS so the tree is pinned at zero by derivation."
    )
    spent = {
        tree: (len(swallowed.get(tree, [])), budget)
        for tree, (budget, _) in _SWALLOWED_ASSERTIONS.items()
        if len(swallowed.get(tree, [])) < budget
    }
    assert not spent, (
        "these trees are now BELOW their recorded budget (actual, budget): "
        f"{spent}. Lower the number here in the same commit."
    )


def test_the_detector_finds_a_planted_return_and_spares_the_legitimate_ones() -> None:
    """Self-test. Every exclusion branch is exercised, not merely written down."""
    assert offending_returns("def test_a():\n    return False\n") == [("test_a", 2)]
    assert offending_returns("class TestX:\n    def test_a(self):\n        return 1\n")

    # Excluded, and each for a different reason.
    assert not offending_returns("def test_a():\n    return\n"), "a bare return"
    assert not offending_returns("def test_a():\n    return None\n"), "an explicit None"
    assert not offending_returns(
        "import pytest\n\n\n@pytest.fixture\ndef test_a():\n    return 1\n"
    ), "a fixture is supposed to return"
    assert not offending_returns(
        "def test_a():\n    yield 1\n    return 2\n"
    ), "a generator's return is StopIteration's value, not a verdict"
    assert not offending_returns(
        "class Helper:\n    def test_a(self):\n        return 1\n"
    ), "pytest does not collect a method of a non-Test class"

    # Attribution: the nested helper owns its own return, the test does not.
    nested = "def test_a():\n    def helper():\n        return 1\n\n    helper()\n"
    assert not offending_returns(nested), (
        "a nested helper's return was attributed to its enclosing test — that is "
        "the naive walk this guard exists to avoid"
    )

    # The assert/raise exemption added with the #14920 driver fix. Every other
    # branch here has a synthetic case; without one this branch is proven only
    # by whatever the live tree happens to contain today.
    assert not offending_returns(
        "def test_a():\n    assert True\n    return True\n"
    ), "a test that asserts AND returns can fail; its return is a separate driver contract"
    assert not offending_returns(
        "def test_b():\n    raise AssertionError('x')\n    return True\n"
    ), "a raising test can fail; its return is a separate driver contract"
    assert offending_returns(
        "def test_c():\n    return True\n"
    ), "a test whose return is its ONLY verdict is still an offence"

    # #15195 narrowed that exemption to assertions which can actually fire. The
    # driver shape it exists to protect must survive the narrowing, including
    # when the driver guards itself against a specific error it tolerates —
    # `except ValueError` does not catch an AssertionError, so the assert below
    # still propagates and the return is still a separate driver contract.
    assert not offending_returns(
        "def test_a():\n"
        "    try:\n"
        "        assert True\n"
        "        return True\n"
        "    except ValueError:\n"
        "        return False\n"
    ), "a handler naming a non-assertion exception leaves the assert able to fire"

    swallowing = (
        "def test_a():\n"
        "    try:\n"
        "        assert 1 == 2, 'nope'\n"
        "        return True\n"
        "    except Exception:\n"
        "        return False\n"
    )
    assert sorted(offending_returns(swallowing)) == [("test_a", 4), ("test_a", 6)], (
        "an assert under `except Exception` is inert — the test cannot fail, "
        "which is exactly this sweep's subject (#15195)"
    )
    for catcher in (
        "except BaseException:",
        "except AssertionError:",
        "except:",
        "except (ValueError, Exception):",
        "except Exception as exc:",
    ):
        assert offending_returns(
            swallowing.replace("except Exception:", catcher)
        ), f"`{catcher}` swallows AssertionError too"
    for handler in ("        raise\n", "        assert False\n"):
        assert not offending_returns(
            swallowing.replace("        return False\n", handler)
        ), "a handler that hands the failure back on protects nothing away"


def test_an_unparseable_swept_file_fails_loudly_instead_of_reading_as_clean() -> None:
    """The sweep is a denylist from the repo root, so it meets stray files.

    One must never be skipped: a file the walk could not read is not a file the
    walk cleared, and dropping it silently is the under-reporting this guard
    exists to catch. It has to fail, name the file and say what to do about it.

    The probe is written under a ``SKIP``ped directory so no concurrently
    running sweep can pick it up while it exists.
    """
    scratch = REPO_ROOT / "__pycache__"
    scratch.mkdir(exist_ok=True)
    stray = scratch / "unparseable_probe_test.py"
    stray.write_text("from a-b.c import (\n", encoding="utf-8")
    try:
        with pytest.raises(AssertionError) as raised:
            parse_module(stray)
    finally:
        stray.unlink()

    message = str(raised.value)
    assert "unparseable_probe_test.py" in message, "the failure must name the file"
    assert "SKIP" in message, "the failure must say how to exclude a file on purpose"
