# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The contrast half of the fixed-path teardown guard: what it must and must not flag (#15797).

``fixture_fixed_path_teardown_guard_test.py`` runs the scanner over the live
tree, which is green -- and a scanner that has only ever been shown a green
tree has proved nothing: it could return an empty violation list
unconditionally and every one of those assertions would still pass. The repo
standard is a contrast pair per defect closed. That module documents the
guard's rationale; this one holds the synthetic fixtures for which calls and
decorators the scanner sees at all, and
``fixture_fixed_path_teardown_guard_derivation_test.py`` holds those for how a
name earns "derived" -- so no module has to fit all three under
``check_python_file_size.py``'s MAX_LINES (the same split as
``ansible_manifest_resolution_contrast_test.py``).

Nothing here reads the repository. Every fixture below is a literal source
string this module writes itself -- seeding the pairs from the live population
(zero violations since #15772) would make them vacuous today and break the
moment a violation reappeared, the trap #15762 records.

Each pair is deliberately two-sided. A fix that closes a false negative by
flagging more is only correct if the fixture that must NOT be flagged still
passes: a guard that fires on correct code gets switched off, and every later
verdict it would have given goes missing with it.

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

TWO SCOPE LEAKS AT THE REMAINING CALL SITES (#15797 second review)
---------------------------------------------------------------------
``_walk_current_scope`` landed at one call site only. ``_collect_calls`` and
``_assignment_pairs`` still descended into nested ``def``/``lambda`` bodies,
each in its own direction. A never-called ``def cleanup():
shutil.rmtree(fixed)`` at the fixture's own top level counted as the teardown
it never performs (a FALSE POSITIVE -- ``_collect_calls``' ``guarded`` flag
already excused the same helper when it sat inside an ``if``, which is why the
nested-def pair above passed while this shape did not). A nested helper's local
``test_dir = tmp_path / "leaf"`` marked an OUTER, fixed ``test_dir`` derived,
excusing a real violation (a FALSE NEGATIVE). Both now walk the fixture's own
scope. The ``_collect_calls`` half is pinned here; the ``_assignment_pairs``
half, and why ``_expr_is_derived`` keeps ``ast.walk`` for closures, are pinned
in ``fixture_fixed_path_teardown_guard_derivation_test.py`` with the rest of
the derivation pairs.
"""

from __future__ import annotations

import ast

from repo_tests.fixture_fixed_path_teardown_guard import _is_violation, _iter_pytest_fixtures

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


# ============================================================================
# Second review pass on #15797: the two remaining ``ast.walk`` call sites.
# ============================================================================

_DEFERRED_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    test_dir = Path("/tmp/autobot/deferred_safe")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    def cleanup():
        shutil.rmtree(test_dir)
"""

_DEFERRED_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    test_dir = Path("/tmp/autobot/deferred_hazard")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    shutil.rmtree(test_dir)
"""


class TestDeferredRemovalIsNotTheFixturesOwnTeardown:
    """Review finding 3: ``_collect_calls`` descended into nested scopes too.

    ``_NESTED_DEF_SAFE_SOURCE`` above only ever passed because its helper sat
    inside an ``if``, so ``guarded`` excused it -- move the same never-called
    helper to the fixture's own top level and the removal it never performs
    was counted, flagging a fixture that deletes nothing (a FALSE POSITIVE).
    The hazard source is the identical fixture with the removal actually at
    fixture scope, so the fix cannot be "return False more often".
    """

    def test_uncalled_top_level_helper_is_not_counted_as_removal(self):
        assert _is_violation(_only_fixture(_DEFERRED_SAFE_SOURCE)) is False

    def test_the_same_removal_at_fixture_scope_is_still_counted(self):
        assert _is_violation(_only_fixture(_DEFERRED_HAZARD_SOURCE)) is True
