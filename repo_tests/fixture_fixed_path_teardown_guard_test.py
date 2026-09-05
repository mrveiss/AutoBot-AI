# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A test fixture that creates AND removes a fixed filesystem path (#15785).

    @pytest.fixture
    def temp_allowed_dir(tmp_path):                       # tmp_path taken, ignored
        test_dir = Path("/tmp/autobot/test_security")     # fixed, shared, process-wide
        test_dir.mkdir(parents=True, exist_ok=True)
        yield test_dir
        shutil.rmtree(test_dir)                           # unconditional

Two concurrent shards running this fixture at once delete each other's
directory: shard A's teardown removes the directory shard B is mid-test with.
In ``mcp_security_test.py`` that turned a dangling symlink chain into one that
*resolved* under the allowed root, which flipped a security assertion from
"blocked" to "an escape got through" -- the wrong answer was "the security
control failed" (#15785's own writeup). Fixed in #15772 by giving the leaf a
per-test suffix from ``tmp_path.name``.

The AST scanner itself lives in ``fixture_fixed_path_teardown_guard.py``, a
plain (non-``_test.py``) sibling module (the same split as
``sys_modules_leak_guard.py`` / ``sys_modules_leak_guard_test.py``), so the
scanner's own growth does not also have to fit under this module's line
budget. This module documents the guard's rationale and carries every
assertion and contrast fixture.

THE DISCRIMINATOR IS CREATE-AND-REMOVE, NOT A BARE FIXED PATH
-----------------------------------------------------------------
``api/codebase_analytics/endpoints/report_scoping_test.py:384``
(``Path("/tmp/does-not-need-to-exist")``) and
``services/knowledge/code_graph_provenance_test.py:95``
(``Path("/tmp/unused-13508.json")``) are both fixed, shared paths -- and both
are inert: neither is inside a ``@pytest.fixture`` at all, and neither ever
calls ``mkdir``/``rmtree``. This guard only ever inspects functions decorated
with ``@pytest.fixture``, so both are out of scope by construction, not by an
exemption list.

WHY "UNCONDITIONAL" MATTERS: ``tmp_root_exists`` IN THE SAME FILE
----------------------------------------------------------------------
``mcp_security_test.py``'s own ``tmp_root_exists`` fixture also creates a
fixed, non-``tmp_path``-derived path (``Path(TMP_ROOT)``) and also calls
``shutil.rmtree`` in its teardown -- but only inside ``if created: ...``,
never unconditionally, and cleans up by diffing pre-existing entries the rest
of the time. That is the same shape #15772's fix uses for a genuinely
required fixed root (``ALLOWED_DIRECTORIES`` permits ``/tmp/autobot/`` and
``tmp_path`` sits outside it) -- gating the destructive call behind a
condition, or deriving the leaf from ``tmp_path``, is exactly what stops two
shards from deleting each other's tree. ``_collect_calls`` tracks whether a
call sits inside an ``ast.If``/ternary and only counts an *unguarded* removal
call as the hazard, which is why ``tmp_root_exists`` is not flagged while the
pre-#15772 ``temp_allowed_dir`` is (see the contrast pair below).

WHY THE FIXTURE IS SYNTHETIC, NOT THE LIVE VIOLATION SET
---------------------------------------------------------
The one known instance was fixed in #15772; the live population is zero
(measured below). Seeding this guard's pass/fail from that population would
make it vacuous today and break the moment a violation reappears -- the trap
#15762 records. Every contrast pair is a literal fixture source this file
writes itself.

REACH, NOT FINDINGS (the vacuity floor)
------------------------------------------
The violation count is zero either way, so a scanner that silently examined
no fixtures would print the identical clean line as one that examined every
fixture in the tree. ``_MIN_EXPECTED_FIXTURES_SCANNED`` binds the floor to how
many ``@pytest.fixture`` functions were actually found, not to what they did --
same shape as ``core_router_auth_guard_test.py``'s
``_MIN_EXPECTED_CORE_ROUTERS``. Measured at 1,212+ fixtures across every
tracked ``.py`` file (fixtures live in plain test modules and in
``conftest.py``, so the scan is not limited to ``*_test.py`` filenames); the
floor sits comfortably below that.

