# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Contrast pairs for which nested bodies the fixed-path teardown guard reaches (#15810).

The third topical split of this guard's synthetic pairs, after
``fixture_fixed_path_teardown_guard_contrast_test.py`` (which calls and
decorators the scanner sees at all) and
``fixture_fixed_path_teardown_guard_derivation_test.py`` (how a name earns
"derived"). Every pair here exercises ``_reached_scopes`` and the
``_nested_scopes_by_name``/``_collect_loads`` pairing under it, which decide
whether a nested ``def``/``lambda`` is live code or merely written down.

The same two rules apply as there. Nothing reads the repository -- every
fixture is a literal source string this module writes itself, because seeding
from the live population (zero violations since #15772) would make the
assertions vacuous today and break the moment a violation reappeared (#15762).
And every pair is two-sided: closing a false negative by flagging more is only
correct if the fixture that must NOT be flagged still passes.

A REACHED NESTED BODY IS THE FIXTURE'S OWN TEARDOWN (#15810)
---------------------------------------------------------------
#15809 scoped call collection to the fixture's own body, because a branch that
only *defines* ``def cleanup(): shutil.rmtree(p)`` was being counted as a
teardown it never performs. That left the opposite error open: ``def fin():
shutil.rmtree(fixed)`` beside ``request.addfinalizer(fin)`` removes a fixed
path on every path through the fixture, and the removal sat in a scope the
scanner declined to enter (a FALSE NEGATIVE). ``_reached_scopes`` folds back
exactly the nested bodies the enclosing scope *names* -- reference, not
``def``, because ``addfinalizer(fin)`` never writes ``fin()`` -- so the
never-called helper stays excused and ``request.addfinalizer`` is seen.
"""

from __future__ import annotations

import ast

from repo_tests.fixture_fixed_path_teardown_guard import _is_violation, _iter_pytest_fixtures


def _only_fixture(source: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    (func,) = _iter_pytest_fixtures(ast.parse(source))
    return func


# ============================================================================
# #15810: a nested helper the fixture actually REACHES is its teardown.
# ============================================================================

_FINALIZER_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(request):
    fixed = Path("/tmp/autobot/finalizer_hazard")
    fixed.mkdir(parents=True, exist_ok=True)
    def fin():
        shutil.rmtree(fixed)
    request.addfinalizer(fin)
    yield fixed
"""

_FINALIZER_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(request, tmp_path):
    leaf = tmp_path / "finalizer_safe"
    leaf.mkdir(parents=True, exist_ok=True)
    def fin():
        shutil.rmtree(leaf)
    request.addfinalizer(fin)
    yield leaf
"""

_FINALIZER_UNREGISTERED_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(request):
    fixed = Path("/tmp/autobot/finalizer_unregistered")
    fixed.mkdir(parents=True, exist_ok=True)
    def fin():
        shutil.rmtree(fixed)
    yield fixed
"""

_DIRECT_HELPER_CALL_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir():
    fixed = Path("/tmp/autobot/direct_helper_call")
    fixed.mkdir(parents=True, exist_ok=True)
    yield fixed
    def cleanup():
        shutil.rmtree(fixed)
    cleanup()
"""


_CONDITIONAL_FINALIZER_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(request, register_cleanup):
    fixed = Path("/tmp/autobot/conditional_finalizer")
    fixed.mkdir(parents=True, exist_ok=True)
    def fin():
        shutil.rmtree(fixed)
    if register_cleanup:
        request.addfinalizer(fin)
    yield fixed
"""


class TestReachedNestedHelperIsTheFixturesTeardown:
    """#15810: scoping call collection to the fixture's body hid a registered finalizer.

    ``_DEFERRED_SAFE_SOURCE`` above is why call collection stopped descending
    into nested bodies -- a helper nobody calls removes nothing. The cost was
    the opposite error: ``def fin(): shutil.rmtree(fixed)`` followed by
    ``request.addfinalizer(fin)`` removes a fixed path on every path through
    the fixture, and went unflagged (a FALSE NEGATIVE). The discriminator is
    the *reference*, not the ``def``.

    ``_FINALIZER_UNREGISTERED_SOURCE`` is the hazard source with the
    ``addfinalizer`` line deleted and nothing else changed: it must stay
    green, or the fix is just "descend into nested bodies again" and #15809's
    defect is back. ``_FINALIZER_SAFE_SOURCE`` is the same registration over a
    ``tmp_path`` leaf, so folding the helper in cannot be achieved by flagging
    every finalizer. ``_CONDITIONAL_FINALIZER_SAFE_SOURCE`` registers that same
    helper inside an ``if``: the removal it performs is then no more
    unconditional than the reference that reaches it, the rule
    ``tmp_root_exists`` already relies on.

    ``_FINALIZER_SAFE_SOURCE`` is green on the create side as well -- its
    ``mkdir`` is on the same derived leaf -- so it does not on its own prove
    that the *removal* inside a reached helper is judged against the derived
    names. Reverting the inheritance of derived names into a reached helper
    leaves this test passing; the pin that fails is
    ``TestReachedHelperDerivesFromItsOwnScope`` in
    ``fixture_fixed_path_teardown_guard_derivation_test.py``, whose safe
    source creates a FIXED path and removes a derived one, so the removal
    verdict is the only thing holding it green.
    """

    def test_finalizer_over_a_fixed_path_is_flagged(self):
        assert _is_violation(_only_fixture(_FINALIZER_HAZARD_SOURCE)) is True

    def test_finalizer_over_a_tmp_path_leaf_is_not_flagged(self):
        assert _is_violation(_only_fixture(_FINALIZER_SAFE_SOURCE)) is False

    def test_the_same_helper_never_referenced_is_still_not_a_removal(self):
        assert _is_violation(_only_fixture(_FINALIZER_UNREGISTERED_SOURCE)) is False

    def test_helper_called_directly_in_teardown_is_a_removal(self):
        assert _is_violation(_only_fixture(_DIRECT_HELPER_CALL_SOURCE)) is True

    def test_a_finalizer_registered_only_on_one_branch_stays_conditional(self):
        assert _is_violation(_only_fixture(_CONDITIONAL_FINALIZER_SAFE_SOURCE)) is False
