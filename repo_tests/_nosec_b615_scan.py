# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Token and AST discriminators for the B615 suppression guard (#13034).

Split out of `nosec_b615_suppressions_are_registry_backed_13034_test.py` so the
guard's assertions and contrast fixtures stay under the file-size ceiling. The
functions here are pure: they take source text or an AST and know nothing about
the tree being swept.
"""

from __future__ import annotations

import ast
import io
import tokenize

#: The bandit test id the guard is about. Built from parts so that this
#: module's own source carries no occurrence of the marker outside a string.
MARKER = "nosec " + "B615"

#: The registry helper a dynamic call site must consult.
RESOLVER = "pinned_revision_kwargs"


def comment_markers(source: str) -> list[int]:
    """Line numbers of `COMMENT` tokens in *source* that carry the marker.

    `tokenize` is the whole point: it is what separates a suppression from a
    sentence about one. A `STRING` token holding the identical text -- a
    docstring, an error message, a test fixture -- contributes nothing.
    """
    found: list[int] = []
    reader = io.StringIO(source).readline
    for token in tokenize.generate_tokens(reader):
        if token.type == tokenize.COMMENT and MARKER in token.string:
            found.append(token.start[0])
    return found


def is_resolver_call(node: ast.AST) -> bool:
    """True for a call to the registry resolver, by name or by attribute."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == RESOLVER) or (
        isinstance(func, ast.Attribute) and func.attr == RESOLVER
    )


def calls_resolver(module: ast.Module) -> bool:
    """True when this module calls the registry resolver, by name or attribute."""
    return any(is_resolver_call(node) for node in ast.walk(module))


def supplies_pin(value: ast.AST | None) -> bool:
    """True when *value* SUPPLIES the resolver's kwargs: the call itself, or a dict splatting it.

    ``{"use_fast": True, **resolver(x)}`` supplies the pin; ``{"metadata": resolver(x)}``
    and ``resolver(x) if c else {}`` contain the call but do not, so they do not count.
    """
    if is_resolver_call(value):
        return True
    return isinstance(value, ast.Dict) and any(
        key is None and is_resolver_call(item) for key, item in zip(value.keys, value.values)
    )


_SCOPE_BOUNDARIES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)

#: Dict methods that change a splatted mapping in place -- each is a rebinding in effect.
_MUTATORS = frozenset({"pop", "popitem", "clear", "update", "setdefault", "__setitem__", "__delitem__"})

#: Mutators addressing one key: harmless when that key is a constant other than ``revision``.
_KEYED_MUTATORS = frozenset({"pop", "setdefault", "__setitem__", "__delitem__"})

Binding = tuple[tuple[int, int], bool]


def _may_touch_revision(key: ast.AST) -> bool:
    """False only for a constant key other than ``revision`` -- e.g. ``kwargs["cache_dir"] = ...``."""
    return not (isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value != "revision")


