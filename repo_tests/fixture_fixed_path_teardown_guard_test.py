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
``_MIN_EXPECTED_CORE_ROUTERS``. Measured at 1,209 fixtures across every
tracked ``.py`` file (fixtures live in plain test modules and in
``conftest.py``, so the scan is not limited to ``*_test.py`` filenames); the
floor sits comfortably below that.
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


def _is_pytest_fixture_decorator(node: ast.expr) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Attribute):
        return target.attr == "fixture"
    return isinstance(target, ast.Name) and target.id == "fixture"


def _iter_pytest_fixtures(tree: ast.Module) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(_is_pytest_fixture_decorator(dec) for dec in node.decorator_list):
                yield node


def _guarded_child_ids(node: ast.AST) -> Set[int]:
    """Direct children an ``if``/ternary reaches on only one branch."""
    if isinstance(node, ast.If):
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


def _uses_unique_source(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True if a tmp_path-family parameter is actually referenced, not merely accepted.

    ``temp_allowed_dir(tmp_path)`` pre-#15772 took ``tmp_path`` and never used
    it, so presence alone is not enough -- it must appear as a ``Load`` inside
    the function body.
    """
    params = [*func.args.args, *func.args.kwonlyargs, *func.args.posonlyargs]
    unique_params = {p.arg for p in params} & _UNIQUE_SOURCE_PARAMS
    if not unique_params:
        return False
    used = {n.id for n in ast.walk(func) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    return bool(unique_params & used)


def _creates_and_unconditionally_removes(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    calls = _collect_calls(func)
    creates = any(_call_target_name(call) in _CREATE_CALL_NAMES for call, _guarded in calls)
    removes = any(_call_target_name(call) in _REMOVE_CALL_NAMES and not guarded for call, guarded in calls)
    return creates and removes


def _is_violation(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if _uses_unique_source(func):
        return False
    return _creates_and_unconditionally_removes(func)


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
