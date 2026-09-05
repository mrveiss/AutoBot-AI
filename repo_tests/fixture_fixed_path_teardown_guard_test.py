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
#15762 records. The contrast pair is two literal fixture sources this file
writes itself.

REACH, NOT FINDINGS (the vacuity floor)
------------------------------------------
The violation count is zero either way, so a scanner that silently examined
no fixtures would print the identical clean line as one that examined every
fixture in the tree. ``_MIN_EXPECTED_FIXTURES_SCANNED`` binds the floor to how
many ``@pytest.fixture`` functions were actually found, not to what they did --
same shape as ``core_router_auth_guard_test.py``'s
``_MIN_EXPECTED_CORE_ROUTERS``. Measured at 1,212 fixtures across every
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
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Iterator, List, Set, Tuple

import pytest

from autobot_shared.paths import scrubbed_git_env

_REPO = Path(__file__).resolve().parents[1]

# pytest's own per-test-unique path sources. A fixture that actually uses one
# of these to build its path cannot collide across concurrent tests, whatever
# its teardown does.
_UNIQUE_SOURCE_PARAMS = frozenset({"tmp_path", "tmp_path_factory", "tmpdir", "tmpdir_factory"})

_CREATE_CALL_NAMES = frozenset({"mkdir", "makedirs"})
_REMOVE_CALL_NAMES = frozenset({"rmtree", "unlink", "rmdir", "remove"})

_SKIP_PARTS = {"node_modules", ".worktrees", "__pycache__", "venv", ".venv"}

# Bound to REACH (fixtures actually examined), not to how many violations turn
# up -- see the module docstring.
_MIN_EXPECTED_FIXTURES_SCANNED = 1000


def _fixture_alias_names(tree: ast.Module) -> Set[str]:
    """Local names bound to ``pytest.fixture`` via ``from pytest import fixture as X`` (#15797).

    ``@pytest.fixture`` is recognised on the attribute alone (any module alias
    already works), but a bare-name import loses that: ``@repo_fixture`` carries
    no ``.fixture`` attribute to check, so the alias has to be resolved from the
    module's own imports instead.
    """
    names = {"fixture"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {"pytest", "_pytest.fixtures"}:
            for alias in node.names:
                if alias.name == "fixture":
                    names.add(alias.asname or alias.name)
    return names


def _is_pytest_fixture_decorator(node: ast.expr, fixture_names: Set[str]) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Attribute):
        return target.attr == "fixture"
    return isinstance(target, ast.Name) and target.id in fixture_names


def _iter_pytest_fixtures(tree: ast.Module) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    fixture_names = _fixture_alias_names(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(_is_pytest_fixture_decorator(dec, fixture_names) for dec in node.decorator_list):
                yield node


def _if_exhaustively_removes(node: ast.If) -> bool:
    """True when a remove call is guaranteed on every branch of this if/elif/.../else (#15797).

    ``if use_rmtree: rmtree(p) else: rmtree(p)`` removes either way -- treating
    that as "guarded" because the call sits inside an ``if`` is the false
    negative. An ``if`` with no ``else`` can never be exhaustive: skipping it
    entirely is itself a path with no removal, which is exactly the shape
    ``tmp_root_exists``'s ``if created: ...`` relies on to stay conditional.
    """
    if not node.orelse:
        return False
    if not _branch_removes(node.body):
        return False
    if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
        return _if_exhaustively_removes(node.orelse[0])
    return _branch_removes(node.orelse)


def _branch_removes(stmts: List[ast.stmt]) -> bool:
    """True if a remove call is guaranteed to run somewhere in this statement list."""
    return any(_stmt_guarantees_remove(stmt) for stmt in stmts)


def _stmt_guarantees_remove(stmt: ast.stmt) -> bool:
    """True if *stmt* itself, unconditionally, reaches a remove call.

    A loop, ``try``, or ``with`` may run zero times or raise before the call,
    so a remove call nested inside one is never guaranteed by this statement
    alone -- it stays whatever the enclosing construct already tags it as.
    """
    if isinstance(stmt, ast.If):
        return _if_exhaustively_removes(stmt)
    if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)):
        return False
    return any(_call_target_name(call) in _REMOVE_CALL_NAMES for call in ast.walk(stmt) if isinstance(call, ast.Call))


def _guarded_child_ids(node: ast.AST) -> Set[int]:
    """Direct children an ``if``/ternary reaches on only one branch.

    An exhaustive if/else (every branch removes, see above) contributes no
    guarded ids at all -- the removal it contains is unconditional overall,
    even though it is lexically inside an ``if``.
    """
    if isinstance(node, ast.If):
        if _if_exhaustively_removes(node):
            return set()
        return {id(child) for child in list(node.body) + list(node.orelse)}
    if isinstance(node, ast.IfExp):
        return {id(node.body), id(node.orelse)}
    return set()


