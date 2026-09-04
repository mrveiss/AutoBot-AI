# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The detection engine behind ``unprefixed_placeholder_string_test.py`` (#15589).

Three categories of string that emits its own placeholder syntax, each a finder
over one parsed module and all three sharing a single tree sweep. WHY EACH
CATEGORY IS SHAPED THE WAY IT IS -- the measured populations, the false
positives every narrowing removes, and what would come back if one were
widened -- is recorded in that test module's docstring, next to the assertions
that hold the numbers. Read it before changing a condition here.

This file carries the engine only because the test module reached its 600-line
ceiling; the split is a size decomposition, not a seam. It writes no
replacement field literally, for the reason the test module's docstring gives.
"""

from __future__ import annotations

import ast
import builtins
import string
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
import sys
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, FrozenSet, List, Optional, Set, Tuple

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Directory names that are never repository source under a full-tree sweep.
EXCLUDED_DIR_NAMES = frozenset({".worktrees", "node_modules", "__pycache__", ".venv", "venv"})

#: Nodes a replacement field may be built from. Anything else -- a comparison,
#: a lambda, a walrus -- is not an interpolation someone forgot to prefix.
_ALLOWED_FIELD_NODES: Tuple[type, ...] = (
    ast.Expression,
    ast.Name,
    ast.Attribute,
    ast.Subscript,
    ast.Call,
    ast.Constant,
    ast.Load,
    ast.Slice,
    ast.Tuple,
    ast.List,
    ast.keyword,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.USub,
)

#: At least one of these must appear, or the field is a bare name -- the route
#: decorator shape the first category exists to walk past. The bare half it
#: drops is carried by :func:`companion_interpolations` (#15617) and by
#: :func:`emitted_bare_interpolations` (#15628), not discarded.
#:
#: WHAT THE DROPPED HALF ACTUALLY HOLDS, measured rather than assumed (#15628).
#: 1,452 bare fields stand outside any file this guard flags. Partitioned by
#: shape: 1,201 are decorator path segments naming a parameter of their own
#: handler, 138 have an identifier that is a keyword to a ``format`` call in
#: the same file, 6 are other decorator strings, and 107 are the residue.
#: All 107 were read at their sites. 13 were real missing prefixes; 11 of those
#: stand in an emitted message, which is the shape the fourth category below
#: carries. The remaining 94 are route text outside a decorator (index maps,
#: contract fixtures, path-normalisation sentinels, prose), prompt and HTML
#: templates rendered by a ``format`` call in another module, and quoted
#: JSON/JS fixtures -- none of them an interpolation site. That is why the
#: condition stays: widening it reaches 1,452 strings to find 11.
_REQUIRED_FIELD_NODES: Tuple[type, ...] = (ast.Attribute, ast.Subscript, ast.Call)

#: The conditional-expression shape :data:`_ALLOWED_FIELD_NODES` drops (#15627).
#: A ternary is an ``ast.IfExp`` and its test is ordinarily a comparison or a
#: boolean operator, none of which that set admits, so a field holding one is
#: discarded before any category sees it -- even when its names are bound and
#: even when it sits beside a confirmed finding, which is how ten of them
#: reached the tree. Kept separate rather than merged into the allowed set so
#: the three populations the test module's docstring records keep their counts.
_CONDITIONAL_FIELD_NODES: Tuple[type, ...] = _ALLOWED_FIELD_NODES + (
    ast.IfExp,
    ast.Compare,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
)

#: Calls whose positional arguments carry a message meant for a human to read.
#: A bare identifier here is the only bug-bearing shape in the 1,452 (#15628).
_EMIT_METHODS = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "log", "fatal", "print"}
)

#: Prefixes that mark a quoted f-string *inside* a string -- source code held as
#: data (a generated script, a documented example). Its braces belong to the
#: inner program, not to this one.
_INNER_FSTRING_MARKERS = ('f"', "f'", 'F"', "F'", 'rf"', "rf'", 'fr"', "fr'")

_BUILTIN_NAMES = frozenset(dir(builtins))

#: Roots that name a standard-library module. A field rooted at one of these in
#: a file that never imports it is the #15614 class: the prefix alone would
#: raise ``NameError``, so the import is the fix.
_STDLIB_MODULE_NAMES = frozenset(sys.stdlib_module_names)

#: The opening of a shell/JS template expansion, assembled from parts: written
#: whole it would be a finding in this module's own source under a sibling guard.
_SHELL_EXPANSION_PREFIX = "$" + "{"

#: One parsed module's shared state: the tree, every name it binds, and each
#: string it is legal to examine paired with the fields that string emits.
ModuleView = Tuple[ast.AST, Set[str], List[Tuple[ast.Constant, List[str]]]]

#: ``(line, field)`` pairs, the shape every category returns.
Findings = List[Tuple[int, str]]


def _replacement_fields(text: str) -> List[str]:
    """Every replacement field in *text*, or none when it is not a format string.

    ``Formatter.parse`` raises on an unbalanced brace, which is exactly what
    regex source and quoted JS bodies look like -- those are not format strings
    and have no fields to offer.
    """
    try:
        return [field for _, field, _, _ in string.Formatter().parse(text) if field is not None]
    except (ValueError, IndexError):
        return []


@lru_cache(maxsize=16384)
def _field_root(field: str, qualified: bool = True) -> Optional[str]:
    """The name a replacement field is ultimately rooted at, or ``None``.

    Returns ``None`` for a field that is not an expression built purely from
    names, attributes, subscripts, calls, constants and arithmetic -- the test
    that separates a stranded interpolation from regex or foreign-language
    source, which does not parse at all. *qualified* selects which half of the
    parsed population is wanted: ``True`` for fields naming an attribute,
    subscript or call, ``False`` for the bare identifiers those exclude.
    """
    try:
        parsed = ast.parse(field, mode="eval")
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return None
    nodes = list(ast.walk(parsed))
    if not all(isinstance(node, _ALLOWED_FIELD_NODES) for node in nodes):
        return None
    if any(isinstance(node, _REQUIRED_FIELD_NODES) for node in nodes) is not qualified:
        return None
    return _walk_to_root(parsed.body)


def _walk_to_root(node: ast.AST) -> Optional[str]:
    """Descend an attribute/subscript/call chain to the ``Name`` underneath it."""
    while True:
        if isinstance(node, ast.Attribute):
            node = node.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.BinOp):
            node = node.left
        else:
            return node.id if isinstance(node, ast.Name) else None


def _bound_names(tree: ast.AST) -> Set[str]:
    """Every name the module could interpolate: imports, assignments, defs, params, builtins."""
    names: Set[str] = set(_BUILTIN_NAMES)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
            names.update(_parameter_names(node.args))
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names


def _parameter_names(args: ast.arguments) -> Set[str]:
    """Every parameter name on one signature, positional-only through ``**kwargs``."""
    named = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
    collected = {arg.arg for arg in named}
    collected.update(arg.arg for arg in (args.vararg, args.kwarg) if arg is not None)
    return collected


def _inert_string_ids(tree: ast.AST) -> Set[int]:
    """Ids of strings no category may look at: docstrings, ``format`` targets, f-string parts."""
    inert: Set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            _add_docstring(node, inert)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("format", "format_map"):
                inert.add(id(node.func.value))
        elif isinstance(node, ast.JoinedStr):
            inert.update(id(part) for part in ast.walk(node))
    return inert


def _add_docstring(node: ast.AST, inert: Set[int]) -> None:
    """Record the first-statement docstring of *node*, if it has one."""
    body = getattr(node, "body", None)
    if not body:
        return
    first = body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        inert.add(id(first.value))


def _is_foreign_template(text: str) -> bool:
    """True for shell/JS expansions and for source code held as data."""
    return _SHELL_EXPANSION_PREFIX in text or any(marker in text for marker in _INNER_FSTRING_MARKERS)


def _module_view(tree: ast.AST) -> ModuleView:
    """The per-file state all three categories share, computed once per file."""
    inert = _inert_string_ids(tree)
    strings = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in inert
        and not _is_foreign_template(node.value)
    ]
    return tree, _bound_names(tree), [(node, _replacement_fields(node.value)) for node in strings]


def _findings_in(view: ModuleView) -> Findings:
    """The first category: a qualifying field whose root the module binds."""
    _, names, strings = view
    return [(node.lineno, field) for node, fields in strings for field in fields if _field_root(field) in names]


def _companion_findings_in(view: ModuleView) -> Findings:
    """#15617 -- a bare identifier standing beside a qualifying finding.

    "Beside" is the same string or the same enclosing function, never the same
    module: at file granularity this readmits the whole bare population of any
    file holding one finding, which is the swamping the first condition exists
    to prevent.
    """
    tree, names, strings = view
    decorated = _decorator_string_ids(tree)
    scopes: Dict[int, int] = {}
    _tag_scopes(tree, id(tree), scopes)
    eligible = [(node, fields) for node, fields in strings if id(node) not in decorated]
    anchors = {scopes.get(id(n), id(tree)) for n, f in eligible if _has_qualifying(f, names)} - {id(tree)}
    findings: Findings = []
    for node, fields in eligible:
        if _has_qualifying(fields, names) or scopes.get(id(node), id(tree)) in anchors:
            findings.extend((node.lineno, f) for f in fields if _field_root(f, qualified=False) in names)
    return findings


def _has_qualifying(fields: List[str], names: Set[str]) -> bool:
    """True when a string already holds a field the first category would flag."""
    return any(_field_root(field) in names for field in fields)


def _tag_scopes(node: ast.AST, scope: int, scopes: Dict[int, int]) -> None:
    """Tag every string under *node* with the id of its nearest enclosing function."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            scopes[id(child)] = scope
        inner = id(child) if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else scope
        _tag_scopes(child, inner, scopes)


