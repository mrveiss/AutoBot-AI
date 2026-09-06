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
    with whether anything gates it. ``_walk_current_scope``, ``_collect_calls``
    and ``_collect_loads`` are all filters over it, so the guard has one
    traversal to reason about rather than several that drifted. What counts as
    a gate is decided once, in ``_always_running_child_ids``, and #15820
    inverted its default: a child is unconditional only where the rule NAMES
    the construct as running on every path -- a statement in the scope's own
    statement list, a ``Try.finalbody``, a ``with`` body -- and everything
    else, unrecognised and future syntax included, is gated.

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

# Node types that evaluate every operand they hold, on every path through
# themselves: they introduce no branch of their own, so a call written inside
# one runs exactly when the node does. Naming them is what keeps
# ``shutil.rmtree(test_dir)`` -- an ``Expr`` holding a ``Call`` -- unconditional
# under a rule whose default is "gated". A node type absent from here and from
# ``_ALWAYS_RUNS_FIELDS`` gates every child, which is #15820's whole point.
#
# ``ast.Compare`` is absent on purpose rather than by oversight: ``a < b < c``
# never evaluates ``c`` when the first comparison is false, so it branches.
# ``ast.Assert`` likewise -- ``python -O`` strips the statement entirely.
_UNBRANCHING_NODES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.Module,
    ast.Expr,
    ast.Assign,
    ast.AugAssign,
    ast.AnnAssign,
    ast.NamedExpr,
    ast.Return,
    ast.Delete,
    ast.Raise,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
    ast.Call,
    ast.keyword,
    ast.arguments,
    ast.arg,
    ast.withitem,
    ast.Attribute,
    ast.Subscript,
    ast.Slice,
    ast.BinOp,
    ast.UnaryOp,
    ast.Tuple,
    ast.List,
    ast.Set,
    ast.Dict,
    ast.Starred,
    ast.JoinedStr,
    ast.FormattedValue,
    ast.Name,
    ast.Constant,
)

# A comprehension evaluates the OUTERMOST iterable once, eagerly, and nothing
# else is guaranteed: ``[shutil.rmtree(e) for e in fixed.iterdir()]`` removes
# zero times on an empty directory, and a second ``for`` clause is reached only
# if the first yielded an item. So only ``generators[0]`` is always-running,
# which is a position rather than a field and is handled in code below.
_COMPREHENSION_NODES = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)

# Branching node types -> the fields whose children still run on every path
# through the node. Every other field of these nodes is gated, and so is every
# field of every node type named in neither table.
#
#   ``If``/``IfExp``   the test is evaluated to choose a branch; no branch is.
#   ``For``/``AsyncFor`` the iterable is evaluated once, before any decision
#                      about the body; an empty one runs the body zero times,
#                      and ``orelse`` is skipped by a ``break``.
#   ``While``          the test runs; the body may never.
#   ``Try``            only ``finalbody`` runs on every path out of the
#                      statement. ``handlers`` need a raise, ``orelse`` needs
#                      the absence of one, and ``body`` is the clause whose
#                      whole purpose is that control may leave it early.
#   ``With``           the body runs; a context manager that swallows an
#                      exception does not stop it from being entered. This is
#                      the commonest fixture teardown there is and must keep
#                      flagging.
#   ``Match``          the subject is evaluated; a case needs it to match, and
#                      a ``match`` with no matching case runs nothing at all.
#   ``comprehension``  the iterable of the generator clause the parent already
#                      admitted; ``target`` and ``ifs`` are per-item.
_ALWAYS_RUNS_FIELDS: Dict[type, Tuple[str, ...]] = {
    ast.If: ("test",),
    ast.IfExp: ("test",),
    ast.For: ("iter",),
    ast.AsyncFor: ("iter",),
    ast.While: ("test",),
    # ``body`` as well as ``finalbody``: a try body BEGINS executing whenever the
    # statement is reached, exactly like a scope's own statement list. Within
    # either, a later statement runs only if the earlier ones did not raise --
    # and this model does not track exceptions for plain statement lists, so
    # treating a try body as gated while a plain list is not would be an
    # inconsistency, not extra caution. It made
    # ``try: rmtree(fixed) / except OSError: pass`` a false negative (#15821
    # review). ``handlers`` and ``orelse`` stay gated: both need the body to
    # have raised, or not to have, before they run at all.
    ast.Try: ("body", "finalbody"),
    ast.With: ("items", "body"),
    ast.AsyncWith: ("items", "body"),
    ast.comprehension: ("iter",),
}

# ``match`` is 3.10+ and ``except*`` 3.11+; both are named where they exist and
# default to fully gated where they do not, which is the same answer.
for _name, _fields in (("Match", ("subject",)), ("TryStar", ("body", "finalbody"))):
    _node_type = getattr(ast, _name, None)
    if _node_type is not None:
        _ALWAYS_RUNS_FIELDS[_node_type] = _fields

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
    always_runs = _always_running_child_ids(node)
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _NESTED_SCOPE_NODES):
            continue
        yield from _walk_scope_guarded(child, guarded or id(child) not in always_runs)


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


