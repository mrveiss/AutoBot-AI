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


def holds_resolver_call(value: ast.AST | None) -> bool:
    """True when *value* is, or contains (e.g. ``{"a": 1, **resolver(x)}``), a resolver call."""
    return value is not None and any(is_resolver_call(n) for n in ast.walk(value))


def _binding_events(node: ast.AST) -> list[tuple[str, bool]]:
    """``(name, binds_a_pin)`` for every plain name *node* (re)binds.

    Any rebinding counts, not only assignments from the resolver: a later
    ``kwargs = {}`` is exactly what unpins a name bound from it earlier.
    """
    if isinstance(node, ast.Assign):
        pinned = holds_resolver_call(node.value)
        return [(t.id, pinned) for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and isinstance(node.target, ast.Name):
        return [(node.target.id, holds_resolver_call(node.value))]
    if isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
        return [(n.id, False) for n in ast.walk(node.target) if isinstance(n, ast.Name)]
    if isinstance(node, ast.withitem) and node.optional_vars is not None:
        return [(n.id, False) for n in ast.walk(node.optional_vars) if isinstance(n, ast.Name)]
    return []


def binding_timeline(scope: ast.AST) -> dict[str, list[tuple[tuple[int, int], bool]]]:
    """Per name, every binding inside *scope* as ``((line, col), binds_a_pin)``, in source order."""
    timeline: dict[str, list[tuple[tuple[int, int], bool]]] = {}
    for node in ast.walk(scope):
        position = (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))
        for name, pinned in _binding_events(node):
            timeline.setdefault(name, []).append((position, pinned))
    for events in timeline.values():
        events.sort(key=lambda event: event[0])
    return timeline


def name_pinned_at(name: str, call: ast.Call, timeline: dict[str, list[tuple[tuple[int, int], bool]]]) -> bool:
    """True when the last binding of *name* before *call* came from the resolver."""
    at = (call.lineno, call.col_offset)
    earlier = [pinned for position, pinned in timeline.get(name, []) if position < at]
    return bool(earlier) and earlier[-1]


def call_carries_pin(call: ast.Call, timeline: dict[str, list[tuple[tuple[int, int], bool]]]) -> bool:
    """True when this call itself passes ``revision=`` or ``**<name pinned at this call>``.

    ``revision=None`` / ``revision=""`` pin nothing and do not count. A name
    counts only if its most recent binding before the call, in source order,
    holds a resolver call -- so ``kwargs = resolver(m); kwargs = {}`` is unpinned.
    """
    for kw in call.keywords:
        if kw.arg == "revision":
            if isinstance(kw.value, ast.Constant) and not kw.value.value:
                continue
            return True
        if kw.arg is None and (
            holds_resolver_call(kw.value)
            or (isinstance(kw.value, ast.Name) and name_pinned_at(kw.value.id, call, timeline))
        ):
            return True
    return False


def is_from_pretrained(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "from_pretrained"


def unpinned_suppressed_calls(source: str) -> list[int]:
    """Lines of suppressed ``from_pretrained`` calls that do not carry a registry pin themselves.

    "The file calls the resolver somewhere" is not the property: a resolver call
    whose result is dropped on the floor pins nothing. Each suppressed call must
    pass ``revision=`` or ``**<name>`` where ``<name>``'s last binding before the
    call, in the same function (module level counts as its own scope), is a
    resolver call.
    """
    marker_lines = set(comment_markers(source))
    module = ast.parse(source)
    scopes = [n for n in ast.walk(module) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))] + [module]
    bad: set[int] = set()
    seen: set[int] = set()
    for scope in sorted(scopes, key=lambda n: -getattr(n, "lineno", 0)):  # innermost first
        timeline = binding_timeline(scope)
        for node in ast.walk(scope):
            if not is_from_pretrained(node) or id(node) in seen:
                continue
            if not any(node.lineno <= ln <= (node.end_lineno or node.lineno) for ln in marker_lines):
                continue
            seen.add(id(node))
            if not call_carries_pin(node, timeline):
                bad.add(node.lineno)
    return sorted(bad)