def _decorator_string_ids(tree: ast.AST) -> Set[int]:
    """Ids of strings inside a decorator: a route path segment is not the module's interpolation.

    ``decorator_list`` hangs off the function node, so without this a handler
    holding one real finding would drag its own route path in with it.
    """
    ids: Set[int] = set()
    for node in ast.walk(tree):
        for decorator in getattr(node, "decorator_list", []):
            found = (p for p in ast.walk(decorator) if isinstance(p, ast.Constant) and isinstance(p.value, str))
            ids.update(id(part) for part in found)
    return ids


@lru_cache(maxsize=16384)
def _conditional_field_names(field: str) -> Optional[FrozenSet[str]]:
    """Every name a conditional-expression field interpolates, or ``None`` (#15627).

    ``None`` when the field is not one of those: it does not parse, it reaches
    outside the conditional grammar, or it holds no ternary at all. An empty
    result is a ternary over constants alone, which interpolates nothing and is
    therefore not a stranded interpolation either.
    """
    try:
        parsed = ast.parse(field, mode="eval")
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return None
    nodes = list(ast.walk(parsed))
    if not all(isinstance(node, _CONDITIONAL_FIELD_NODES) for node in nodes):
        return None
    if not any(isinstance(node, ast.IfExp) for node in nodes):
        return None
    return frozenset(node.id for node in nodes if isinstance(node, ast.Name))


