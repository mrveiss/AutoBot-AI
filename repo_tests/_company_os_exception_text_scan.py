# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Finds LLC response bodies built from exception text or a helper's exception parameter (#21579).

Stdlib only, so a throwaway script can load it by path. A site is a call to `HTTPException`,
`JSONResponse` or `Response` with an argument that holds

* a name bound by an enclosing `except ... as <name>`: bare, or through any attribute other than
  `public_detail` and `errors` (or one allow-listed by (file, attribute)); or
* a function parameter that is an exception (annotated `...Exception` / `...Error`, or named like one) run
  through `str()`, `repr()`, an f-string, `%`/`+`/`.format` or read as `.args` / `.message` (the helper
  shape: `def helper(exc): ... detail=str(exc)`). `isinstance(exc, X)` is a type test, not text.

A local assigned (plain, annotated or walrus) from an expression rendering such a name is tainted and
treated the same way (`msg = str(exc)` then `detail=msg`). Passing `str(exc)` to another function
whose result reaches a detail is interprocedural and NOT covered.

A call to `http_refusal` is the sanctioned mapping: its arguments are not searched, and
`http_refusal` itself is not scanned for the parameter shape.
"""

from __future__ import annotations

import ast
from pathlib import Path

from autobot_shared.testfile_names import is_test_filename
from tools.lint import _parse_cache as parse_cache

LLC_ROOT = "autobot-backend/llc"
RESPONSE_CALLS = frozenset({"HTTPException", "JSONResponse", "Response"})
PUBLIC_ATTRS = frozenset({"public_detail", "errors"})
PARAM_LEAK_ATTRS = frozenset({"args", "message"})
SANCTIONED_CALL = "http_refusal"
#: (relative path, attribute) pairs allowed beyond PUBLIC_ATTRS; each needs a reason in a comment.
ATTRIBUTE_ALLOW: frozenset[tuple[str, str]] = frozenset(
    {
        # Structured exception attributes (counts, names, ids), never message text.
        ("autobot-backend/llc/api/boards.py", "column_name"),
        ("autobot-backend/llc/api/boards.py", "wip_limit"),
        ("autobot-backend/llc/api/boards.py", "current_count"),
        ("autobot-backend/llc/api/contacts.py", "company_ids"),
        ("autobot-backend/llc/api/templates.py", "unresolved"),
    }
)
EXCEPTION_PARAM_NAMES = frozenset({"exc", "e", "ex", "err", "error", "exception"})
_FORMAT_PARENTS = (ast.JoinedStr, ast.FormattedValue, ast.BinOp)


def _exc_text_call_name(call: ast.Call) -> str:
    func = call.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""


def _exc_text_is_exception_param(arg: ast.arg) -> bool:
    """A parameter that holds an exception: annotated as one, or named like one."""
    note = ast.unparse(arg.annotation) if arg.annotation else ""
    return arg.arg in EXCEPTION_PARAM_NAMES or note.endswith(("Exception", "Error", "Violation"))


def _exc_text_parent_map(root: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(root) for child in ast.iter_child_nodes(parent)}


def _exc_text_names_outside_sanctioned(node: ast.AST):
    """Every `ast.Name` under *node*, not descending into a `http_refusal(...)` call."""
    if isinstance(node, ast.Call) and _exc_text_call_name(node) == SANCTIONED_CALL:
        return
    if isinstance(node, ast.Name):
        yield node
    for child in ast.iter_child_nodes(node):
        yield from _exc_text_names_outside_sanctioned(child)


def _exc_text_in_format(name: ast.Name, parents: dict[ast.AST, ast.AST]) -> bool:
    """Whether *name* is rendered to text: str()/repr(), .format(), an f-string, `%` or `+`."""
    node: ast.AST = name
    while node in parents and not isinstance(node, ast.Call):
        node = parents[node]
        if isinstance(node, _FORMAT_PARENTS):
            return True
    if isinstance(node, ast.Call):
        return _exc_text_call_name(node) in {"str", "repr", "format"}
    return False


def _exc_text_leaks(name: ast.Name, parents: dict[ast.AST, ast.AST], rel: str, from_except: bool) -> bool:
    parent = parents.get(name)
    if isinstance(parent, ast.Attribute) and parent.value is name:
        if parent.attr in PUBLIC_ATTRS or (rel, parent.attr) in ATTRIBUTE_ALLOW:
            return False
        return from_except or parent.attr in PARAM_LEAK_ATTRS
    if isinstance(parent, ast.Call) and _exc_text_call_name(parent) in {"isinstance", "type"}:
        return False
    return from_except or _exc_text_in_format(name, parents)


_EXC_TEXT_LOOPS = (ast.For, ast.AsyncFor, ast.While)
_EXC_TEXT_TRIES = tuple({ast.Try, getattr(ast, "TryStar", ast.Try)})
_EXC_TEXT_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
#: A name tainted in two different statement lists: no same-list overwrite can clear it any more.
_EXC_TEXT_TAINTED_ELSEWHERE = -1


def _exc_text_stmt_lists(func: ast.AST) -> tuple[dict[int, int], set[int], int]:
    """`({id(statement): id(its statement list)}, ids of lists an overwrite may clear in, id(function body))`.

    A list is clearing-safe unless control can leave it between two of its statements: it sits inside a
    loop (any part, `orelse` included) or is a `try`'s `body`, `orelse` or `finalbody`, at any enclosing level.
    An except-handler body is safe unless its `try` is itself inside a loop or another try's block.
    """
    homes: dict[int, int] = {}
    safe: set[int] = set()

    def walk(node: ast.AST, unsafe: bool) -> None:
        inner = unsafe or isinstance(node, _EXC_TEXT_LOOPS + _EXC_TEXT_TRIES)
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if not (isinstance(block, list) and block and isinstance(block[0], ast.stmt)):
                continue
            homes.update({id(stmt): id(block) for stmt in block})
            if not inner:
                safe.add(id(block))
            for stmt in block:
                if not isinstance(stmt, _EXC_TEXT_NESTED_SCOPES):
                    walk(stmt, inner)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ExceptHandler, ast.match_case)):
                walk(child, unsafe)

    walk(func, False)
    return homes, safe, id(func.body)


class _ExcTextScan(ast.NodeVisitor):
    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.qual: list[str] = []
        self.excepts: list[str] = []
        self.params: list[set[str]] = []
        self.tainted: list[set[str]] = [set()]
        #: Per function: where each statement lives (id of its statement list), the function's own list, and
        #: the list each tainted name was last tainted in -- what decides whether an overwrite is definite.
        self.stmt_list: list[dict[int, int]] = [{}]
        self.safe_lists: list[set[int]] = [set()]
        self.top_list: list[int] = [0]
        self.taint_list: list[dict[str, int]] = [{}]
        self.counts: dict[str, int] = {}
        self.sites: list[str] = []

    def _exc_text_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        args = node.args
        every = [*args.posonlyargs, *args.args, *args.kwonlyargs, *([args.vararg] if args.vararg else [])]
        self.qual.append(node.name)
        self.params.append({a.arg for a in every if _exc_text_is_exception_param(a)})
        self.tainted.append(set())
        homes, safe, top = _exc_text_stmt_lists(node)
        self.stmt_list.append(homes)
        self.safe_lists.append(safe)
        self.top_list.append(top)
        self.taint_list.append({})
        self.generic_visit(node)
        self.taint_list.pop()
        self.top_list.pop()
        self.safe_lists.pop()
        self.stmt_list.pop()
        self.tainted.pop()
        self.params.pop()
        self.qual.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _exc_text_function

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.qual.append(node.name)
        self.generic_visit(node)
        self.qual.pop()

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.excepts.append(node.name or "")
        self.generic_visit(node)
        self.excepts.pop()

    def _exc_text_name_leaks(self, name: ast.Name, parents: dict[ast.AST, ast.AST]) -> bool:
        """Whether *name* renders an exception to text: an except-bound or tainted name by any use, an
        exception-typed parameter only when run through the parameter-rendering rules."""
        bound = {n for n in self.excepts if n}.union(*self.tainted)
        if name.id in bound:
            return _exc_text_leaks(name, parents, self.rel, True)
        params = set().union(*self.params)
        return name.id in params and _exc_text_leaks(name, parents, self.rel, False)

    def _exc_text_carries_text(self, value: ast.AST | None) -> bool:
        """Whether *value* renders an exception (bound, tainted or parameter) to text, not via `public_detail`."""
        if value is None:
            return False
        parents = _exc_text_parent_map(value)
        return any(self._exc_text_name_leaks(n, parents) for n in _exc_text_names_outside_sanctioned(value))

    def _exc_text_taint(self, targets: list[ast.expr], value: ast.AST | None, stmt: ast.stmt | None = None) -> None:
        names = [n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)]
        home = self.stmt_list[-1].get(id(stmt)) if stmt is not None else None
        if self._exc_text_carries_text(value):
            self.tainted[-1].update(names)
            where = self.taint_list[-1]
            for name in names:
                seen = where.get(name, home)
                where[name] = home if home is not None and seen == home else _EXC_TEXT_TAINTED_ELSEWHERE
        elif value is not None and home is not None and all(isinstance(t, ast.Name) for t in targets):
            for name in names:
                if self._exc_text_overwrite_is_definite(name, home):
                    self.tainted[-1].discard(name)
                    self.taint_list[-1].pop(name, None)

    def _exc_text_overwrite_is_definite(self, name: str, home: int) -> bool:
        """Whether an overwrite of *name* in statement list *home* runs after every taint of it, whatever happens."""
        return home == self.top_list[-1] or (home == self.taint_list[-1].get(name) and home in self.safe_lists[-1])

    def visit_Assign(self, node: ast.Assign) -> None:
        self._exc_text_taint(node.targets, node.value, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._exc_text_taint([node.target], node.value, node)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._exc_text_taint([node.target], node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _exc_text_call_name(node) in RESPONSE_CALLS and self._exc_text_leaking(node):
            where = ".".join(self.qual) or "<module>"
            self.counts[where] = self.counts.get(where, 0) + 1
            self.sites.append(f"{self.rel}::{where}#{self.counts[where]}")
        self.generic_visit(node)

    def _exc_text_leaking(self, call: ast.Call) -> bool:
        if SANCTIONED_CALL in self.qual:
            return False
        parents = _exc_text_parent_map(call)
        values = [*call.args, *(k.value for k in call.keywords)]
        return any(self._exc_text_name_leaks(n, parents) for v in values for n in _exc_text_names_outside_sanctioned(v))


def exc_text_scan_source(source: str, rel: str) -> list[str]:
    """The site identities in one source text, in source order."""
    scan = _ExcTextScan(rel)
    scan.visit(parse_cache.parse(source))
    return scan.sites


def _exc_text_is_test_file(path: Path, root: Path) -> bool:
    """A test module, judged by the directories BELOW *root*: a checkout under a `tests` ancestor is not tests."""
    return "tests" in path.relative_to(root).parts[:-1] or is_test_filename(path.name)


def exc_text_scanned_files(root: Path) -> list[str]:
    """Repo-relative paths of the non-test modules under `autobot-backend/llc` the sweep parses."""
    return [
        path.relative_to(root).as_posix()
        for path in sorted((root / LLC_ROOT).rglob("*.py"))
        if not _exc_text_is_test_file(path, root)
    ]


def exc_text_scan_report(root: Path) -> tuple[dict[str, int], int]:
    """`({identity: 1}, files parsed)`: the parsed count is independent of what was found."""
    found: dict[str, int] = {}
    files = exc_text_scanned_files(root)
    for rel in files:
        for site in exc_text_scan_source((root / rel).read_text(encoding="utf-8"), rel):
            found[site] = 1
    return found, len(files)


def exc_text_scan_tree(root: Path) -> dict[str, int]:
    """`{identity: 1}` for every non-test module under `autobot-backend/llc`."""
    return exc_text_scan_report(root)[0]