def _collect_calls(node: ast.AST, guarded: bool = False) -> List[Tuple[ast.Call, bool]]:
    """Every ``Call`` under *node*, tagged with whether an if/ternary gates it."""
    calls: List[Tuple[ast.Call, bool]] = []
    if isinstance(node, ast.Call):
        calls.append((node, guarded))
    guarded_ids = _guarded_child_ids(node)
    for child in ast.iter_child_nodes(node):
        calls.extend(_collect_calls(child, guarded or id(child) in guarded_ids))
    return calls


def _call_target_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _assignment_pairs(func: ast.FunctionDef | ast.AsyncFunctionDef) -> List[Tuple[Set[str], ast.expr]]:
    """(assigned names, right-hand-side expression) for every simple assignment in *func*."""
    pairs: List[Tuple[Set[str], ast.expr]] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and node.value is not None:
            targets = {n.id for t in node.targets for n in ast.walk(t) if isinstance(n, ast.Name)}
            pairs.append((targets, node.value))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = {n.id for n in ast.walk(node.target) if isinstance(n, ast.Name)}
            pairs.append((targets, node.value))
        elif isinstance(node, ast.NamedExpr):
            pairs.append(({node.target.id}, node.value))
    return pairs


def _expr_is_derived(expr: ast.expr, derived: Set[str]) -> bool:
    """True if any name *expr* reads is already known to trace back to a unique source."""
    return any(isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in derived for n in ast.walk(expr))


def _derived_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> Set[str]:
    """Names that trace back to a tmp_path-family source via simple assignment (#15797).

    A unique-source parameter is not proof by itself -- #15772's own pre-fix
    fixture *took* ``tmp_path`` and ignored it. Only a name actually assigned
    from one, transitively (``test_dir = tmp_path / "leaf"``), counts, and
    that fixed point is what ``_call_path_is_derived`` checks the create/remove
    calls against.
    """
    params = [*func.args.args, *func.args.kwonlyargs, *func.args.posonlyargs]
    derived = {p.arg for p in params} & _UNIQUE_SOURCE_PARAMS
    assignments = _assignment_pairs(func)
    changed = True
    while changed:
        changed = False
        for targets, value in assignments:
            if _expr_is_derived(value, derived) and (targets - derived):
                derived |= targets
                changed = True
    return derived


def _call_path_is_derived(call: ast.Call, derived: Set[str]) -> bool:
    """True if the path *call* operates on -- its object or an argument -- is derived."""
    candidates: List[ast.expr] = list(call.args) + [kw.value for kw in call.keywords]
    if isinstance(call.func, ast.Attribute):
        candidates.append(call.func.value)
    return any(_expr_is_derived(candidate, derived) for candidate in candidates)


def _creates_and_unconditionally_removes(func: ast.FunctionDef | ast.AsyncFunctionDef, derived: Set[str]) -> bool:
    calls = _collect_calls(func)
    creates = any(
        _call_target_name(call) in _CREATE_CALL_NAMES and not _call_path_is_derived(call, derived)
        for call, _guarded in calls
    )
    removes = any(
        _call_target_name(call) in _REMOVE_CALL_NAMES and not guarded and not _call_path_is_derived(call, derived)
        for call, guarded in calls
    )
    return creates and removes


def _is_violation(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return _creates_and_unconditionally_removes(func, _derived_names(func))


def _tracked_python_files() -> List[Path]:
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    ).stdout
    paths = (_REPO / rel for rel in listing.split("\0") if rel.endswith(".py"))
    return [path for path in paths if not _SKIP_PARTS & set(path.relative_to(_REPO).parts)]


def _scan_repo() -> Tuple[int, List[Tuple[Path, str, int]], List[Tuple[Path, str]]]:
    """(fixtures examined, violations, unreadable) across every tracked ``.py`` file."""
    examined = 0
    violations: List[Tuple[Path, str, int]] = []
    unreadable: List[Tuple[Path, str]] = []
    for path in _tracked_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError, OSError) as failure:
            unreadable.append((path, f"{type(failure).__name__}: {failure}"))
            continue
        for func in _iter_pytest_fixtures(tree):
            examined += 1
            if _is_violation(func):
                violations.append((path, func.name, func.lineno))
    return examined, violations, unreadable


@pytest.fixture(scope="module")
def scan_result() -> Tuple[int, List[Tuple[Path, str, int]], List[Tuple[Path, str]]]:
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