def _conditional_findings_in(view: ModuleView) -> Findings:
    """#15627 -- a ternary field, invisible to all three categories above.

    Every name in the field must be bound, not only one root: a ternary carries
    a root per branch plus one in its test, and a field the module can resolve
    only half of is a template addressed elsewhere rather than a lost prefix.
    """
    _, names, strings = view
    findings: Findings = []
    for node, fields in strings:
        for field in fields:
            interpolated = _conditional_field_names(field)
            if interpolated and interpolated <= names:
                findings.append((node.lineno, field))
    return findings


def _called_name(func: ast.AST) -> Optional[str]:
    """The attribute or bare name a call names, so ``logger.info`` and ``print`` both resolve."""
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else None


def _emitted_string_ids(tree: ast.AST) -> Set[int]:
    """Ids of strings standing in a positional argument of a logging or ``print`` call."""
    ids: Set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _called_name(node.func) not in _EMIT_METHODS:
            continue
        for argument in node.args:
            found = (p for p in ast.walk(argument) if isinstance(p, ast.Constant) and isinstance(p.value, str))
            ids.update(id(part) for part in found)
    return ids


def _function_bindings(node: ast.AST) -> Set[str]:
    """Parameters, assignments, loop targets and caught exceptions of one function body."""
    bound = set(_parameter_names(node.args))
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Store):
            bound.add(inner.id)
        elif isinstance(inner, ast.ExceptHandler) and inner.name:
            bound.add(inner.name)
    return bound


