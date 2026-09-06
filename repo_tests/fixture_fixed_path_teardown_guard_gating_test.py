# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which constructs gate a removal, and which run on every path (#15815, #15820).

The gating half of the fixed-path teardown guard's contrast suite, split out of
``fixture_fixed_path_teardown_guard_contrast_test.py`` when #15820 doubled it
-- that module keeps the pairs for which calls and decorators are seen at all,
``..._derivation_test.py`` those for how a name earns "derived", and
``..._reachability_test.py`` those for which nested bodies are live code.
Nothing here reads the repository; every fixture below is a literal source this
module writes itself, for the reason the contrast module's docstring records.

THE DEFAULT WAS THE DEFECT (#15820)
--------------------------------------
``_guarded_child_ids`` was a whitelist of node types known to be *conditional*
-- ``If``, ``IfExp``, then the loops -- and anything unnamed was assumed to run
unconditionally. Measured against it, five shapes were already wrong, every one
in the FALSE POSITIVE direction: a comprehension body, an ``except`` handler, a
``try``/``else``, a ``match`` case and the right-hand operand of ``or`` all read
as unconditional removals although each runs on only some paths. A guard that
flags correct code gets switched off, and every later verdict it would have
produced goes missing with it -- so the default is now the other way round.
``_always_running_child_ids`` names the constructs that run on every path
through their parent and gates everything else, unrecognised and future syntax
included; ``TestUnrecognisedNodeTypesDefaultToGated`` is what stops the next
Python release reintroducing the defect one construct at a time.

Every pair below is built from ``_FIXTURE_TEMPLATE``: the create side is not
merely equivalent across the two halves, it is the identical text, so only the
teardown -- and therefore only the removal verdict -- can move the assertion.
This guard has already shipped a test that passed for a reason unrelated to
what it pinned (``tmp_root_exists`` survived on ternaries being tagged guarded,
which masked the loop gap entirely), so a pair whose create side could decide
its own verdict proves nothing.
"""

from __future__ import annotations

import ast

from repo_tests.fixture_fixed_path_teardown_flow import _always_running_child_ids
from repo_tests.fixture_fixed_path_teardown_guard import _is_violation, _iter_pytest_fixtures

_FIXTURE_TEMPLATE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir({params}):
    test_dir = Path("/tmp/autobot/gating_pair")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
{teardown}
"""


def _only_fixture(source: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    (func,) = _iter_pytest_fixtures(ast.parse(source))
    return func


def _flags_teardown(teardown: str, params: str = "") -> bool:
    """The guard's verdict on a fixture whose only variable is its teardown.

    The fixed path and its ``mkdir`` come from ``_FIXTURE_TEMPLATE`` verbatim,
    so the create half of ``creates and unconditionally removes`` is True in
    every call and cannot be what an assertion below is actually measuring.
    """
    return _is_violation(_only_fixture(_FIXTURE_TEMPLATE.format(params=params, teardown=teardown)))


_BARE_TEARDOWN = "    shutil.rmtree(test_dir)"


# ============================================================================
# #15797 / #15815 -- gating pairs earned before the inversion. These are the
# ones the new default may not regress.
# ============================================================================

_EXHAUSTIVE_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path, use_alt_removal):
    test_dir = Path("/tmp/autobot/exhaustive_hazard")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    if use_alt_removal:
        shutil.rmtree(test_dir)
    else:
        shutil.rmtree(test_dir)
"""

_EXHAUSTIVE_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(created_flag):
    test_dir = Path("/tmp/autobot/exhaustive_safe")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    if created_flag:
        shutil.rmtree(test_dir)
"""


class TestExhaustiveBranchRemovalIsUnconditional:
    """Defect 2 (#15797): remove-on-every-branch must count as unconditional.

    ``_EXHAUSTIVE_SAFE_SOURCE`` mirrors ``tmp_root_exists``'s own shape -- a
    single ``if`` with no ``else`` -- so the fix must not start flagging it.
    Under #15820's inverted default an ``If`` contributes only its ``test`` to
    the always-running set; the exhaustive case is the second question asked of
    a construct that is otherwise gated, and it widens the answer to every
    branch. Losing that widening is what this pair catches.
    """

    def test_removal_on_every_branch_of_if_else_is_flagged(self):
        assert _is_violation(_only_fixture(_EXHAUSTIVE_HAZARD_SOURCE)) is True

    def test_removal_on_a_single_unmatched_branch_stays_conditional(self):
        assert _is_violation(_only_fixture(_EXHAUSTIVE_SAFE_SOURCE)) is False


_TERNARY_GATED_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(flag, drop):
    test_dir = Path("/tmp/autobot/ternary_gated")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    if flag:
        shutil.rmtree(test_dir) if drop else None
    else:
        shutil.rmtree(test_dir)
"""

_TERNARY_EXHAUSTIVE_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(use_root):
    test_dir = Path("/tmp/autobot/ternary_exhaustive")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    shutil.rmtree(test_dir) if use_root else shutil.rmtree(test_dir / "leaf")
"""


class TestTernaryGatingIsDistinguishedFromExhaustion:
    """#15815 review: a ternary-gated removal is not a guaranteed removal.

    ``_stmt_guarantees_remove`` used to fall through to a plain scan of the
    statement, discarding the guardedness the primitive already carried, so
    ``shutil.rmtree(p) if drop else None`` satisfied ``_branch_removes``. In
    ``_TERNARY_GATED_SAFE_SOURCE`` that made the whole if/else look exhaustive
    -- every call in it then read as unconditional, and a fixture that removes
    on one path only was flagged. That is the FALSE POSITIVE direction, the one
    that gets a guard switched off, so it is the half that had to be fixed
    first.

    Refusing every ternary would have closed it by opening the mirror, which
    ``_TERNARY_EXHAUSTIVE_HAZARD_SOURCE`` pins: both arms remove, so a removal
    happens on every path and the fixture is a real hazard.
    ``_ifexp_exhaustively_removes`` asks the ternary the same question
    ``_if_exhaustively_removes`` asks an ``if``, which is what separates the
    two shapes. Both fixtures create the same fixed path, so the create side
    is True either way and only the removal verdict moves these assertions.
    """

    def test_ternary_gated_removal_inside_a_branch_stays_conditional(self):
        assert _is_violation(_only_fixture(_TERNARY_GATED_SAFE_SOURCE)) is False

    def test_ternary_that_removes_on_both_arms_is_flagged(self):
        assert _is_violation(_only_fixture(_TERNARY_EXHAUSTIVE_HAZARD_SOURCE)) is True


_LOOP_BODY_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir():
    test_dir = Path("/tmp/autobot/loop_body")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    for entry in test_dir.iterdir():
        shutil.rmtree(entry)
"""

_FINALLY_TEARDOWN_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir():
    test_dir = Path("/tmp/autobot/finally_teardown")
    test_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield test_dir
    finally:
        shutil.rmtree(test_dir)
"""


class TestLoopBodiesGateARemovalButFinallyDoesNot:
    """#15815 review: the loop rule was stated in one place and not the other.

    ``_stmt_guarantees_remove`` has always said a loop may run zero times, so
    a remove inside one is not guaranteed; the gating rule never said it, so
    the same call read as unguarded in the verdict that matters. The live
    tree's ``tmp_root_exists`` survived only because its ``for entry in ...:
    rmtree(entry) if entry.is_dir() else entry.unlink()`` was read as a gated
    ternary -- and the moment the ternary was judged on its own merits (both
    arms remove, so it is exhaustive) the loop had nothing left holding it and
    a correct fixture was flagged. ``_LOOP_BODY_SAFE_SOURCE`` is that shape
    reduced to the loop alone, so it pins the loop rule rather than the
    ternary's accident. It is also why #15820 removed the duplicate list from
    ``_stmt_guarantees_remove`` entirely: one rule cannot disagree with itself.

    ``_FINALLY_TEARDOWN_HAZARD_SOURCE`` is why ``Try.finalbody`` is named as
    always-running: a ``finally:`` removal runs on every path out of the
    fixture and is the commonest teardown there is. Gating by default must not
    become gating everything, or the guard stops reaching the hazard it was
    written for.
    """

    def test_removal_only_inside_a_loop_body_is_not_unconditional(self):
        assert _is_violation(_only_fixture(_LOOP_BODY_SAFE_SOURCE)) is False

    def test_removal_in_a_finally_block_is_still_unconditional(self):
        assert _is_violation(_only_fixture(_FINALLY_TEARDOWN_HAZARD_SOURCE)) is True


# ============================================================================
# #15820 -- the five shapes the whitelist reported as unconditional, plus the
# default that stops a sixth arriving the same way.
# ============================================================================

_COMPREHENSION_TEARDOWN = "    [shutil.rmtree(entry) for entry in test_dir.iterdir()]"


class TestComprehensionBodyIsGated:
    """A comprehension over an empty iterable evaluates its element zero times.

    Structurally identical to the loop body above, and it was reported the
    opposite way for the whole of the whitelist's life: ``ListComp`` was simply
    not a name anybody had thought to add. Only ``generators[0].iter`` is
    always evaluated now, so the element expression -- and with it the removal
    -- is gated however the comprehension is written.

    The control is the same removal as a plain statement, with the create side
    coming from the identical template text, so a fix that merely stopped
    flagging comprehensions would fail it.
    """

    def test_removal_only_in_a_comprehension_body_is_not_unconditional(self):
        assert _flags_teardown(_COMPREHENSION_TEARDOWN) is False

    def test_the_same_removal_as_a_statement_is_still_unconditional(self):
        assert _flags_teardown(_BARE_TEARDOWN) is True


_EVERY_TRY_CLAUSE = """try:
    body()
except OSError:
    handler()
else:
    no_raise()
finally:
    always()
"""

_EVERY_MATCH_CASE = """match mode:
    case "drop":
        chosen()
    case _:
        wildcard()
"""

_EXCEPT_HANDLER_TEARDOWN = """    try:
        test_dir.exists()
    except OSError:
        shutil.rmtree(test_dir)"""

_FINALLY_CLAUSE_TEARDOWN = """    try:
        test_dir.exists()
    finally:
        shutil.rmtree(test_dir)"""


class TestExceptHandlerIsGated:
    """An ``except`` body runs only if the ``try`` body raised.

    The tightest contrast in this module: the two teardowns differ by one
    clause keyword on the same ``try`` statement, over the same create side, so
    the assertion can only be measuring which clause of a ``Try`` the rule
    names as always-running. ``finalbody`` is named and ``handlers`` is not,
    which is the whole difference between the two verdicts.
    """

    def test_removal_only_in_an_except_handler_is_not_unconditional(self):
        assert _flags_teardown(_EXCEPT_HANDLER_TEARDOWN) is False

    def test_the_same_removal_in_the_finally_clause_is_still_unconditional(self):
        assert _flags_teardown(_FINALLY_CLAUSE_TEARDOWN) is True

    def test_only_the_finally_clause_of_a_try_is_named_as_always_running(self):
        """Pins the clause list itself, because the pair above cannot.

        A handler body is gated twice over -- ``handlers`` is absent from the
        ``Try`` entry AND ``ExceptHandler`` is a node type the rule names
        nowhere -- so reverting either one alone leaves the other holding and
        the pair above still passes. Only reverting both, which is exactly the
        pre-#15820 classification, moves it. That makes the pair evidence for
        the shape but not for the rule, so the rule gets its own assertion:
        every clause of a ``try`` other than ``finally`` is gated, at this one
        point, whatever the clause bodies happen to contain.
        """
        node = ast.parse(_EVERY_TRY_CLAUSE).body[0]
        assert _always_running_child_ids(node) == {id(stmt) for stmt in node.finalbody}


_TRY_ELSE_TEARDOWN = """    try:
        test_dir.exists()
    except OSError:
        pass
    else:
        shutil.rmtree(test_dir)"""


class TestTryElseIsGated:
    """A ``try``/``else`` body runs only if the ``try`` body did NOT raise.

    The mirror of the handler above, and it needs its own pin because it is a
    different field of the same node: naming ``handlers`` while still omitting
    ``orelse`` -- or the reverse -- leaves exactly one of the two shapes
    misreported, and only a per-clause test says which.
    """

    def test_removal_only_in_a_try_else_is_not_unconditional(self):
        assert _flags_teardown(_TRY_ELSE_TEARDOWN) is False

    def test_the_same_removal_in_the_finally_clause_is_still_unconditional(self):
        assert _flags_teardown(_FINALLY_CLAUSE_TEARDOWN) is True


_MATCH_CASE_TEARDOWN = """    match mode:
        case "drop":
            shutil.rmtree(test_dir)"""


class TestMatchCaseIsGated:
    """A ``match`` case runs only on a matching subject -- and none may match.

    ``match`` postdates this guard's original rule by a Python release, which
    is precisely the way the whitelist kept acquiring defects: syntax the rule
    had never heard of defaulted to unconditional. Only ``subject`` is
    evaluated on every path through a ``Match``; every ``case`` is gated,
    including a wildcard one, because the rule declines to reason about
    exhaustiveness it cannot verify.
    """

    def test_removal_only_in_a_match_case_is_not_unconditional(self):
        assert _flags_teardown(_MATCH_CASE_TEARDOWN, params="mode") is False

    def test_the_same_removal_as_a_statement_is_still_unconditional(self):
        assert _flags_teardown(_BARE_TEARDOWN) is True

    def test_only_the_subject_of_a_match_is_named_as_always_running(self):
        """Pins the field list, for the reason the ``try`` pin above records.

        A case body is gated by the ``Match`` entry and again by ``match_case``
        being unnamed, so the pair above survives either revert on its own.
        The wildcard ``case _`` is in the source deliberately: it always
        matches, and the rule still gates it rather than reasoning about an
        exhaustiveness it cannot verify.
        """
        node = ast.parse(_EVERY_MATCH_CASE).body[0]
        assert _always_running_child_ids(node) == {id(node.subject)}


_OR_RIGHT_OPERAND_TEARDOWN = "    flag or shutil.rmtree(test_dir)"
_OR_LEFT_OPERAND_TEARDOWN = "    shutil.rmtree(test_dir) or flag"


class TestShortCircuitOperandIsGated:
    """``or`` evaluates its right operand only when the left one is falsy.

    Both halves are the same ``BoolOp`` over the same two operands with the
    operands swapped, so nothing but position can move the verdict: the first
    operand of a ``BoolOp`` is always evaluated and every later one is gated.
    That two-sidedness is what stops the fix being "refuse every ``BoolOp``",
    which would lose a genuinely unconditional removal written beside a flag.
    """

    def test_removal_as_the_right_operand_of_or_is_not_unconditional(self):
        assert _flags_teardown(_OR_RIGHT_OPERAND_TEARDOWN, params="flag") is False

    def test_removal_as_the_first_operand_is_still_unconditional(self):
        assert _flags_teardown(_OR_LEFT_OPERAND_TEARDOWN, params="flag") is True


_WITH_BODY_TEARDOWN = """    with open(test_dir / "log", "w", encoding="utf-8") as handle:
        shutil.rmtree(test_dir)"""

_WITH_LOOP_TEARDOWN = """    with open(test_dir / "log", "w", encoding="utf-8") as handle:
        for entry in test_dir.iterdir():
            shutil.rmtree(entry)"""


class TestWithBodyRunsOnEveryPath:
    """A ``with`` body is entered whenever the statement is reached.

    The second control the inversion could plausibly have broken -- gating by
    default makes UNDER-flagging the likely error now, and a ``with``-wrapped
    teardown is common enough that losing it would quietly retire the guard.
    ``items`` and ``body`` are both named; the second half shows the naming did
    not become blanket permission, since a loop nested one level inside the
    same ``with`` is still gated.
    """

    def test_removal_in_a_with_body_is_still_unconditional(self):
        assert _flags_teardown(_WITH_BODY_TEARDOWN) is True

    def test_removal_inside_a_loop_within_the_with_body_is_gated(self):
        assert _flags_teardown(_WITH_LOOP_TEARDOWN) is False


_UNNAMED_CONSTRUCT_TEARDOWN = "    assert shutil.rmtree(test_dir) is None"


class _FutureBranch(ast.AST):
    """A node type the rule names nowhere -- the stand-in for syntax not yet shipped."""

    _fields = ("body",)


class TestUnrecognisedNodeTypesDefaultToGated:
    """The pin on the default itself, which is what #15820 actually changed.

    Every other class here pins one construct. This one pins the rule that
    stops the next construct arriving as a false positive at all: a node type
    named in neither ``_ALWAYS_RUNS_FIELDS`` nor ``_UNBRANCHING_NODES``
    contributes no always-running children, so everything it holds is gated.

    ``_FutureBranch`` is a fabricated AST node, deliberately not any real
    syntax -- a test written against a real construct would only pin that
    construct, and the defect being closed is about the ones nobody has
    written yet. ``ast.Assert`` supplies the behavioural half: it is unnamed on
    purpose (``python -O`` strips the statement outright), so a removal that
    exists only inside one is not a removal the guard will vouch for. Both
    halves are checked against a named node so the assertion cannot pass by
    the helper simply returning an empty set for everything.
    """

    def test_a_node_type_the_rule_does_not_name_gates_every_child(self):
        removal = ast.parse("shutil.rmtree(test_dir)").body[0]
        assert _always_running_child_ids(_FutureBranch(body=[removal])) == set()

    def test_a_named_node_type_still_reports_its_children_as_always_running(self):
        removal = ast.parse("shutil.rmtree(test_dir)").body[0]
        assert _always_running_child_ids(removal) == {id(removal.value)}

    def test_removal_only_inside_an_unnamed_construct_is_not_unconditional(self):
        assert _flags_teardown(_UNNAMED_CONSTRUCT_TEARDOWN) is False

    def test_the_same_removal_as_a_statement_is_still_unconditional(self):
        assert _flags_teardown(_BARE_TEARDOWN) is True
