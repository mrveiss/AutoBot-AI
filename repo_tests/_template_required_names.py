# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Which variables a Jinja template cannot render without (#20894), shared by the ansible template guards.

Decided per read, not per name: a read is safe when it carries `| default(...)` or an `is defined` test, or sits in a
branch of an `if` whose test guarantees the name (polarity and Boolean structure followed). Template-local `set` and
`for` targets are ordered and scoped. `jinja2.meta.find_undeclared_variables` is not used: it compiles the template,
which needs every ansible-only filter registered, and it cannot tell a guarded read from a bare one.
"""

from __future__ import annotations

from jinja2 import Environment, nodes

_GLOBALS = frozenset(
    {"range", "dict", "lipsum", "cycler", "joiner", "namespace", "loop", "caller", "varargs", "kwargs"}
)
_FALSY_DEFAULTS = ("", False, 0, None)


def _climb(node: nodes.Node, parents: dict[int, nodes.Node]) -> nodes.Node:
    """The expression a read belongs to: `x.stat.exists` and `x['k']` are reads of `x`, so step up through them."""
    while isinstance(parents.get(id(node)), (nodes.Getattr, nodes.Getitem)) and parents[id(node)].node is node:
        node = parents[id(node)]
    return node


def _guards(read: nodes.Name, parents: dict[int, nodes.Node]) -> bool:
    """True when this one read cannot fail on an undefined name: `| default(...)` or an `is defined` test."""
    top = _climb(read, parents)
    parent = parents.get(id(top))
    is_default = isinstance(parent, nodes.Filter) and parent.name in ("default", "d") and parent.node is top
    return is_default or (isinstance(parent, nodes.Test) and parent.name == "defined" and parent.node is top)


def _reads_name_defaulted(expr: nodes.Node, name: str) -> bool:
    """True when *expr* is `name | default(<falsy literal>)`, possibly further filtered (`| length`, `| trim`)."""
    while isinstance(expr, nodes.Filter) and expr.name not in ("default", "d"):
        expr = expr.node
    if not (isinstance(expr, nodes.Filter) and expr.name in ("default", "d")):
        return False
    base = expr.node
    while isinstance(base, (nodes.Getattr, nodes.Getitem)):
        base = base.node
    fallback = expr.args[0] if expr.args else None
    falsy = isinstance(fallback, nodes.Const) and fallback.value in _FALSY_DEFAULTS
    return isinstance(base, nodes.Name) and base.name == name and falsy


def establishes(expr: nodes.Node, name: str, truth: bool) -> bool:
    """True when *expr* being `truth` guarantees *name* is defined: polarity and Boolean structure are followed.

    `x is defined` establishes it when true; `x is not defined` (a `Not` of that) when FALSE; `x | default('')`
    (a falsy fallback) when truthy, also under `| length > 0`; `and` needs one side, `or` needs both.
    """
    if isinstance(expr, nodes.Not):
        return establishes(expr.node, name, not truth)
    if isinstance(expr, nodes.And):
        parts = [establishes(expr.left, name, truth), establishes(expr.right, name, truth)]
        return any(parts) if truth else all(parts)
    if isinstance(expr, nodes.Or):
        parts = [establishes(expr.left, name, truth), establishes(expr.right, name, truth)]
        return all(parts) if truth else any(parts)
    if isinstance(expr, nodes.Test) and expr.name == "defined":
        base = expr.node
        while isinstance(base, (nodes.Getattr, nodes.Getitem)):
            base = base.node
        return truth and isinstance(base, nodes.Name) and base.name == name
    if isinstance(expr, nodes.Compare) and truth and [o.op for o in expr.ops] in (["gt"], ["ne"]):
        return _reads_name_defaulted(expr.expr, name)
    return truth and _reads_name_defaulted(expr, name)


def _under_establishing_if(read: nodes.Name, parents: dict[int, nodes.Node]) -> bool:
    """True when the read is in a branch of an `if`/`elif` that its test makes safe (the body when the test holds,
    the else branch when every test failed). The test itself is not a branch: it is the read being judged."""
    child: nodes.Node = read
    while (parent := parents.get(id(child))) is not None:
        if isinstance(parent, nodes.If):
            if any(child is n for n in parent.body) and establishes(parent.test, read.name, True):
                return True
            if any(child is n for n in parent.else_):
                tests = [parent.test, *(e.test for e in parent.elif_)]
                if any(establishes(t, read.name, False) for t in tests):
                    return True
        child = parent
    return False


def _targets(node: nodes.Node) -> set[str]:
    """Names an assignment target binds: the name itself, or each name of a tuple target (`find_all` skips the root)."""
    return {n.name for n in (node, *node.find_all(nodes.Name)) if isinstance(n, nodes.Name)}


def _unassigned_reads(tree: nodes.Template) -> list[nodes.Name]:
    """Every read of a name that is not a template-local assignment visible at that point.

    Assignments are ordered (`{{ x }}{% set x = 1 %}` reads an external `x`) and a `for` target is scoped to its
    loop; an `if` opens no scope, so a set inside one stays visible after it (the branch taken is not modelled).
    """
    reads: list[nodes.Name] = []

    def seq(stmts: list[nodes.Node], scope: set[str]) -> None:
        for node in stmts:
            visit(node, scope)

    def visit(node: nodes.Node, scope: set[str]) -> None:
        if isinstance(node, nodes.Assign):
            visit(node.node, scope)
            scope |= _targets(node.target)
        elif isinstance(node, nodes.AssignBlock):
            seq(node.body, set(scope))
            scope |= _targets(node.target)
        elif isinstance(node, nodes.For):
            visit(node.iter, scope)
            inner = scope | _targets(node.target) | {"loop"}
            if node.test is not None:
                visit(node.test, inner)
            seq(node.body, inner)
            seq(node.else_, set(scope))
        elif isinstance(node, nodes.If):
            visit(node.test, scope)
            seq(node.body, scope)  # an `if` opens no scope in Jinja: a `set` inside it is visible after it
            seq(node.elif_, scope)
            seq(node.else_, scope)
        elif isinstance(node, nodes.Macro):
            seq(node.body, scope | {a.name for a in node.args})
        elif isinstance(node, nodes.Name):
            if node.ctx == "load" and node.name not in scope and node.name not in _GLOBALS:
                reads.append(node)
        else:
            for child in node.iter_child_nodes():
                visit(child, scope)

    seq(tree.body, set())
    return reads


def required_names(text: str) -> set[str]:
    """Variables the template cannot render without: some read of the name is neither guarded nor in a safe branch.

    Decided per read, not per name: one guarded read does not excuse an unguarded read elsewhere.
    """
    tree = Environment().parse(
        text
    )  # parsing needs no filter table; `meta.find_undeclared_variables` compiles and does
    parents: dict[int, nodes.Node] = {}
    for parent in tree.find_all(nodes.Node):
        for child in parent.iter_child_nodes():
            parents[id(child)] = parent
    return {
        n.name for n in _unassigned_reads(tree) if not _guards(n, parents) and not _under_establishing_if(n, parents)
    }
