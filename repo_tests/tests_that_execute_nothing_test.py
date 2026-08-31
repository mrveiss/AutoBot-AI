# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A collected test whose body runs nothing still reports green (#15189).

The third shape in the #15189 family, and the only one neither of this
repository's existing ceilings can see::

    def test_migrated_files_import():
        \"\"\"All six migrated modules import successfully.\"\"\"
        pass
        print("✅ services.chat_service imports")
        print("✅ services.rag_service imports")
        ...

That function was real, in ``autobot-backend/cache/cache_consolidation_p4_test.py``
before #15166 fixed it. Its ``import`` statements had been stripped at some
point and nothing noticed, because there was nothing left to notice: it
asserted six imports, performed none, and printed six successes.

WHY THE OTHER TWO GUARDS CANNOT SEE THIS
----------------------------------------
``repo_tests/tests_that_return_instead_of_asserting_test.py`` counts a returned
verdict pytest discards — this shape returns nothing. Its ``_SWALLOWED_ASSERTIONS``
companion counts an assertion neutralised by a handler that catches
``AssertionError`` (#15195) — this shape holds no assertion to neutralise. Both
are ceilings on a written-down thing that does not work; this one is a ceiling
on nothing being written down at all, which is why it needs its own sweep
rather than another number in that file.

WHAT COUNTS, AND HOW NARROWLY
-----------------------------
Every statement in the body is a no-op: ``pass``, ``...``, a bare string
(docstring, or a comment written as one), or ``print(...)`` as a bare name.
``does_nothing`` in ``repo_tests/collected_test_model`` carries the rule.

The narrowness is the point, in three directions, because a guard that
over-flags is a guard somebody switches off:

* **one statement that calls something and the function is out of scope.** A
  test that only calls its subject is a thin test, but "it does not raise" is a
  real assertion and this guard has no business flagging it.
* ``reporter.print(...)`` is somebody's method, not the builtin. Only a bare
  ``print`` name is a no-op.
* a test carrying ``@pytest.mark.skip``/``skipif``/``xfail`` is **declaring**
  that it does not run or is not expected to pass. An empty body under one of
  those is honest, and honesty is not this guard's subject.

THE RATCHET
-----------
Keyed on the top-level tree, never on a filename — an exemption keyed on a path
is stranded by the first rename. Every tree not named below is pinned at zero
by derivation, so the twelfth fails on arrival in any of the other trees with
nobody maintaining a list.

Down-only, and no route up, on the same terms as the sibling guard. There is
nothing an author could be trying to express with an empty test body that a
real body does not express better; if the check genuinely cannot be written
yet, ``@pytest.mark.skip(reason=...)`` says so out loud and this guard steps
aside for it. Lowering a number needs no permission at all — fix a test and the
assertion below prints the new figure.

Each entry also carries a floor on its tree's own test population, for the
reason every baseline guard in ``repo_tests`` carries one: a walk that quietly
stops matching finds nothing, and finding nothing is indistinguishable from
finished work. The collapse is checked before the count, and it fails telling
the reader to fix the sweep rather than to write the zero down.
"""

from __future__ import annotations

from repo_tests.collected_test_model import (
    REPO_ROOT,
    empty_bodies,
    empty_bodies_in,
    parse_module,
    test_functions_by_tree,
    test_modules,
)

# Measured on this branch, per top-level tree.
#
# All eleven found under #15189 are now written for real (#15256):
#
#   autobot-backend/config/timeout_configuration_test.py            2
#     now exercises DocumentsMixin.add_document's asyncio.wait_for(timeout=
#     kb_timeouts.document_add) against a controllable internal delay.
#   autobot-backend/services/rag_integration_test.py                5
#     moved to services/rag_integration_api_test.py (#15256, kept this file
#     under MAX_LINES) and now hit the real api.knowledge_rag router through
#     TestClient with dependency_overrides standing in for auth and the
#     KnowledgeBase/RAGService construction.
#   autobot-backend/tests/api/test_knowledge_grounding.py           4
#     now hit the real api.knowledge_grounding router the same way, with the
#     GroundedAgent singleton and Redis client patched per test.
#
# No tree is pinned above zero. An entry only returns here if a real empty
# body is found again, and it fails on arrival in ANY tree by derivation --
# not just the ones that have had one before (see the module docstring).
_EMPTY_BODIED: dict[str, tuple[int, int]] = {}


def _empty_by_tree() -> dict[str, list[str]]:
    counts: dict[str, list[str]] = {}
    for module in test_modules():
        relative = module.relative_to(REPO_ROOT)
        for name, line in empty_bodies_in(parse_module(module)):
            counts.setdefault(relative.parts[0], []).append(f"{relative}:{line} {name}")
    return counts


# The sweep's own floor, deliberately NOT derived from _EMPTY_BODIED. That dict
# is now empty -- every tree reached zero -- so a floor computed from it iterates
# nothing and can never fire. A guard against tests that execute nothing must not
# itself pass by finding nothing: if test_modules() ever stops resolving, both the
# population and the empty-body count collapse to zero together and every
# assertion below reports clean. Measured 28708 across 13 trees on Dev_new_gui;
# the floors sit under that with room for ordinary churn, and only ever rise.
_TOTAL_FUNCTION_FLOOR = 25000
_TREE_FLOOR = 10


def _collapsed(populations: dict[str, int]) -> dict[str, tuple[int, int]]:
    return {
        tree: (populations.get(tree, 0), floor)
        for tree, (_, floor) in _EMPTY_BODIED.items()
        if populations.get(tree, 0) < floor
    }


def _sweep_shortfalls(populations: dict[str, int]) -> list[str]:
    """Every way the sweep can be too small, reported together."""
    total = sum(populations.values())
    shortfalls = []
    if total < _TOTAL_FUNCTION_FLOOR:
        shortfalls.append(f"only {total} test functions collected, floor is {_TOTAL_FUNCTION_FLOOR}")
    if len(populations) < _TREE_FLOOR:
        shortfalls.append(f"only {len(populations)} trees reached, floor is {_TREE_FLOOR}")
    collapsed = _collapsed(populations)
    if collapsed:
        shortfalls.append(f"trees below their recorded floor (found, floor): {collapsed}")
    return shortfalls


def test_no_tree_outside_the_known_set_has_a_test_that_executes_nothing() -> None:
    """The hard zero, derived — no list of clean trees to go stale."""
    populations = test_functions_by_tree()
    shortfalls = _sweep_shortfalls(populations)
    assert not shortfalls, (
        "the sweep no longer finds the tests it is supposed to be scanning: "
        + "; ".join(shortfalls)
        + ". The zero below is therefore meaningless — a scan that finds nothing "
        "reports every tree clean. Fix the sweep."
    )

    empty = _empty_by_tree()
    surprises = {tree: sites for tree, sites in empty.items() if tree not in _EMPTY_BODIED}
    detail = "\n".join(
        f"  {tree}:\n    " + "\n    ".join(sorted(sites))
        for tree, sites in sorted(surprises.items())
    )
    assert not surprises, (
        "these collected tests execute nothing at all — every statement in the "
        f"body is `pass`, `...`, a docstring or `print()` — in a tree that was "
        f"clean:\n{detail}\n"
        "pytest reports each of them green, so the suite counts a check nobody "
        "wrote. Write the body, or say out loud that it is not written with "
        "`@pytest.mark.skip(reason=...)` (#15189)."
    )


def test_the_empty_bodied_budgets_only_ever_shrink() -> None:
    """Ratchet, both directions — a recorded shrink is locked in (#14498)."""
    populations = test_functions_by_tree()
    shortfalls = _sweep_shortfalls(populations)
    assert not shortfalls, (
        "the sweep no longer finds the tests it is supposed to be scanning: "
        + "; ".join(shortfalls)
        + ". Fix the sweep; do NOT lower these numbers."
    )

    empty = _empty_by_tree()
    over = {
        tree: (len(empty.get(tree, [])), budget)
        for tree, (budget, _) in _EMPTY_BODIED.items()
        if len(empty.get(tree, [])) > budget
    }
    assert not over, (
        "these trees gained a test with nothing in its body "
        f"(actual, budget): {over}. The budgets are ceilings and there is no "
        "route to raise one — write the body, or mark the test skipped with a "
        "reason (#15189)."
    )
    drained = sorted(tree for tree in _EMPTY_BODIED if not empty.get(tree))
    assert not drained, (
        f"{drained} no longer contain an empty-bodied test — delete the entry "
        "from _EMPTY_BODIED so the tree is pinned at zero by derivation. A "
        "budget left behind after the work is done is spendable, and it will "
        "be spent."
    )
    spent = {
        tree: (len(empty.get(tree, [])), budget)
        for tree, (budget, _) in _EMPTY_BODIED.items()
        if len(empty.get(tree, [])) < budget
    }
    assert not spent, (
        "these trees are now BELOW their recorded budget (actual, budget): "
        f"{spent}. Lower the number here in the same commit, or the tests a fix "
        "removed can be spent back inside a stale tolerance."
    )


def test_the_detector_finds_an_empty_body_and_spares_a_real_one() -> None:
    """Self-test. Every branch is exercised, not merely described above.

    The second half is the one that matters most: this guard is worth having
    only if it leaves real tests alone, because an over-flagging guard is a
    guard somebody switches off, and that is worse than the blindness.
    """
    assert empty_bodies("def test_a():\n    pass\n") == [("test_a", 1)]
    assert empty_bodies('def test_a():\n    """Checks the thing."""\n') == [("test_a", 1)]
    assert empty_bodies("def test_a():\n    ...\n") == [("test_a", 1)]
    assert empty_bodies('def test_a():\n    print("✅ imports fine")\n') == [("test_a", 1)]
    assert empty_bodies(
        'def test_a():\n    """Doc."""\n    pass\n    print("✅ six imports")\n'
    ) == [("test_a", 1)], "the #15189 shape itself: docstring, pass, and prints"
    assert empty_bodies("class TestX:\n    def test_a(self):\n        pass\n")
    assert empty_bodies("async def test_a():\n    pass\n") == [("test_a", 1)]

    # Spared, and each for a different reason.
    assert not empty_bodies(
        "def test_a():\n    subject()\n"
    ), "a call is a real check — it can raise, which is a thin assertion but a real one"
    assert not empty_bodies(
        "def test_a():\n    print(subject())\n"
    ), "print(subject()) evaluates subject() first — a real call, not print('literal') (#15263)"
    assert not empty_bodies(
        "def test_a():\n    assert subject()\n"
    ), "an assertion is a body"
    assert not empty_bodies(
        'def test_a():\n    """Doc."""\n    reporter.print("x")\n'
    ), "an attribute call is somebody's method, not the no-op builtin"
    assert not empty_bodies(
        "def test_a():\n    with pytest.raises(ValueError):\n        subject()\n"
    ), "a with-block runs its body"
    assert not empty_bodies(
        "def test_a():\n    return True\n"
    ), "a returning test is the sibling guard's subject, not this one's"
    assert not empty_bodies(
        "import pytest\n\n\n@pytest.fixture\ndef test_a():\n    pass\n"
    ), "a fixture that yields nothing is still a fixture"
    assert not empty_bodies(
        "class Helper:\n    def test_a(self):\n        pass\n"
    ), "pytest does not collect a method of a non-Test class"
    for marker in ("skip", 'skipif(True, reason="x")', "xfail"):
        assert not empty_bodies(
            f"import pytest\n\n\n@pytest.mark.{marker}\ndef test_a():\n    pass\n"
        ), f"`{marker}` declares the test does not run — that is honest, not misleading"
    for marker in ("skip", 'skipif(True, reason="x")', "xfail"):
        assert not empty_bodies(
            "import pytest\n\n\n"
            f"@pytest.mark.{marker}\nclass TestX:\n    def test_a(self):\n        pass\n"
        ), (
            f"a class-level `{marker}` exempts its methods the same as a method-level "
            "one — the method never repeats a decorator it inherits (#15263)"
        )
    assert empty_bodies(
        "import pytest\n\n\n@pytest.mark.asyncio\nasync def test_a():\n    pass\n"
    ), "an unrelated marker does not excuse an empty body — asyncio still runs it"
