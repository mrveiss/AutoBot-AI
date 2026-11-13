# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AST detector: a Company OS route that takes the acting identity from the request (#20521).

The acting user or agent comes from the authenticated session or credential and never from the
request body or query. This reads the syntax tree and reports every place a route VALUES a request
field whose name says "who acted" (``created_by``, ``requested_by_agent_id``, ``author_user_id``,
``actor``, ``decided_by``, ``reviewer_*``...).

Separated from the test module so each mechanism can be exercised against synthetic source, in a
contrast pair, rather than only against today's tree.

A field counts as USED, and so as a violation, when a route:

* reads ``<param>.<field>`` anywhere but a comparison, a bare truthiness test or a log call
  (a field that is only logged or compared is an ignored compatibility shim, not an actor);
* lets the whole model flow onward -- passes ``<param>`` itself, ``**``-spreads it, calls
  ``model_dump``/``dict`` on it, or reads it through ``getattr`` -- when the model declares any
  such field;
* reads a route parameter (path, query) that carries such a name.

Not scanned, by name: a plain ``agent_id`` / ``user_id`` field is far more often the subject of a request (the
agent to assign, the member to add) than its actor, and a name alone cannot tell them apart.

Boundary, stated where it is read: models are found by CLASS NAME across every module handed in,
which is the whole ``llc/api`` package plus the model modules its routes import; a request model defined
outside them is not seen. The test module pins that boundary by listing the annotation names no scanned
class resolves. Two classes may share a name: a route resolves the one defined in its own module, else the one
its ``from <module> import <Name>`` names, else (an import that cannot be matched to a scanned module) the
union of every class of that name -- which can report a route that uses the clean one, never miss one.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Iterable, Iterator, Mapping

from tools.lint import _parse_cache as parse_cache

#: A field name that says who acted: ``actor``, ``author_*``, ``reviewer_*`` or anything ``*_by`` / ``*_by_*``.
ACTOR_NAME = re.compile(r"(^|_)(actor|author|reviewer)(_|$)|_by($|_)")

_VERBS = frozenset({"get", "post", "put", "patch", "delete"})
_DUMPS = frozenset({"model_dump", "dict", "model_dump_json", "json", "model_copy", "copy"})
_LOG_NAMES = frozenset({"logger", "log", "logging"})
#: The methods of a logger. ``log.record(...)`` on an audit log is NOT a log call: it persists its arguments.
_LOG_METHODS = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "log"})


@dataclass(frozen=True, order=True)
class Finding:
    """One use of an actor-named request field: where, which field, and by what mechanism."""

    path: str
    function: str
    field: str
    how: str


def _bases(node: ast.ClassDef) -> list[str]:
    """Base class names: ``Base`` and ``module.Base`` alike (a subscripted base such as ``Generic[T]`` is skipped)."""
    return [b.id if isinstance(b, ast.Name) else b.attr for b in node.bases if isinstance(b, (ast.Name, ast.Attribute))]


def _own_fields(node: ast.ClassDef) -> set[str]:
    return {s.target.id for s in node.body if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)}


def collect_models(trees: Iterable[ast.AST], outer: Mapping[str, set[str]] | None = None) -> dict[str, set[str]]:
    """Every class's declared field names, its bases' included, keyed by class name.

    Classes of one name in *trees* are unioned. A base not defined in *trees* is read from *outer* (the models
    of the other modules), so a class may inherit across modules.
    """
    classes: dict[str, list[ast.ClassDef]] = {}
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.setdefault(node.name, []).append(node)

    def fields(name: str, seen: frozenset[str] = frozenset()) -> set[str]:
        nodes = classes.get(name)
        if nodes is None:
            return set((outer or {}).get(name, ()))
        if name in seen:
            return set()
        found: set[str] = set()
        for node in nodes:
            found |= _own_fields(node).union(*(fields(b, seen | {name}) for b in _bases(node)))
        return found

    return {name: fields(name) for name in classes}


def _module_matches(path: str, module: str) -> bool:
    """Whether the scanned file *path* is the module an ``import`` names (a relative import's dots are dropped)."""
    dotted = path[:-3].replace("/", ".") if path.endswith(".py") else path
    dotted = dotted.removesuffix(".__init__")
    return dotted == module or dotted.endswith("." + module)