def _ifexp_exhaustively_removes(node: ast.IfExp) -> bool:
    """True when a remove call is guaranteed on *both* arms of this ternary (#15815 review).

    The ternary mirror of ``_if_exhaustively_removes``, and it has to be
    asked separately because the two errors point in opposite directions.
    ``shutil.rmtree(p) if drop else None`` removes on one arm only, so
    counting it as guaranteed makes an enclosing ``if`` look exhaustive and
    flags a fixture that removes only conditionally -- a FALSE POSITIVE, the
    direction that gets a guard switched off. ``shutil.rmtree(a) if cond else
    shutil.rmtree(b)`` removes either way, so treating *that* as gated
    because it is lexically a ternary would lose a real hazard. Only "every
    arm removes" is exhaustive; the recursion into each arm is
    ``_node_guarantees_remove``, so a chained ternary answers correctly too.
    """
    return _node_guarantees_remove(node.body) and _node_guarantees_remove(node.orelse)


def _node_guarantees_remove(node: ast.AST) -> bool:
    """True if evaluating *node* always reaches a remove call, gating included.

    The guardedness the primitive already carries is the whole point of
    asking through it: a remove call an ``if``/ternary reaches on one branch
    only is not guaranteed by the node that contains it. Discarding the flag
    here -- a plain scan for any remove call in the subtree -- is what let a
    ternary-gated ``shutil.rmtree(p) if drop else None`` satisfy
    ``_branch_removes`` (#15815 review).
    """
    return any(
        not guarded and isinstance(found, ast.Call) and _call_target_name(found) in _REMOVE_CALL_NAMES
        for found, guarded in _walk_scope_guarded(node)
    )


def _branch_removes(stmts: List[ast.stmt]) -> bool:
    """True if a remove call is guaranteed to run somewhere in this statement list."""
    return any(_stmt_guarantees_remove(stmt) for stmt in stmts)


def _stmt_guarantees_remove(stmt: ast.stmt) -> bool:
    """True if *stmt* itself, unconditionally, reaches a remove call.

    This used to carry its own list of statement types that may run zero times
    -- loops, ``try``, ``with`` -- duplicating a rule ``_guarded_child_ids``
    stated differently, and the two disagreeing about loops is #15815's defect.
    There is one rule now: ``_node_guarantees_remove`` walks *stmt* with the
    gating ``_always_running_child_ids`` decides, so a loop body, an ``except``
    handler or a ``match`` case answers False here without this function
    naming any of them, and a ``try``/``finally`` or a ``with`` inside a branch
    answers True -- which the old list got wrong in the conservative direction.

    Only the nested-scope case survives, and only because it cannot be asked of
    the walk: a ``def``/``lambda`` CHILD is skipped by ``_walk_scope_guarded``,
    but the same node handed in as the walk's root is not, and merely defining
    a helper does not run the removal in its body.
    """
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return _node_guarantees_remove(stmt)


def _all_child_ids(node: ast.AST) -> Set[int]:
    """Every direct child of *node* -- the answer for a node that branches nowhere."""
    return {id(child) for child in ast.iter_child_nodes(node)}


def _field_child_ids(node: ast.AST, fields: Tuple[str, ...]) -> Set[int]:
    """The children *node* holds in *fields*, list-valued fields flattened."""
    ids: Set[int] = set()
    for field in fields:
        value = getattr(node, field, None)
        if isinstance(value, list):
            ids |= {id(item) for item in value if isinstance(item, ast.AST)}
        elif isinstance(value, ast.AST):
            ids.add(id(value))
    return ids


def _always_running_child_ids(node: ast.AST) -> Set[int]:
    """Direct children of *node* that run on EVERY path through it; everything else is gated.

    #15820 inverted this. It used to be ``_guarded_child_ids``, a whitelist of
    node types known to be *conditional* -- ``If``, ``IfExp``, then the loops
    -- with everything unnamed assumed to run unconditionally. That default is
    the wrong way round for this guard. Guessing "unconditional" when unsure
    produces a FALSE POSITIVE, a fixture flagged for a removal it performs on
    only some paths; a guard that flags correct code gets switched off, and
    every later verdict it would have produced goes missing with it. Guessing
    "gated" costs one missed violation and leaves the guard running. Measured
    against the whitelist, five shapes were already wrong in that direction --
    a comprehension body, an ``except`` handler, a ``try``/``else``, a ``match``
    case and the right-hand operand of ``or`` -- and every future syntax would
    have arrived the same way, one construct at a time.

    So the rule is now a denylist of always-executes: a child is unconditional
    only if this function names it, and an unrecognised node type -- including
    one no Python release has shipped yet -- gates every child it holds.

    The exhaustive cases are not exceptions to that. They are a second question
    asked of a construct that is otherwise gated: an ``if``/``elif``/``else``
    or a ternary whose EVERY branch removes performs the removal on every path,
    lexically conditional or not, so it widens to all children. That is what
    keeps ``rmtree(a) if cond else rmtree(b)`` counted while ``rmtree(p) if
    drop else None`` stays gated (#15815 review).
    """
    if isinstance(node, ast.If) and _if_exhaustively_removes(node):
        return _all_child_ids(node)
    if isinstance(node, ast.IfExp) and _ifexp_exhaustively_removes(node):
        return _all_child_ids(node)
    if isinstance(node, _COMPREHENSION_NODES):
        return {id(node.generators[0])} if node.generators else set()
    if isinstance(node, ast.BoolOp):
        return {id(node.values[0])} if node.values else set()
    fields = _ALWAYS_RUNS_FIELDS.get(type(node))
    if fields is not None:
        return _field_child_ids(node, fields)
    if isinstance(node, _UNBRANCHING_NODES):
        return _all_child_ids(node)
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
