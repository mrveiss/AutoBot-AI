# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AST scanner backing ``fixture_fixed_path_teardown_guard_test.py`` (#15785, #15797).

Split out from the test module (the same shape as ``sys_modules_leak_guard.py``
/ ``sys_modules_leak_guard_test.py``) so the false-negative fixes landed for
#15797 could grow the scanner without also tripping
``check_python_file_size.py``'s ``MAX_LINES`` on the test module itself.
``fixture_fixed_path_teardown_guard_test.py`` carries the guard's rationale
and the live-tree assertions, and
``fixture_fixed_path_teardown_guard_contrast_test.py``,
``fixture_fixed_path_teardown_guard_derivation_test.py``,
``fixture_fixed_path_teardown_guard_reachability_test.py`` and
``fixture_fixed_path_teardown_guard_gating_test.py`` carry the synthetic
contrast pair for every defect closed -- which calls and decorators are seen at
all, how a name earns "derived", which nested bodies are live code, and which
constructs gate a removal, respectively; this one documents only the AST shapes
each helper recognizes.

The control-flow half -- which nested bodies are reached, which bindings are
dead, and the single scope-walking primitive all of that is built from -- lives
in ``fixture_fixed_path_teardown_flow.py`` (#15810, #15811), so this module is
left with what it alone knows: what a per-test-unique path is, which operand of
a call carries it, and how a name earns "derived" from it.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Dict, Iterator, List, Set, Tuple

from repo_tests.fixture_fixed_path_teardown_flow import (
    _CREATE_CALL_NAMES,
    _REMOVE_CALL_NAMES,
    Scope,
    _call_target_name,
    _collect_calls,
    _collect_loads,
    _dead_bindings,
    _nested_scopes_by_name,
    _walk_current_scope,
)

from autobot_shared.paths import scrubbed_git_env

_REPO = Path(__file__).resolve().parents[1]

# pytest's own per-test-unique path sources. A fixture that actually uses one
# of these to build its path cannot collide across concurrent tests, whatever
# its teardown does.
_UNIQUE_SOURCE_PARAMS = frozenset({"tmp_path", "tmp_path_factory", "tmpdir", "tmpdir_factory"})

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

#: One reached scope: its node, whether reaching it is gated by an if/ternary,
#: and the names that hold a per-test-unique path once inside it.
ReachedScope = Tuple[Scope, bool, Set[str]]


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


def _assignment_pairs(scope: Scope) -> List[Tuple[Set[str], ast.expr, ast.AST]]:
    """(assigned names, right-hand side, owning statement) for every assignment in *scope*'s own scope.

    A nested helper's locals are not the fixture's: ``def leaf(): test_dir =
    tmp_path / "leaf"`` binds a name that exists only inside ``leaf``, yet
    ``ast.walk`` surfaced it as if the fixture had written it, marking an
    outer, fixed ``test_dir`` derived and excusing a real violation
    (#15797 review). ``_walk_current_scope`` keeps the pairs local to *scope*.

    The owning statement rides along so ``_assignments_by_name`` can drop the
    ones ``_dead_bindings`` calls unobservable (#15811) -- by statement rather
    than by value expression, because ``a = b = value`` shares one expression
    between two names that die independently.
    """
    pairs: List[Tuple[Set[str], ast.expr, ast.AST]] = []
    for node in _walk_current_scope(scope):
        if isinstance(node, ast.Assign) and node.value is not None:
            for target in node.targets:
                pairs.extend((names, value, node) for names, value in _pair_target_value(target, node.value))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = {n.id for n in ast.walk(node.target) if isinstance(n, ast.Name)}
            pairs.append((targets, node.value, node))
        elif isinstance(node, ast.NamedExpr):
            pairs.append(({node.target.id}, node.value, node))
    return pairs


def _expr_is_derived(expr: ast.expr, derived: Set[str]) -> bool:
    """True if any name *expr* reads is already known to trace back to a unique source.

    ``ast.walk`` here is deliberate, not the leak fixed at the two call sites
    above (#15797 review). A lambda inside a value expression is a *closure*
    over the enclosing scope, so the names it reads really are this fixture's:
    ``build = lambda name: tmp_path / name`` followed by ``test_dir =
    build("leaf")`` derives genuinely, and refusing to look inside the lambda
    would flag that correct fixture. The reverse shape -- a lambda whose body
    reads a derived name while the lambda itself is used as something other
    than a path -- would need that lambda's *name* to then appear in a path
    expression: of the 1,216 fixtures scanned, 2 contain a lambda beside a
    create/remove call at all, and neither has that shape.
    """
    return any(isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in derived for n in ast.walk(expr))


def _assignments_by_name(scope: Scope) -> Dict[str, List[ast.expr]]:
    """Every *observable* value assigned to each name in *scope*'s own scope, keyed by name.

    ``_assignment_pairs`` yields one entry per assignment; deriving a name
    correctly needs all of that name's assignments together, because a name
    rebound in one branch is only reliably unique if *every* branch made it so
    (#15797 third review). A binding no path can observe -- overwritten by a
    later one with nothing reading it in between -- is dropped here rather
    than counted against the name, which is #15811's false positive.
    """
    dead = _dead_bindings(scope)
    by_name: Dict[str, List[ast.expr]] = {}
    for targets, value, stmt in _assignment_pairs(scope):
        for name in targets:
            if (id(stmt), name) not in dead:
                by_name.setdefault(name, []).append(value)
    return by_name


def _reachably_derived(by_name: Dict[str, List[ast.expr]], seeds: Set[str]) -> Set[str]:
    """Least fixed point: names *some* assignment traces back to a unique source.

    Optimistic on purpose -- it answers "could this name hold a unique path at
    all", which is reachability from *seeds*. ``_withdraw_partly_fixed`` then
    removes the ones where that is not true on every path.
    """
    derived = set(seeds)
    changed = True
    while changed:
        changed = False
        for name, values in by_name.items():
            if name not in derived and any(_expr_is_derived(value, derived) for value in values):
                derived.add(name)
                changed = True
    return derived


def _withdraw_partly_fixed(by_name: Dict[str, List[ast.expr]], derived: Set[str]) -> Set[str]:
    """Drop any name whose observable assignments are not *all* derived (#15797 third review).

    Withdrawal rather than a stricter least fixed point, and the difference is
    a FALSE POSITIVE. Requiring all assignments while building the set up from
    the seeds can never credit a mutually recursive chain -- ``a = tmp_path /
    "x"`` then ``b = a / "y"`` then ``a = b / "z"`` derives on every
    assignment, yet neither name is creditable until the other already is, so
    both stay out and a correct fixture gets flagged. Starting from
    ``_reachably_derived`` and removing only what is contradicted credits that
    chain (each assignment reads a name still in the set) while still dropping
    the name whose other assignment reads nothing derived. The removals
    cascade: a name losing its credit can leave a name derived only from it
    unsupported, so this iterates to a fixed point too.
    """
    derived = set(derived)
    changed = True
    while changed:
        changed = False
        for name in sorted(derived):
            if any(not _expr_is_derived(value, derived) for value in by_name.get(name, ())):
                derived.discard(name)
                changed = True
    return derived


def _named_params(scope: Scope) -> Set[str]:
    """Parameters pytest can inject a fixture into -- by name, never through a star.

    ``*args``/``**kwargs`` are deliberately absent: pytest resolves a fixture
    request from the signature's *named* parameters, so ``def fin(*tmp_path)``
    binds a caller-supplied tuple, not a per-test-unique path, and must not be
    seeded as one.
    """
    args = scope.args
    return {param.arg for param in [*args.args, *args.kwonlyargs, *args.posonlyargs]}


def _scope_params(scope: Scope) -> Set[str]:
    """Every name *scope*'s signature binds, ``*args``/``**kwargs`` included (#15815 review).

    This is the shadowing set, so it is the wider of the two: a star
    parameter binds a value the caller supplies, and a helper written
    ``def fin(*leaf)`` inside a fixture whose own ``leaf`` is ``tmp_path``-
    derived shares nothing with it but the spelling. Omitting star parameters
    left the enclosing credit standing and excused a removal this guard
    cannot vouch for -- a FALSE NEGATIVE.
    """
    starred = {param.arg for param in (scope.args.vararg, scope.args.kwarg) if param is not None}
    return _named_params(scope) | starred


def _scope_derived_names(scope: Scope, inherited: Set[str]) -> Set[str]:
    """Names that trace back to a tmp_path-family source on *every* observable assignment (#15797).

    A unique-source parameter is not proof by itself -- #15772's own pre-fix
    fixture *took* ``tmp_path`` and ignored it. Only a name actually assigned
    from one, transitively (``test_dir = tmp_path / "leaf"``), counts, and
    that fixed point is what ``_call_path_is_derived`` checks the create/remove
    calls against.

    One derived assignment is not enough either: ``test_dir = Path("/fixed")``
    followed by ``if unique: test_dir = tmp_path / "leaf"`` used to credit
    ``test_dir``, so the false branch created and removed a fixed path with the
    violation suppressed -- the exact hazard, unflagged (#15797 third review).
    A name is credited only when every assignment to it in this scope is
    derived; the dead assignment that rule used to over-count is now dropped
    by ``_dead_bindings`` before the fixed point runs (#15811).

    *inherited* carries the enclosing scope's derived names into a nested
    helper the fixture reaches (#15810), minus anything the helper's own
    parameters shadow -- a parameter's value is unknown here, and treating it
    as still-derived would excuse a removal this guard cannot vouch for.
    Shadowing and seeding read different halves of the signature on purpose:
    every bound name shadows (``*args``/``**kwargs`` included), while only a
    *named* parameter can be pytest's own injection (#15815 review).
    """
    by_name = _assignments_by_name(scope)
    seeds = (inherited - _scope_params(scope)) | (_named_params(scope) & _UNIQUE_SOURCE_PARAMS)
    return _withdraw_partly_fixed(by_name, _reachably_derived(by_name, seeds))


def _derived_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> Set[str]:
    """``_scope_derived_names`` for a fixture, which inherits nothing."""
    return _scope_derived_names(func, set())


def _record_reached(reached: Dict[int, ReachedScope], target: Scope, guarded: bool, inherited: Set[str]) -> bool:
    """Record *target* unless an equal-or-better visit already exists; True if recorded.

    "Better" is unguarded: a helper reached from two places is judged by the
    reference that is not behind an ``if``, because that is the one that runs
    on every path. Only that improvement re-opens a scope, so the walk
    terminates even on mutually recursive helpers.
    """
    seen = reached.get(id(target))
    if seen is not None and not (seen[1] and not guarded):
        return False
    reached[id(target)] = (target, guarded, _scope_derived_names(target, inherited))
    return True


def _reached_scopes(func: ast.FunctionDef | ast.AsyncFunctionDef) -> List[ReachedScope]:
    """The fixture's own scope plus every nested scope its live code actually names (#15810).

    ``def fin(): shutil.rmtree(fixed)`` beside ``request.addfinalizer(fin)``
    removes a fixed path on every path through the fixture, but scoping call
    collection to the fixture's own body (#15809, the fix for a never-called
    helper counting as teardown) made that removal invisible. The discriminator
    is the *reference*: a nested body whose name the enclosing scope reads is
    live code and folds in; one that is only defined still does not.

    Reference, not call, on purpose -- ``addfinalizer(fin)`` never calls
    ``fin`` in the fixture's own text, and demanding ``fin()`` would miss the
    whole idiom the issue is about. Reachability is transitive (a reached
    helper naming another helper reaches it too) and inner definitions shadow
    outer ones, which is why the frontier carries the definitions in scope.
    """
    root: ReachedScope = (func, False, _derived_names(func))
    reached: Dict[int, ReachedScope] = {}
    frontier: List[Tuple[ReachedScope, Dict[str, List[Tuple[Scope, Set[str]]]]]] = [(root, {})]
    while frontier:
        (scope, guarded, derived), outer = frontier.pop()
        defs = dict(outer)
        defs.update({name: [(t, derived) for t in ts] for name, ts in _nested_scopes_by_name(scope).items()})
        for name, load_guarded in _collect_loads(scope):
            for target, inherited in defs.get(name, ()):
                if target is not scope and _record_reached(reached, target, guarded or load_guarded, inherited):
                    frontier.append((reached[id(target)], defs))
    return [root, *reached.values()]


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


def _reached_calls(func: ast.FunctionDef | ast.AsyncFunctionDef) -> List[Tuple[ast.Call, bool, Set[str]]]:
    """Every call the fixture reaches, with its guardedness and the derived names in force.

    A call inside a reached helper is gated by whichever is gated: the
    reference that reaches the helper, or an ``if`` inside the helper itself.
    The derived set travels with the scope, so a helper whose own local is
    ``tmp_path``-derived is judged against that local, not the fixture's name
    of the same spelling.
    """
    return [
        (call, scope_guarded or call_guarded, derived)
        for scope, scope_guarded, derived in _reached_scopes(func)
        for call, call_guarded in _collect_calls(scope)
    ]


def _creates_and_unconditionally_removes(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    calls = _reached_calls(func)
    creates = any(
        _call_target_name(call) in _CREATE_CALL_NAMES and not _call_path_is_derived(call, derived)
        for call, _guarded, derived in calls
    )
    removes = any(
        _call_target_name(call) in _REMOVE_CALL_NAMES and not guarded and not _call_path_is_derived(call, derived)
        for call, guarded, derived in calls
    )
    return creates and removes


def _is_violation(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
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