def scope_nodes(scope: ast.AST):
    """Every node in *scope*'s own body, not descending into nested defs, lambdas or classes."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, _SCOPE_BOUNDARIES):
            stack.extend(ast.iter_child_nodes(node))


def _bound_names(node: ast.AST) -> list[str]:
    """Names *node* binds, deletes, mutates in place, or hands to another scope."""
    if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
        return [node.id]
    if isinstance(node, ast.Subscript) and isinstance(node.ctx, (ast.Store, ast.Del)):
        return [node.value.id] if isinstance(node.value, ast.Name) and _may_touch_revision(node.slice) else []
    if isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
        return [node.value.id] if isinstance(node.value, ast.Name) else []
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _MUTATORS:
        keyed = node.func.attr in _KEYED_MUTATORS and node.args and not _may_touch_revision(node.args[0])
        return [node.func.value.id] if isinstance(node.func.value, ast.Name) and not keyed else []
    if isinstance(node, ast.ExceptHandler) and node.name:
        return [node.name]
    if isinstance(node, ast.alias):
        return [(node.asname or node.name).split(".")[0]]
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return list(node.names)
    if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
        return [node.name]
    if isinstance(node, ast.MatchMapping) and node.rest:
        return [node.rest]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    return []


def _pinning_target(node: ast.AST) -> str | None:
    """The name a plain ``name = <resolver call>`` (or annotated / walrus form) binds, else None."""
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target, value = node.targets[0], node.value
    elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
        target, value = node.target, node.value
    else:
        return None
    return target.id if isinstance(target, ast.Name) and supplies_pin(value) else None


def binding_table(scope: ast.AST) -> dict[str, list[Binding]]:
    """Per name, every binding in *scope*'s own body as ``((line, col), is_a_resolver_pin)``.

    Every binding form counts -- tuple unpack, augmented assignment, ``del``,
    ``except ... as``, imports, ``for``/``with`` targets, match captures,
    ``global``/``nonlocal`` and in-place dict mutation -- because any of them
    can replace or empty a pin bound earlier.
    """
    table: dict[str, list[Binding]] = {}
    pins: dict[str, tuple[int, int]] = {}
    for node in scope_nodes(scope):
        name = _pinning_target(node)
        if name is not None:
            pins[name] = (node.lineno, node.col_offset)
    for node in scope_nodes(scope):
        for name in _bound_names(node):
            position = (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))
            table.setdefault(name, []).append((position, False))
    for name, at in pins.items():
        events = table.get(name, [])
        # The target Name of the pinning statement shares its exact position; mark only that one.
        table[name] = [(pos, pinned or pos == at) for pos, pinned in events]
    return table


def name_pinned_at(name: str, call: ast.Call, table: dict[str, list[Binding]]) -> bool:
    """True only when *name* has EXACTLY ONE binding in its scope: a resolver call, before *call*.

    Any second binding -- conditional, in a loop, in a handler, after the load
    -- makes the name unpinned. Ordering by position cannot follow control
    flow, so the rule refuses to try.
    """
    events = table.get(name, [])
    if len(events) != 1:
        return False
    position, pinned = events[0]
    return pinned and position < (call.lineno, call.col_offset)


def call_carries_pin(call: ast.Call, table: dict[str, list[Binding]]) -> bool:
    """True when this call itself passes ``revision=`` or ``**<name pinned at this call>``.

    ``revision=None`` / ``revision=""`` pin nothing and do not count.
    """
    for kw in call.keywords:
        if kw.arg == "revision":
            if isinstance(kw.value, ast.Constant) and not kw.value.value:
                continue
            return True
        if kw.arg is None and (
            supplies_pin(kw.value) or (isinstance(kw.value, ast.Name) and name_pinned_at(kw.value.id, call, table))
        ):
            return True
    return False


def is_from_pretrained(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "from_pretrained"


def unpinned_suppressed_calls(source: str) -> list[int]:
    """Lines of suppressed ``from_pretrained`` calls that do not carry a registry pin themselves.

    "The file calls the resolver somewhere" is not the property: a resolver call
    whose result is dropped on the floor pins nothing. Each suppressed call must
    pass ``revision=`` or ``**<name>`` where ``<name>`` is bound exactly once in
    the call's own function (module level counts as its own scope), from a
    resolver call, before the call.
    """
    marker_lines = set(comment_markers(source))
    module = ast.parse(source)
    scopes = [n for n in ast.walk(module) if isinstance(n, _SCOPE_BOUNDARIES)] + [module]
    bad: set[int] = set()
    seen: set[int] = set()
    for scope in sorted(scopes, key=lambda n: -getattr(n, "lineno", 0)):  # innermost first
        table = binding_table(scope)
        for node in scope_nodes(scope):
            if not is_from_pretrained(node) or id(node) in seen:
                continue
            if not any(node.lineno <= ln <= (node.end_lineno or node.lineno) for ln in marker_lines):
                continue
            seen.add(id(node))
            if not call_carries_pin(node, table):
                bad.add(node.lineno)
    return sorted(bad)
