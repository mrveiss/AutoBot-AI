# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Contrast pairs for how a name earns "derived" in the fixed-path teardown guard (#15797).

Split out of ``fixture_fixed_path_teardown_guard_contrast_test.py`` when the
conditional-rebinding pair below pushed that module past
``check_python_file_size.py``'s MAX_LINES. The split is topical, not
arithmetic: every pair here exercises ``_derived_names`` and the two helpers it
composes, which decide whether the path a fixture creates and removes is
per-test unique. The other module keeps the pairs about *which* calls and
decorators the scanner sees at all.

The same two rules apply as there. Nothing reads the repository -- every
fixture is a literal source string this module writes itself, because seeding
from the live population (zero violations since #15772) would make the
assertions vacuous today and break the moment a violation reappeared (#15762).
And every pair is two-sided: a fix that closes a false negative by flagging
more is only correct if the fixture that must NOT be flagged still passes, so
each hazard below is shadowed by the nearest correct fixture that must stay
green.

EVERY ASSIGNMENT MUST DERIVE, NOT JUST ONE (#15797 third review)
------------------------------------------------------------------
``_derived_names`` credited a name the moment *any* assignment to it read a
unique source, so ``test_dir = Path("/fixed")`` followed by ``if unique:
test_dir = tmp_path / "leaf"`` marked ``test_dir`` derived and suppressed the
violation -- while the false branch created and removed the fixed path, which
is the exact hazard the guard exists for (a FALSE NEGATIVE). A name now counts
only when every assignment to it in the fixture's own scope derives.

That rule is enforced by withdrawal rather than by a stricter build-up, and
``TestEveryAssignmentToANameMustDerive`` pins why: a mutually recursive chain
where every assignment genuinely derives can never be credited from the seeds
outward, so building the set up under an all-assignments rule would flag a
correct fixture (a FALSE POSITIVE). ``_reachably_derived`` answers the
optimistic question and ``_withdraw_partly_fixed`` removes only what is
contradicted.

NESTED SCOPES AND CLOSURES (#15797 second review)
----------------------------------------------------
``_assignment_pairs`` descended into nested ``def``/``lambda`` bodies, so a
helper's local ``test_dir = tmp_path / "leaf"`` marked an OUTER, fixed
``test_dir`` derived and excused a real violation (a FALSE NEGATIVE). It now
walks the fixture's own scope. ``_expr_is_derived`` keeps ``ast.walk``
deliberately, because a lambda in a value expression closes over this
fixture's names -- ``TestLambdaFactoryDerivationStillCounts`` is what stops
that site being "fixed" the same way.

A DEAD BINDING IS NOT AN ASSIGNMENT ANY PATH MAKES (#15811)
--------------------------------------------------------------
"Every assignment must derive" could not tell a dead assignment from a live
conditional one, so ``test_dir = Path("/fixed")`` immediately overwritten by
``test_dir = tmp_path / "leaf"`` was flagged although every path uses the
derived value (a FALSE POSITIVE -- the direction that gets a guard switched
off). ``_dead_bindings`` drops a binding overwritten by a later one in the same
statement list with no read in between, which is why the conditional rebind
above -- whose overwrite sits in a branch and kills nothing -- is untouched.
And because a reached helper (#15810) now contributes calls, each scope earns
"derived" from its own locals, pinned by
``TestReachedHelperDerivesFromItsOwnScope``.
"""

from __future__ import annotations

import ast

from repo_tests.fixture_fixed_path_teardown_guard import _is_violation, _iter_pytest_fixtures


def _only_fixture(source: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    (func,) = _iter_pytest_fixtures(ast.parse(source))
    return func


_NESTED_LOCAL_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    test_dir = Path("/tmp/autobot/nested_local_hazard")
    test_dir.mkdir(parents=True, exist_ok=True)
    def leaf():
        test_dir = tmp_path / "leaf"
        return test_dir
    yield test_dir
    shutil.rmtree(test_dir)
"""

_NESTED_LOCAL_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    test_dir = tmp_path / "nested_local_safe"
    test_dir.mkdir(parents=True, exist_ok=True)
    def leaf():
        other = Path("/tmp/autobot/nested_local_leaf")
        return other
    yield test_dir
    shutil.rmtree(test_dir)
"""


class TestNestedHelperLocalsDoNotDeriveOuterNames:
    """Review finding 4: ``_assignment_pairs`` walked into nested scopes too.

    A helper's ``test_dir = tmp_path / "leaf"`` binds a name that exists only
    inside the helper, but it marked the fixture's OWN fixed ``test_dir``
    derived -- the created-and-removed path was then excused (a FALSE
    NEGATIVE). The safe source keeps a nested helper with a fixed local of its
    own while the fixture's real path derives from ``tmp_path``, so scoping the
    pairs cannot be achieved by simply ignoring derivation.
    """

    def test_nested_local_does_not_derive_the_outer_fixed_path(self):
        assert _is_violation(_only_fixture(_NESTED_LOCAL_HAZARD_SOURCE)) is True

    def test_outer_derivation_is_still_recognized_beside_a_nested_helper(self):
        assert _is_violation(_only_fixture(_NESTED_LOCAL_SAFE_SOURCE)) is False


_LAMBDA_FACTORY_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    build = lambda name: tmp_path / name
    test_dir = build("lambda_safe")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    shutil.rmtree(test_dir)
"""

_LAMBDA_FACTORY_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    build = lambda name: Path("/tmp/autobot/lambda_hazard") / name
    test_dir = build("leaf")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    shutil.rmtree(test_dir)
"""


class TestLambdaFactoryDerivationStillCounts:
    """Why ``_expr_is_derived`` keeps ``ast.walk`` while the two above dropped it.

    A lambda in a value expression is a closure over the enclosing scope, so
    the names it reads really are the fixture's: ``build = lambda name:
    tmp_path / name`` derives ``build``, and through it ``test_dir``. Teaching
    that site to ignore lambda bodies would stop seeing the derivation and
    flag this correct fixture -- which is what this pair pins. (Merely
    swapping in ``_walk_current_scope`` would not: that helper yields the node
    it is handed and skips only nested *children*, and here the lambda is the
    whole right-hand side.) The hazard source is the identical shape over a
    fixed root and must still be flagged, so the site tracks where the path
    came from rather than excusing anything a lambda touches.
    """

    def test_lambda_factory_over_tmp_path_is_recognized_as_derived(self):
        assert _is_violation(_only_fixture(_LAMBDA_FACTORY_SAFE_SOURCE)) is False

    def test_lambda_factory_over_a_fixed_root_is_still_flagged(self):
        assert _is_violation(_only_fixture(_LAMBDA_FACTORY_HAZARD_SOURCE)) is True


_CONDITIONAL_REBIND_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path, use_unique):
    test_dir = Path("/tmp/autobot/conditional_rebind_hazard")
    if use_unique:
        test_dir = tmp_path / "leaf"
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    shutil.rmtree(test_dir)
"""

_CONDITIONAL_REBIND_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path, use_alt):
    if use_alt:
        test_dir = tmp_path / "conditional_rebind_alt"
    else:
        test_dir = tmp_path / "conditional_rebind_main"
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    shutil.rmtree(test_dir)
"""

_DERIVED_CHAIN_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    test_dir = tmp_path / "chain_root"
    leaf = test_dir / "leaf"
    test_dir = leaf / "deeper"
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    shutil.rmtree(test_dir)
"""


class TestEveryAssignmentToANameMustDerive:
    """Review finding: one derived assignment used to credit the whole name.

    The hazard fixture creates and removes a FIXED path whenever ``use_unique``
    is false -- the guard's whole subject -- yet the ``tmp_path`` rebinding in
    the true branch put ``test_dir`` in ``derived`` and suppressed it (a FALSE
    NEGATIVE). Crediting only names whose every assignment derives closes it
    without dominance analysis.

    Tightening ``derived`` makes flagging MORE likely, so the two safe sources
    carry the weight here. The first is the legitimate shape the rule must not
    break: an ``if``/``else`` where both branches assign a ``tmp_path``-derived
    value is still fully derived and must stay green. The second pins the
    implementation choice -- ``test_dir`` and ``leaf`` each derive on every
    assignment, but each is creditable only once the other already is, so an
    all-assignments rule applied while building the set up from the seeds would
    credit neither and flag this correct fixture. Withdrawal from
    ``_reachably_derived`` credits it.
    """

    def test_conditional_rebinding_over_a_fixed_initial_value_is_flagged(self):
        assert _is_violation(_only_fixture(_CONDITIONAL_REBIND_HAZARD_SOURCE)) is True

    def test_if_else_with_every_branch_derived_is_not_flagged(self):
        assert _is_violation(_only_fixture(_CONDITIONAL_REBIND_SAFE_SOURCE)) is False

    def test_a_chain_that_derives_on_every_assignment_is_not_flagged(self):
        assert _is_violation(_only_fixture(_DERIVED_CHAIN_SAFE_SOURCE)) is False


_DEAD_FIXED_ASSIGNMENT_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    test_dir = Path("/tmp/autobot/dead_fixed_assignment")
    test_dir = tmp_path / "live_leaf"
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    shutil.rmtree(test_dir)
"""

_DEAD_DERIVED_ASSIGNMENT_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    test_dir = tmp_path / "dead_leaf"
    test_dir = Path("/tmp/autobot/live_fixed")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    shutil.rmtree(test_dir)
"""

_READ_BEFORE_OVERWRITE_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(tmp_path):
    test_dir = Path("/tmp/autobot/read_before_overwrite")
    test_dir.mkdir(parents=True, exist_ok=True)
    test_dir = tmp_path / "leaf"
    yield test_dir
    shutil.rmtree(test_dir)
"""


class TestDeadAssignmentsDoNotCountAgainstAName:
    """#15811: "every assignment must derive" could not tell dead from conditional.

    ``_DEAD_FIXED_ASSIGNMENT_SAFE_SOURCE`` reaches its create and its remove
    with a ``tmp_path`` leaf on every path -- the fixed value is overwritten
    before anything can read it -- yet the rule from #15809 withdrew
    ``test_dir`` and flagged a correct fixture (a FALSE POSITIVE, the
    direction that gets a guard switched off). ``_dead_bindings`` drops the
    unobservable binding before the fixed point runs.

    Dropping bindings makes flagging LESS likely, so the two hazard sources
    carry the weight. The first is the same pair in the other order -- the
    derived value is the dead one and the fixed value is what every path uses
    -- so the rule cannot be "ignore the first assignment". The second keeps
    both assignments but reads the fixed value in between (``mkdir`` on it),
    which makes it live and observable; the ordering pin in
    ``TestEveryAssignmentToANameMustDerive`` above covers the conditional
    rebind, where the overwrite sits in a branch and kills nothing.
    """

    def test_dead_fixed_assignment_overwritten_by_a_derived_one_is_not_flagged(self):
        assert _is_violation(_only_fixture(_DEAD_FIXED_ASSIGNMENT_SAFE_SOURCE)) is False

    def test_dead_derived_assignment_overwritten_by_a_fixed_one_is_still_flagged(self):
        assert _is_violation(_only_fixture(_DEAD_DERIVED_ASSIGNMENT_HAZARD_SOURCE)) is True

    def test_a_binding_read_before_the_overwrite_is_not_dead(self):
        assert _is_violation(_only_fixture(_READ_BEFORE_OVERWRITE_HAZARD_SOURCE)) is True


_HELPER_LOCAL_DERIVED_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(request, tmp_path):
    fixed_marker = Path("/tmp/autobot/helper_local_marker")
    fixed_marker.mkdir(parents=True, exist_ok=True)
    def fin():
        leaf = tmp_path / "helper_local_leaf"
        shutil.rmtree(leaf)
    request.addfinalizer(fin)
    yield fixed_marker
"""

_HELPER_LOCAL_FIXED_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(request, tmp_path):
    fixed_marker = Path("/tmp/autobot/helper_local_marker")
    fixed_marker.mkdir(parents=True, exist_ok=True)
    def fin():
        leaf = Path("/tmp/autobot/helper_local_fixed")
        shutil.rmtree(leaf)
    request.addfinalizer(fin)
    yield fixed_marker
"""


class TestReachedHelperDerivesFromItsOwnScope:
    """A reached helper's locals are judged in the helper, not in the fixture.

    Folding a registered finalizer's calls into the fixture (#15810) is only
    correct if the names in those calls are resolved where they are written:
    ``fin``'s own ``leaf = tmp_path / "..."`` is per-test unique and must
    excuse the removal, while the identical shape over a fixed root must not.
    Judging both against the *fixture's* derived names would get one of them
    wrong whichever way that set happened to fall.
    """

    def test_helper_local_derived_from_tmp_path_excuses_its_removal(self):
        assert _is_violation(_only_fixture(_HELPER_LOCAL_DERIVED_SAFE_SOURCE)) is False

    def test_helper_local_over_a_fixed_root_is_still_flagged(self):
        assert _is_violation(_only_fixture(_HELPER_LOCAL_FIXED_HAZARD_SOURCE)) is True


_STAR_PARAM_SHADOW_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(request, tmp_path):
    fixed_marker = Path("/tmp/autobot/star_param_marker")
    fixed_marker.mkdir(parents=True, exist_ok=True)
    leaf = tmp_path / "star_param_leaf"
    def fin(*leaf):
        shutil.rmtree(leaf[0])
    request.addfinalizer(fin)
    yield fixed_marker
"""

_STAR_PARAM_CLOSURE_SAFE_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(request, tmp_path):
    fixed_marker = Path("/tmp/autobot/star_param_marker")
    fixed_marker.mkdir(parents=True, exist_ok=True)
    leaf = tmp_path / "star_param_leaf"
    def fin(*args):
        shutil.rmtree(leaf)
    request.addfinalizer(fin)
    yield fixed_marker
"""

_STAR_PARAM_UNIQUE_NAME_HAZARD_SOURCE = """
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def temp_dir(request):
    fixed_marker = Path("/tmp/autobot/star_param_marker")
    fixed_marker.mkdir(parents=True, exist_ok=True)
    def fin(*tmp_path):
        shutil.rmtree(tmp_path[0])
    request.addfinalizer(fin)
    yield fixed_marker
"""


class TestStarParametersShadowInheritedDerivation:
    """#15815 review: ``*args``/``**kwargs`` bind a name like any other parameter.

    ``_scope_params`` collected only ``args``/``kwonlyargs``/``posonlyargs``,
    and ``_scope_derived_names`` subtracts that set from the names a reached
    helper inherits. A helper written ``def fin(*leaf)`` inside a fixture
    whose own ``leaf`` is ``tmp_path``-derived therefore kept the enclosing
    credit, and ``shutil.rmtree(leaf[0])`` -- a tuple element the caller
    supplied, sharing nothing with the fixture's path but the spelling --
    read as derived and excused itself. A FALSE NEGATIVE, and the docstring
    already claimed the opposite.

    ``_STAR_PARAM_CLOSURE_SAFE_SOURCE`` is the same helper with the star
    parameter named ``args``: ``leaf`` is then a genuine closure over the
    fixture's derived name and must still reach the nested scope, so the fix
    cannot be "a star parameter stops inheritance". Every source here creates
    the SAME fixed marker, so the create side is True in all three and the
    removal verdict is the only thing these assertions can be reading.

    ``_STAR_PARAM_UNIQUE_NAME_HAZARD_SOURCE`` pins the other half of the
    split: shadowing reads every bound name, but seeding reads only
    ``_named_params``, because pytest injects ``tmp_path`` by parameter name
    and never through a star. Widening the seed set along with the shadow set
    would have swapped this false negative for a new one.
    """

    def test_star_parameter_shadows_the_inherited_derived_name(self):
        assert _is_violation(_only_fixture(_STAR_PARAM_SHADOW_HAZARD_SOURCE)) is True

    def test_a_differently_named_star_parameter_keeps_the_closure_derived(self):
        assert _is_violation(_only_fixture(_STAR_PARAM_CLOSURE_SAFE_SOURCE)) is False

    def test_a_star_parameter_named_tmp_path_is_not_pytests_injection(self):
        assert _is_violation(_only_fixture(_STAR_PARAM_UNIQUE_NAME_HAZARD_SOURCE)) is True