def _local_bindings(node: ast.AST, bound: FrozenSet[str], scopes: Dict[int, FrozenSet[str]]) -> None:
    """Tag every string with the names its enclosing functions bind locally."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            scopes[id(child)] = bound
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _local_bindings(child, bound | _function_bindings(child), scopes)
        else:
            _local_bindings(child, bound, scopes)


def _emitted_bare_findings_in(view: ModuleView) -> Findings:
    """#15628 -- a bare identifier in an emitted message, bound where the message is built.

    Both conditions are what make this half of the bare population readable.
    Message position alone reaches 12 of the 1,452 and one of the twelve is a
    ``print`` documenting a route shape; requiring the root to be local to the
    enclosing function drops exactly that one, because a runtime value being
    emitted is bound where the emitting happens. 1,452 -> 11, all eleven real.
    """
    tree, names, strings = view
    emitted = _emitted_string_ids(tree)
    candidates = [(node, fields) for node, fields in strings if fields and id(node) in emitted]
    if not candidates:
        return []  # the scope tagging below costs a walk per function; most files never need it
    scopes: Dict[int, FrozenSet[str]] = {}
    _local_bindings(tree, frozenset(), scopes)
    findings: Findings = []
    for node, fields in candidates:
        local = scopes.get(id(node), frozenset())
        roots = ((field, _field_root(field, qualified=False)) for field in fields)
        findings.extend((node.lineno, field) for field, root in roots if root in local and root in names)
    return findings


def _unimported_module_findings_in(view: ModuleView) -> Findings:
    """#15614 -- a field rooted at a standard-library module the file never imports."""
    _, names, strings = view
    findings: Findings = []
    for node, fields in strings:
        for field in fields:
            root = _field_root(field)
            if root in _STDLIB_MODULE_NAMES and root not in names:
                findings.append((node.lineno, field))
    return findings


#: Every category, each a finder over one parsed module. They share the sweep,
#: the reach floors and the module view; each is asserted separately.
CATEGORIES: Tuple[Tuple[str, Callable[[ModuleView], Findings]], ...] = (
    ("stranded", _findings_in),
    ("companion", _companion_findings_in),
    ("unimported_module", _unimported_module_findings_in),
    ("conditional", _conditional_findings_in),
    ("emitted_bare", _emitted_bare_findings_in),
)


def _examine(source: str, finder: Callable[[ModuleView], Findings]) -> Findings:
    """Apply one category to *source*, so a fixture and a repository file share the code path.

    Returns an empty list for source that does not parse -- callers count parsed
    files separately, so a syntax error can never masquerade as a clean file.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    return finder(_module_view(tree))


def stranded_interpolations(source: str) -> Findings:
    """``(line, field)`` for every string in *source* that emits its own placeholder."""
    return _examine(source, _findings_in)


def companion_interpolations(source: str) -> Findings:
    """``(line, field)`` for every bare identifier stranded beside one of those (#15617)."""
    return _examine(source, _companion_findings_in)


def unimported_module_interpolations(source: str) -> Findings:
    """``(line, field)`` for every field reaching a stdlib module *source* never imports (#15614)."""
    return _examine(source, _unimported_module_findings_in)


def conditional_interpolations(source: str) -> Findings:
    """``(line, field)`` for every stranded field holding a conditional expression (#15627)."""
    return _examine(source, _conditional_findings_in)


def emitted_bare_interpolations(source: str) -> Findings:
    """``(line, field)`` for every bare identifier stranded in an emitted message (#15628)."""
    return _examine(source, _emitted_bare_findings_in)


def tracked_python_files() -> Tuple[str, ...]:
    """Every tracked ``.py`` path, git-enumerated so a stray local file cannot join the sweep."""
    listed = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        env=scrubbed_git_env(),
    )
    paths = [line.replace("\\", "/") for line in listed.stdout.splitlines() if line.strip()]
    return tuple(p for p in paths if not any(part in EXCLUDED_DIR_NAMES for part in Path(p).parts))


@lru_cache(maxsize=1)
def sweep() -> Tuple[Dict[str, Dict[str, int]], int, int]:
    """``(per-category findings-per-file, files parsed, string constants examined)``.

    Both reach counters are returned alongside the findings so the floors can be
    asserted on what the sweep *touched*, never on what it *found*.
    """
    findings: Dict[str, Dict[str, int]] = {name: {} for name, _ in CATEGORIES}
    parsed = examined = 0
    for relative in tracked_python_files():
        try:
            source = (REPO_ROOT / relative).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
            continue
        parsed += 1
        examined += sum(1 for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str))
        view = _module_view(tree)
        for name, finder in CATEGORIES:
            hits = finder(view)
            if hits:
                findings[name][relative] = len(hits)
    return findings, parsed, examined
