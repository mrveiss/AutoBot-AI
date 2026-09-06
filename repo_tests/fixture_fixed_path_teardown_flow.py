# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The control-flow model under ``fixture_fixed_path_teardown_guard.py`` (#15810, #15811).

Every defect closed in that guard since #15785 has been a question about
*control flow* wearing a different hat, and each was answered with another
bespoke traversal until #15809 left two open in opposite directions:

* a nested helper that IS reached -- ``def fin(): shutil.rmtree(fixed)`` then
  ``request.addfinalizer(fin)`` -- had its removal invisible, because call
  collection was scoped to the fixture's own body (#15810, a FALSE NEGATIVE);
* a **dead** fixed assignment unconditionally overwritten by a derived one was
  flagged, because "every assignment to this name must derive" cannot tell a
  dead assignment from a live conditional one (#15811, a FALSE POSITIVE).

Both fall out of one model, which is what this module is, so neither needed a
fourth and fifth traversal bolted onto the guard. It answers three questions
about a scope, all from a single walking primitive:

``_walk_scope_guarded``
    THE primitive. Every node in one scope -- never descending into a nested
    ``def``/``lambda``, whose body does not run where it is written -- tagged
    with whether an ``if``/ternary gates it. ``_walk_current_scope``,
    ``_collect_calls`` and ``_collect_loads`` are all filters over it, so the
    guard has one traversal to reason about rather than several that drifted.

``_nested_scopes_by_name`` + ``_collect_loads``
    REACHABILITY. A nested scope runs only if the enclosing scope names it,
    so pairing the scopes a body defines against the names that body reads
    tells the guard which nested bodies are live code, and the guardedness of
    the reference tells it whether they run unconditionally (#15810). The
    guard walks that to a fixed point in ``_reached_scopes``.

``_dead_bindings``
    LIVENESS. Within one statement list, a simple binding overwritten by a
    later simple binding with no read of the name in between can never be
    observed -- it is dead, and must not count against the name (#15811).
    The read test is deliberately textual and conservative: any load between
    the two, at any depth including inside a nested body, keeps the earlier
    binding live, so a closure that reads the name (and would in fact see the
    later value) can only ever make the guard flag more, never less.

Both answers stay inside one scope on purpose. The guard composes them across
scopes, because only it knows what a "derived" name is.
"""

from __future__ import annotations

import ast
from typing import Dict, Iterator, List, Set, Tuple

_CREATE_CALL_NAMES = frozenset({"mkdir", "makedirs"})
_REMOVE_CALL_NAMES = frozenset({"rmtree", "unlink", "rmdir", "remove"})

# A nested ``def``/``lambda`` is a scope of its own: its body neither runs nor
# binds names where it is written. The primitive below never descends into one;
# ``_reached_scopes`` in the guard re-enters the ones the code actually names.
_NESTED_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)

#: A scope this model can analyse: a fixture, or a nested helper it reaches.
Scope = ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda


def _call_target_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _walk_scope_guarded(node: ast.AST, guarded: bool = False) -> Iterator[Tuple[ast.AST, bool]]:
    """Every node in *node*'s own scope, tagged with whether an if/ternary gates it.

    The one traversal the rest of this module and the guard are built from.
    Nested ``def``/``lambda`` bodies are skipped because a call or a name
    written inside one does not run or resolve where it is written: a
    never-called ``def cleanup(): shutil.rmtree(p)`` is not a teardown
    (#15797 review), and a helper's local ``test_dir = tmp_path / "leaf"``
    does not bind the fixture's ``test_dir``. ``guarded`` is per branch, so a
    node inside an ``if`` carries the flag while its siblings do not.
    """
    yield node, guarded
    guarded_ids = _guarded_child_ids(node)
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _NESTED_SCOPE_NODES):
            continue
        yield from _walk_scope_guarded(child, guarded or id(child) in guarded_ids)


def _walk_current_scope(node: ast.AST) -> Iterator[ast.AST]:
    """``_walk_scope_guarded`` without the guardedness, for callers that judge it themselves."""
    return (found for found, _guarded in _walk_scope_guarded(node))


def _collect_calls(node: ast.AST) -> List[Tuple[ast.Call, bool]]:
    """Every ``Call`` in *node*'s own scope, tagged with whether an if/ternary gates it."""
    return [(found, guarded) for found, guarded in _walk_scope_guarded(node) if isinstance(found, ast.Call)]


def _collect_loads(node: ast.AST) -> List[Tuple[str, bool]]:
    """Every name *read* in *node*'s own scope, tagged with whether an if/ternary gates it.

    The reachability half of #15810: ``request.addfinalizer(fin)`` reads
    ``fin``, and that read -- not the ``def`` -- is what makes the helper's
    body live code. An unguarded read means the helper runs unconditionally.
    """
    return [
        (found.id, guarded)
        for found, guarded in _walk_scope_guarded(node)
        if isinstance(found, ast.Name) and isinstance(found.ctx, ast.Load)
    ]


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


def _bound_names(node: ast.AST) -> Set[str]:
    """Bare ``Name`` targets *node* binds -- nothing else counts as a simple binding.

    A tuple/subscript/attribute target is deliberately excluded: this feeds
    both the lambda-binding lookup and the dead-binding test, and in the
    latter a killer that only *might* rebind the whole name would kill a live
    assignment. Excluding them keeps every earlier binding live, which can
    only make the guard flag more.
    """
    if isinstance(node, ast.Assign):
        return {target.id for target in node.targets if isinstance(target, ast.Name)}
    if isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and isinstance(node.target, ast.Name):
        return {node.target.id} if node.value is not None else set()
    return set()


def _nested_scopes_by_name(scope: ast.AST) -> Dict[str, List[Scope]]:
    """Name -> the nested ``def``/``lambda`` bodies *scope* binds to it, in its own scope.

    Half of the reachability answer (#15810): these are the bodies that
    *could* run, and ``_collect_loads`` says which of them the code names.
    A ``lambda`` has no name of its own, so it is picked up from whatever
    simple binding it is the value of (``build = lambda name: ...``).
    """
    by_name: Dict[str, List[Scope]] = {}
    for node in _walk_current_scope(scope):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                by_name.setdefault(child.name, []).append(child)
        value = getattr(node, "value", None)
        if isinstance(value, ast.Lambda):
            for name in _bound_names(node):
                by_name.setdefault(name, []).append(value)
    return by_name


def _statement_blocks(scope: ast.AST) -> Iterator[List[ast.stmt]]:
    """Every statement list in *scope*'s own scope -- bodies, else-bodies, finally-bodies.

    A statement list is the unit the dead-binding test works in: within one
    list, statement order IS execution order, so "later" and "in between" are
    answerable without a full CFG. Two bindings in *different* lists are never
    compared, which is what keeps ``if unique: test_dir = tmp_path / "leaf"``
    from being read as killing the fixed value above it (#15797 third review).
    """
    for node in _walk_current_scope(scope):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list) and block and all(isinstance(stmt, ast.stmt) for stmt in block):
                yield block


def _reads_name(nodes: List[ast.AST], name: str) -> bool:
    """True if any of *nodes* reads *name*, at any depth -- nested bodies included.

    Plain ``ast.walk`` on purpose. A closure written between two bindings
    would in fact observe the later value, so counting its read keeps the
    earlier binding live and the fixture flagged: the conservative direction
    for a test that exists to REMOVE flags.
    """
    return any(
        isinstance(found, ast.Name) and isinstance(found.ctx, ast.Load) and found.id == name
        for node in nodes
        for found in ast.walk(node)
    )


def _dead_block_bindings(block: List[ast.stmt]) -> Set[Tuple[int, str]]:
    """``(id(stmt), name)`` for each binding in *block* overwritten before anything reads it.

    Keyed by statement AND name because ``a = b = value`` binds two names from
    one statement and each is killed on its own schedule.
    """
    positions: Dict[str, List[int]] = {}
    for index, stmt in enumerate(block):
        for name in _bound_names(stmt) if isinstance(stmt, (ast.Assign, ast.AnnAssign)) else ():
            positions.setdefault(name, []).append(index)
    dead: Set[Tuple[int, str]] = set()
    for name, indices in positions.items():
        for earlier, later in zip(indices, indices[1:]):
            overwrite = block[later]
            between: List[ast.AST] = [*block[earlier + 1 : later], *filter(None, [overwrite.value])]
            if not _reads_name(between, name):
                dead.add((id(block[earlier]), name))
    return dead


def _dead_bindings(scope: ast.AST) -> Set[Tuple[int, str]]:
    """Every binding in *scope*'s own scope that no execution path can observe (#15811).

    ``test_dir = Path("/fixed")`` followed immediately by ``test_dir =
    tmp_path / "leaf"`` puts a fixed value in a name that every later
    create/remove reads as the derived one; counting the dead assignment
    against the name flagged a correct fixture. Consecutive pairs are enough:
    if a read sits between the first and second binding the first is live and
    stays, and the second is then judged against the third on its own.
    """
    dead: Set[Tuple[int, str]] = set()
    for block in _statement_blocks(scope):
        dead |= _dead_block_bindings(block)
    return dead