def _scoped_models(
    tree: ast.AST, models: Mapping[str, set[str]], modules: Mapping[str, ast.AST]
) -> dict[str, set[str]]:
    """The models one module sees: the global census, its imports resolved to the module they name, then its own."""
    scoped = dict(models)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ImportFrom) and node.module):
            continue
        sources = [t for p, t in modules.items() if _module_matches(p, node.module)]
        imported = collect_models(sources, models) if sources else {}
        for alias in node.names:
            if alias.name in imported:
                scoped[alias.asname or alias.name] = imported[alias.name]
    scoped.update(collect_models([tree], scoped))
    return scoped


def _is_route(func: ast.AST) -> bool:
    """A function decorated with ``<router>.get|post|put|patch|delete(...)``."""
    if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return any(
        isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in _VERBS
        for d in func.decorator_list
    )


def _parents(root: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(root) for child in ast.iter_child_nodes(parent)}


def _annotation_names(annotation: ast.AST | None) -> set[str]:
    """Every class name an annotation mentions, however it is wrapped.

    ``ast.walk`` yields every node (Subscript, BinOp, Load, Tuple...), so only the nodes that CARRY a name are
    read: a ``Name`` (``Body``), the attribute of a dotted one (``schemas.Body``) and a string annotation
    (``"Body"``, parsed and read the same way). An un-annotated parameter has no annotation at all.
    """
    if annotation is None:
        return set()
    names: set[str] = set()
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names |= _string_annotation_names(node.value)
    return names


def _string_annotation_names(text: str) -> set[str]:
    try:
        return _annotation_names(parse_cache.parse(text, mode="eval").body)
    except (SyntaxError, ValueError):
        return set()


def _args(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    a = func.args
    return [*a.posonlyargs, *a.args, *a.kwonlyargs]


def _in_log_call(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> bool:
    """Whether the NEAREST enclosing call is a logger's.

    A value passed on into another call inside a log call -- ``logger.info("%s", svc.create(by=body.by))`` -- is
    not logged as it is: it reaches that call, so it is a use. ``logger.info("%s", str(body.by))`` is reported
    too: the detector cannot tell a formatter from a service, and reporting is the safer error.
    """
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.Call):
            func = node.func
            return (
                isinstance(func, ast.Attribute)
                and func.attr in _LOG_METHODS
                and isinstance(func.value, ast.Name)
                and func.value.id in _LOG_NAMES
            )
    return False


def _only_looked_at(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> bool:
    """A comparison operand, a bare truthiness test, or a log argument: the value is not used."""
    parent = parents.get(node)
    if isinstance(parent, ast.Compare):
        return True
    if isinstance(parent, (ast.If, ast.IfExp)) and parent.test is node:
        return True
    return _in_log_call(node, parents)


def _callee_param(node: ast.Name, parents: Mapping[ast.AST, ast.AST], defs: Mapping[str, ast.AST]):  # noqa: ANN202
    """``(function, parameter name)`` when *node* is passed whole to a function defined in the scanned module."""
    parent = parents.get(node)
    call = parents.get(parent) if isinstance(parent, ast.keyword) else parent
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in defs):
        return None
    helper = defs[call.func.id]
    if isinstance(parent, ast.keyword):
        return (helper, parent.arg) if parent.arg else None
    positional = [a.arg for a in [*helper.args.posonlyargs, *helper.args.args]]
    index = call.args.index(node) if node in call.args else -1
    return (helper, positional[index]) if 0 <= index < len(positional) else None


def _declares(func: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    """Whether *name* is a named parameter of *func*; one absorbed by ``**kwargs`` cannot be followed."""
    return name in {a.arg for a in _args(func)}


def _uses(func: ast.AST, name: str, defs: Mapping[str, ast.AST], depth: int = 3) -> Iterator[tuple[str, str]]:
    """``(how, field)`` for each way *func* VALUES parameter *name*: ``attr`` / ``dump`` / ``whole``.

    A model handed whole to a helper in the same module is followed into it, so a route that delegates a
    log-and-compare to a helper is judged by what the helper does with it.
    """
    parents = _parents(func)
    for node in ast.walk(func):
        if not (isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load)):
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Attribute) and parent.value is node:
            if parent.attr in _DUMPS:
                yield "dump", parent.attr
            elif not _only_looked_at(parent, parents):
                yield "attr", parent.attr
        elif _only_looked_at(node, parents):
            continue
        elif depth and (target := _callee_param(node, parents, defs)) and _declares(target[0], target[1]):
            yield from _uses(target[0], target[1], defs, depth - 1)
        else:
            yield "whole", name