THREE FALSE NEGATIVES CLOSED (#15797)
--------------------------------------
``@repo_fixture`` (an aliased import) was invisible to the decorator check,
``if a: rmtree(p) else: rmtree(p)`` counted as guarded because a bare ``if``
does, and reading ``tmp_path`` anywhere in the body was treated as proof the
created/removed path was unique even when it traced to something else
entirely. ``_fixture_alias_names``, ``_if_exhaustively_removes``, and
``_derived_names`` close each one respectively; each has its own contrast
pair below and none may widen what ``tmp_root_exists`` or ``temp_forbidden_dir``
already pass.

TWO MORE GAPS CLOSED IN REVIEW (#15797 follow-up)
----------------------------------------------------
``_if_exhaustively_removes``'s exhaustiveness check used ``ast.walk``, which
descends into a nested ``FunctionDef``/``Lambda`` body -- a branch that only
*defines* ``def cleanup(): shutil.rmtree(p)``, without ever calling it, was
misread as guaranteeing a remove, so an if/else where both branches merely
define such a helper was misclassified as exhaustive removal and could flag a
fixture that never removes anything (a FALSE POSITIVE). ``_walk_current_scope``
closes it by refusing to descend into nested function/lambda bodies at all.

Separately, ``_assignment_pairs`` credited *every* target of a tuple
assignment with derivation the moment *any* value element read ``tmp_path``
(``a, b = tmp_path, Path("/tmp/autobot/fixed")`` marked ``b`` derived too), and
``_call_path_is_derived`` treated *every* argument and keyword of a call as a
path candidate (an unrelated derived keyword could clear a fixed first
argument). Both are FALSE NEGATIVES -- a fixed-path create/remove could evade
the guard whenever an unrelated derived value sat nearby. ``_pair_target_value``
pairs each target element with its matching value element instead, and
``_call_path_is_derived`` now inspects only the receiver (for
``Path.mkdir``/``unlink``/``rmdir``) or the first positional argument (for
``shutil.rmtree``/``os.remove``/``os.makedirs``).
"""

from __future__ import annotations

import ast

import pytest
from repo_tests.fixture_fixed_path_teardown_guard import (
    _MIN_EXPECTED_FIXTURES_SCANNED,
    _REPO,
    _is_violation,
    _iter_pytest_fixtures,
    _scan_repo,
)


@pytest.fixture(scope="module")
def scan_result():
    return _scan_repo()


class TestScanIsNotVacuous:
    """A guard that silently examines nothing would report a clean sweep too."""

    def test_fixture_reach_meets_floor(self, scan_result):
        examined, _violations, _unreadable = scan_result
        assert examined >= _MIN_EXPECTED_FIXTURES_SCANNED, (
            f"only {examined} pytest fixtures were examined, below the recorded floor of "
            f"{_MIN_EXPECTED_FIXTURES_SCANNED} -- every assertion below is vacuous if the "
            "scan itself silently collapsed"
        )

    def test_no_tracked_source_is_unreadable_by_this_guard(self, scan_result):
        _examined, _violations, unreadable = scan_result
        assert (
            not unreadable
        ), f"these tracked sources could not be parsed, so this guard saw NONE of their fixtures: {unreadable}"


class TestFixedPathTeardownGuard:
    def test_no_fixture_creates_and_unconditionally_removes_a_fixed_path(self, scan_result):
        _examined, violations, _unreadable = scan_result
        assert not violations, (
            f"{violations} -- each fixture creates a path that is not derived from tmp_path "
            "(or another per-test unique source) and unconditionally removes it in teardown. "
            "Concurrent shards running this fixture collide (#15785). Derive the leaf from "
            "tmp_path, or gate the removal behind a check the way "
            "mcp_security_test.py's tmp_root_exists does"
        )


class TestKnownInertPlaceholdersStayUnflagged:
    """#15785's own AC: neither placeholder may quietly become a fixture this guard must judge."""

    @pytest.mark.parametrize(
        "relative_path,needle",
        [
            ("autobot-backend/api/codebase_analytics/endpoints/report_scoping_test.py", "does-not-need-to-exist"),
            ("autobot-backend/services/knowledge/code_graph_provenance_test.py", "unused-13508.json"),
        ],
    )
    def test_placeholder_path_is_not_inside_a_fixture(self, relative_path, needle):
        path = _REPO / relative_path
        source = path.read_text(encoding="utf-8")
        needle_line = next(i + 1 for i, line in enumerate(source.splitlines()) if needle in line)
        fixture_lines = {
            lineno
            for func in _iter_pytest_fixtures(ast.parse(source))
            for lineno in (getattr(n, "lineno", None) for n in ast.walk(func))
            if lineno is not None
        }
        assert needle_line not in fixture_lines, (
            f"{relative_path}:{needle_line} is now inside a pytest fixture -- re-evaluate it "
            "against this guard's create-and-remove discriminator instead of assuming it stays inert"
        )


class TestRealFixtureRegressionPins:
    """Pins the guard's classification against the actual fixtures #15772 and #13598 shipped.

    Not the seed for pass/fail (see module docstring) -- an extra check against
    real code already known to be on each side of the line, so a change to the
    discriminator itself is caught here as well as by the synthetic pair below.
    """

    @pytest.mark.parametrize(
        "fixture_name,expected_violation",
        [
            ("temp_allowed_dir", False),  # #15772: unique leaf under the allowed root
            ("temp_forbidden_dir", False),  # tmp_path-derived directly
            ("tmp_root_exists", False),  # #13598: if-guarded / diff-based cleanup, not unconditional
        ],
    )
    def test_mcp_security_fixtures_are_classified_correctly(self, fixture_name, expected_violation):
        path = _REPO / "autobot-backend" / "mcp" / "mcp_security_test.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        (func,) = (f for f in _iter_pytest_fixtures(tree) if f.name == fixture_name)
        assert _is_violation(func) is expected_violation


_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_allowed_dir(tmp_path):
    test_dir = Path("/tmp/autobot/test_security")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    shutil.rmtree(test_dir)
"""

_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_allowed_dir(tmp_path):
    test_dir = Path("/tmp/autobot") / f"test_security_{tmp_path.name}"
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    if test_dir.exists():
        shutil.rmtree(test_dir)
"""


def _only_fixture(source: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    (func,) = _iter_pytest_fixtures(ast.parse(source))
    return func


class TestContrastPair:
    """A guard that never fires passes its own suite -- this proves it can fire."""

    def test_fixed_path_create_and_unconditional_remove_is_flagged(self):
        assert _is_violation(_only_fixture(_HAZARD_SOURCE)) is True

    def test_tmp_path_derived_leaf_is_not_flagged(self):
        assert _is_violation(_only_fixture(_SAFE_SOURCE)) is False


# ============================================================================
# #15797 -- three false negatives closed above, each with its own contrast pair.
# ============================================================================

_ALIAS_HAZARD_SOURCE = """
import shutil
from pathlib import Path
from pytest import fixture as repo_fixture

@repo_fixture
def temp_dir(tmp_path):
    test_dir = Path("/tmp/autobot/alias_hazard")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    shutil.rmtree(test_dir)
"""

_ALIAS_SAFE_SOURCE = """
import shutil
from pytest import fixture as repo_fixture

@repo_fixture(scope="session")
def temp_dir(tmp_path):
    test_dir = tmp_path / "alias_safe"
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    shutil.rmtree(test_dir)
"""


class TestAliasedFixtureDecoratorIsRecognized:
    """Defect 1 (#15797): a bare-name import alias is not seen at all otherwise."""

    def test_aliased_bare_decorator_is_recognized_and_flagged(self):
        func = _only_fixture(_ALIAS_HAZARD_SOURCE)
        assert func.name == "temp_dir"
        assert _is_violation(func) is True

    def test_aliased_call_form_decorator_is_recognized_and_not_flagged(self):
        func = _only_fixture(_ALIAS_SAFE_SOURCE)
        assert func.name == "temp_dir"
        assert _is_violation(func) is False


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
    """

    def test_removal_on_every_branch_of_if_else_is_flagged(self):
        assert _is_violation(_only_fixture(_EXHAUSTIVE_HAZARD_SOURCE)) is True

    def test_removal_on_a_single_unmatched_branch_stays_conditional(self):
        assert _is_violation(_only_fixture(_EXHAUSTIVE_SAFE_SOURCE)) is False


_TRACED_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    tmp_path.exists()
    Path("/tmp/autobot/traced_hazard").mkdir(parents=True, exist_ok=True)
    yield
    shutil.rmtree("/tmp/autobot/traced_hazard")
"""

_TRACED_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    tmp_path.exists()
    test_dir = tmp_path / "traced_safe"
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    shutil.rmtree(test_dir)
"""


class TestTmpPathMustBeTracedIntoThePath:
    """Defect 3 (#15797): reading ``tmp_path`` elsewhere must not launder a fixed path."""

    def test_incidental_tmp_path_reference_does_not_clear_a_fixed_path(self):
        assert _is_violation(_only_fixture(_TRACED_HAZARD_SOURCE)) is True

    def test_tmp_path_actually_used_to_build_the_path_is_recognized(self):
        assert _is_violation(_only_fixture(_TRACED_SAFE_SOURCE)) is False


# ============================================================================
# Review follow-up on #15797: two more gaps, each with its own contrast pair.
# ============================================================================

_NESTED_DEF_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path, use_helper_a):
    test_dir = Path("/tmp/autobot/nested_def_safe")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    if use_helper_a:
        def cleanup():
            shutil.rmtree(test_dir)
    else:
        def cleanup():
            shutil.rmtree(test_dir)
"""

_NESTED_DEF_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path, use_helper_a):
    test_dir = Path("/tmp/autobot/nested_def_hazard")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    if use_helper_a:
        shutil.rmtree(test_dir)
    else:
        shutil.rmtree(test_dir)
"""


class TestNestedFunctionDefinitionDoesNotCountAsRemoval:
    """Review finding 1: ``ast.walk`` used to enter nested function/lambda bodies.

    ``_NESTED_DEF_SAFE_SOURCE``'s if/else has both branches merely *define* a
    ``cleanup`` helper that is never called -- nothing is ever removed, so the
    fixture must not be flagged, even though a naive scan of the branch bodies
    would find an ``rmtree`` call inside each. ``_NESTED_DEF_HAZARD_SOURCE``
    is the same shape with the nesting removed -- both branches call
    ``shutil.rmtree`` directly -- to prove the fix does not just always return
    False; a real unconditional removal in the same if/else shape still counts.
    """

    def test_branch_that_only_defines_a_cleanup_helper_is_not_removal(self):
        assert _is_violation(_only_fixture(_NESTED_DEF_SAFE_SOURCE)) is False

    def test_branch_that_directly_calls_remove_is_still_removal(self):
        assert _is_violation(_only_fixture(_NESTED_DEF_HAZARD_SOURCE)) is True


_TUPLE_ASSIGN_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    a, b = tmp_path, Path("/tmp/autobot/tuple_hazard")
    b.mkdir(parents=True, exist_ok=True)
    yield b
    shutil.rmtree(b)
"""

_TUPLE_ASSIGN_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    a, b = tmp_path, tmp_path / "tuple_safe"
    b.mkdir(parents=True, exist_ok=True)
    yield b
    shutil.rmtree(b)
"""


class TestTupleAssignmentDoesNotLeakDerivationAcrossTargets:
    """Review finding 2a: a tuple assignment must pair value elements with the
    matching target, not credit every target because *any* element derives.

    ``_TUPLE_ASSIGN_HAZARD_SOURCE`` pairs ``a`` with the genuinely-derived
    ``tmp_path`` and ``b`` with an unrelated fixed path -- ``b`` must stay
    fixed and the fixture must be flagged. ``_TUPLE_ASSIGN_SAFE_SOURCE`` pairs
    ``b`` with a value that itself derives from ``tmp_path``, proving the
    element-wise pairing still recognizes a correctly-paired derivation.
    """

    def test_unrelated_sibling_in_tuple_assignment_does_not_clear_a_fixed_path(self):
        assert _is_violation(_only_fixture(_TUPLE_ASSIGN_HAZARD_SOURCE)) is True

    def test_correctly_paired_tuple_element_is_still_recognized_as_derived(self):
        assert _is_violation(_only_fixture(_TUPLE_ASSIGN_SAFE_SOURCE)) is False


_CALL_ARG_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    some_derived_thing = tmp_path / "flag"
    test_dir = Path("/tmp/autobot/call_arg_hazard")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    shutil.rmtree(test_dir, ignore_errors=some_derived_thing)
"""

_CALL_ARG_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    some_derived_thing = tmp_path / "flag"
    test_dir = tmp_path / "call_arg_safe"
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    shutil.rmtree(test_dir, ignore_errors=some_derived_thing)
"""


class TestCallArgumentDerivationIsScopedToThePathOperand:
    """Review finding 2b: only the receiver or the known path argument of a
    create/remove call is the path operand -- an unrelated derived keyword
    must not launder a fixed first positional argument.

    ``_CALL_ARG_HAZARD_SOURCE``'s ``ignore_errors`` keyword is derived from
    ``tmp_path`` but the actual removed path is fixed -- it must stay flagged.
    ``_CALL_ARG_SAFE_SOURCE`` has the same unrelated derived keyword sitting
    beside a path that is itself genuinely derived, proving the scoped check
    still recognizes derivation when it belongs to the real path argument.
    """

    def test_unrelated_derived_keyword_does_not_clear_the_fixed_path_argument(self):
        assert _is_violation(_only_fixture(_CALL_ARG_HAZARD_SOURCE)) is True

    def test_actual_path_argument_being_derived_is_still_recognized(self):
        assert _is_violation(_only_fixture(_CALL_ARG_SAFE_SOURCE)) is False
