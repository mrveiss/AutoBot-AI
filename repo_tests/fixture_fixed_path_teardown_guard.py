# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AST scanner backing ``fixture_fixed_path_teardown_guard_test.py`` (#15785, #15797).

Split out from the test module (the same shape as ``sys_modules_leak_guard.py``
/ ``sys_modules_leak_guard_test.py``) so the false-negative fixes landed for
#15797 could grow the scanner without also tripping
``check_python_file_size.py``'s ``MAX_LINES`` on the test module itself. The
test module's own docstring carries the guard's rationale and history; this
one documents only the AST shapes each helper recognizes.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Iterator, List, Set, Tuple

from autobot_shared.paths import scrubbed_git_env

_REPO = Path(__file__).resolve().parents[1]

# pytest's own per-test-unique path sources. A fixture that actually uses one
# of these to build its path cannot collide across concurrent tests, whatever
# its teardown does.
_UNIQUE_SOURCE_PARAMS = frozenset({"tmp_path", "tmp_path_factory", "tmpdir", "tmpdir_factory"})

_CREATE_CALL_NAMES = frozenset({"mkdir", "makedirs"})
_REMOVE_CALL_NAMES = frozenset({"rmtree", "unlink", "rmdir", "remove"})

# The path operand of a create/remove call is either its receiver (a Path
# method, called as ``some_path.mkdir(...)``) or its first positional
# argument (a module-level function that takes the path as ``arg[0]``) --
# never "any argument or keyword", which is what let an unrelated derived
# value launder a fixed path elsewhere in the same call (#15797 follow-up).
_RECEIVER_BASED_PATH_CALLS = frozenset({"mkdir", "unlink", "rmdir"})
_FIRST_ARG_PATH_CALLS = frozenset({"rmtree", "remove", "makedirs"})

_SKIP_PARTS = {"node_modules", ".worktrees", "__pycache__", "venv", ".venv"}

# Bound to REACH (fixtures actually examined), not to how many violations turn
# up -- see the test module's docstring.
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


def _walk_current_scope(node: ast.AST) -> Iterator[ast.AST]:
    """Like ``ast.walk``, but never descends into a nested function/lambda body.

    ``def cleanup(): shutil.rmtree(p)`` only *defines* ``cleanup`` -- the
    ``rmtree`` call inside it never runs unless something later calls
    ``cleanup()``. ``ast.walk`` does not know the difference and would
    surface that call as if it executed at the enclosing statement's own
    scope, which is the false positive a defining-but-never-calling branch
    triggers (#15797 follow-up).
    """
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield from _walk_current_scope(child)


def _stmt_guarantees_remove(stmt: ast.stmt) -> bool:
    """True if *stmt* itself, unconditionally, reaches a remove call.

    A loop, ``try``, or ``with`` may run zero times or raise before the call,
    so a remove call nested inside one is never guaranteed by this statement
    alone -- it stays whatever the enclosing construct already tags it as.
    Nor does merely *defining* a nested function or lambda run its body: a
    function/lambda statement (or a value assigned one) is never itself a
    guaranteed remove, no matter what its uncalled body contains.
    """
    if isinstance(stmt, ast.If):
        return _if_exhaustively_removes(stmt)
    if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)):
        return False
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return any(
        _call_target_name(call) in _REMOVE_CALL_NAMES
        for call in _walk_current_scope(stmt)
        if isinstance(call, ast.Call)
    )


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


def _pair_target_value(target: ast.expr, value: ast.expr) -> List[Tuple[Set[str], ast.expr]]:
    """Element-wise (name, value) pairs for one assignment target (#15797 follow-up).

    ``a, b = tmp_path, Path("/tmp/autobot/fixed")`` must credit only ``a`` --
    crediting ``b`` too because *some* element of the value derives is the
    false negative. A tuple/list target is paired against the matching
    element of a same-length tuple/list value, recursively (so nested
    tuples pair correctly too). A value that is not a matching tuple/list
    (a starred target, a length mismatch, or a single expression such as a
    function call feeding a tuple target) cannot be paired element-wise;
    conservatively that yields no pairs at all here rather than crediting
    every name with the whole value, so an un-pairable destructuring never
    marks anything derived that wasn't already.
    """
    if isinstance(target, (ast.Tuple, ast.List)):
        if (
            isinstance(value, (ast.Tuple, ast.List))
            and len(value.elts) == len(target.elts)
            and not any(isinstance(elt, ast.Starred) for elt in target.elts)
        ):
            pairs: List[Tuple[Set[str], ast.expr]] = []
            for t_elem, v_elem in zip(target.elts, value.elts):
                pairs.extend(_pair_target_value(t_elem, v_elem))
            return pairs
        return []
    return [({n.id for n in ast.walk(target) if isinstance(n, ast.Name)}, value)]


def _assignment_pairs(func: ast.FunctionDef | ast.AsyncFunctionDef) -> List[Tuple[Set[str], ast.expr]]:
    """(assigned names, right-hand-side expression) for every simple assignment in *func*."""
    pairs: List[Tuple[Set[str], ast.expr]] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and node.value is not None:
            for target in node.targets:
                pairs.extend(_pair_target_value(target, node.value))
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
    """True if the specific path operand of this create/remove *call* is derived.

    ``shutil.rmtree(Path("/tmp/autobot/fixed"), ignore_errors=some_derived_thing)``
    must read as NOT derived: ``ignore_errors`` is not a path, and treating any
    argument or keyword as a candidate let it launder a fixed first argument
    (#15797 follow-up). Only the one operand each API actually takes as its
    path counts: the receiver for ``Path.mkdir``/``unlink``/``rmdir``, the
    first positional for ``shutil.rmtree``/``os.remove``/``os.makedirs``.
    """
    name = _call_target_name(call)
    if name in _RECEIVER_BASED_PATH_CALLS:
        return isinstance(call.func, ast.Attribute) and _expr_is_derived(call.func.value, derived)
    if name in _FIRST_ARG_PATH_CALLS:
        return bool(call.args) and _expr_is_derived(call.args[0], derived)
    return False


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