def _model_param_uses(func, models: Mapping[str, set[str]], defs):  # noqa: ANN001, ANN202
    for arg in _args(func):
        classes = _annotation_names(arg.annotation) & set(models)
        declared = set().union(*(models[c] for c in classes)) if classes else set()
        actors = {f for f in declared if ACTOR_NAME.search(f)}
        if not actors:
            continue
        for how, field in _uses(func, arg.arg, defs):
            if how == "attr" and field in actors:
                yield "attr", field
            elif how != "attr":
                yield how, ",".join(sorted(actors))


def _scalar_param_uses(func, defs) -> Iterator[tuple[str, str]]:  # noqa: ANN001
    for arg in _args(func):
        if ACTOR_NAME.search(arg.arg) and any(True for _ in _uses(func, arg.arg, defs)):
            yield "param", arg.arg


_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _nested_defs(func: ast.AST) -> dict[str, ast.AST]:
    """The functions defined inside *func* (a helper the route closes over)."""
    return {n.name: n for n in ast.walk(func) if isinstance(n, _FUNCTIONS) and n is not func}


def _aliases(tree: ast.AST) -> dict[str, str]:
    """``from m import Name as Alias`` -> ``{"Alias": "Name"}``."""
    return {a.asname: a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names if a.asname}


def _route_annotation_names(tree: ast.AST) -> set[str]:
    """Every name a route parameter's annotation mentions, an import alias read as the class it names."""
    aliases = _aliases(tree)
    names: set[str] = set()
    for func in filter(_is_route, ast.walk(tree)):
        for arg in _args(func):
            names |= {aliases.get(n, n) for n in _annotation_names(arg.annotation)}
    return names


def findings_in(
    path: str, tree: ast.AST, models: Mapping[str, set[str]], modules: Mapping[str, ast.AST] | None = None
) -> list[Finding]:
    """Every use, in one module's routes, of a request field or parameter naming the actor."""
    models = _scoped_models(tree, models, modules or {})
    found: list[Finding] = []
    module_defs = {n.name: n for n in getattr(tree, "body", []) if isinstance(n, _FUNCTIONS)}
    for func in ast.walk(tree):
        if not _is_route(func):
            continue
        defs = {**module_defs, **_nested_defs(func)}
        uses = [*_model_param_uses(func, models, defs), *_scalar_param_uses(func, defs)]
        found.extend(Finding(path, func.name, field, how) for how, field in uses)
    return sorted(set(found))


def declared_actor_fields(trees: Mapping[str, ast.AST], models: Mapping[str, set[str]]) -> set[tuple[str, str]]:
    """Every ``(class, field)`` a route's request model declares with an actor-like name -- used or not.

    This is the census the baseline is read against: it shows what the detector can SEE, so a fixed
    field that was removed and one the detector never reached are told apart.
    """
    bound: set[str] = set()
    for tree in trees.values():
        bound |= _route_annotation_names(tree) & set(models)
    return {(c, f) for c in bound for f in models[c] if ACTOR_NAME.search(f)}


def unresolved_annotations(trees: Mapping[str, ast.AST], models: Mapping[str, set[str]]) -> set[str]:
    """Capitalised annotation names on route parameters that no scanned class resolves: the boundary."""
    names: set[str] = set()
    for tree in trees.values():
        names |= {n for n in _route_annotation_names(tree) if n[:1].isupper()}
    return names - set(models)


def parse_all(sources: Mapping[str, str]) -> dict[str, ast.AST]:
    return {path: parse_cache.parse(text, path) for path, text in sources.items()}


def scan(sources: Mapping[str, str], model_sources: Mapping[str, str] | None = None) -> list[Finding]:
    """Findings across route *sources* (``path -> text``).

    Request models are resolved across the routes AND *model_sources*, modules that define models the
    routes import but are not themselves scanned for routes.
    """
    trees = parse_all(sources)
    modules = {**parse_all(model_sources or {}), **trees}
    models = collect_models(modules.values())
    return sorted(f for path, tree in trees.items() for f in findings_in(path, tree, models, modules))
