# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AST scan of the spellings audit writers pass (#18716); the half of the guard that reads source.

A writer call is found by its callee name, and the action it passes is *resolved*, not
grepped: a string literal, an enum member (``AuditAction.X`` / ``IdentityAuditAction.X`` /
``ComplianceEventType.X``, with or without ``.value``), a module-level constant, or a
module-level dict looked up by key. An f-string resolves to its constant prefix. A value that
is a parameter, an attribute or a call is a *forwarder*: its literal is written (and
scanned) at the call site that supplies it, so it is reported as ``unresolved`` rather than
guessed at.

Known gap, stated rather than hidden: a literal handed to a wrapper that is not itself a
writer name (``_audit_file_operation(request, "x", ...)``) is not seen here.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator, NamedTuple

#: callee name -> positional index of the action (keyword ``action`` / ``operation`` always wins).
WRITERS: dict[str, int] = {
    "audit_log": 0,
    "_audit_log": 0,
    "log_action": 0,
    "audit_row": 0,
    "AuditEvent": 1,
    "create_audit_log": 2,
    "audit_operation": 0,
}
#: Writers that run the one boundary mapping (``audit_row`` canonicalises), so a legacy
#: ``IdentityAuditAction`` constant they pass is stored canonical.
BOUNDARY_WRITERS = frozenset({"audit_row", "_audit_log"})
#: A module-level dict whose values are all written as actions (the audit middleware's path map).
ACTION_TABLES = frozenset({"AUTO_AUDIT_OPERATIONS"})
TAXONOMY = "autobot-backend/services/audit/taxonomy.py"
IDENTITY = "autobot_shared/user_management/models/audit.py"


class Written(NamedTuple):
    rel: str
    line: int
    writer: str
    kind: str  # "literal" | "prefix" | "unresolved"
    value: str


def enum_members(source: str, class_name: str) -> dict[str, str]:
    """``{MEMBER: "value"}`` of the string-valued class named *class_name* in *source*."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                t.id: stmt.value.value
                for stmt in node.body
                if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant)
                for t in stmt.targets
                if isinstance(t, ast.Name) and isinstance(stmt.value.value, str)
            }
    return {}


def _module_constants(tree: ast.Module) -> dict[str, ast.expr]:
    return {
        t.id: stmt.value
        for stmt in tree.body
        if isinstance(stmt, ast.Assign)
        for t in stmt.targets
        if isinstance(t, ast.Name)
    }


def _resolve(
    node: ast.expr, consts: dict[str, ast.expr], enums: dict[str, dict[str, str]]
) -> Iterator[tuple[str, str]]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield "literal", node.value
    elif isinstance(node, ast.JoinedStr):
        head = node.values[0] if node.values else None
        yield "prefix", head.value if isinstance(head, ast.Constant) else ""
    elif isinstance(node, ast.Attribute) and node.attr == "value":
        yield from _resolve(node.value, consts, enums)
    elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in enums:
        member = enums[node.value.id].get(node.attr)
        yield ("literal", member) if member is not None else ("unresolved", ast.unparse(node))
    elif isinstance(node, ast.IfExp):
        yield from _resolve(node.body, consts, enums)
        yield from _resolve(node.orelse, consts, enums)
    else:
        yield from _resolve_name(node, consts, enums)


def _resolve_name(
    node: ast.expr, consts: dict[str, ast.expr], enums: dict[str, dict[str, str]]
) -> Iterator[tuple[str, str]]:
    target = node.value if isinstance(node, ast.Subscript) else node
    bound = consts.get(target.id) if isinstance(target, ast.Name) else None
    if isinstance(bound, ast.Dict) and isinstance(node, ast.Subscript):
        for value in bound.values:
            yield from _resolve(value, {}, enums)
    elif bound is not None and isinstance(node, ast.Name):
        yield from _resolve(bound, {}, enums)
    else:
        yield "unresolved", ast.unparse(node)


def _action_node(call: ast.Call, index: int) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg in ("action", "operation"):
            return kw.value
    return call.args[index] if len(call.args) > index and not isinstance(call.args[index], ast.Starred) else None


def _callee(call: ast.Call) -> str | None:
    fn = call.func
    return fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None


def scan_source(rel: str, source: str, enums: dict[str, dict[str, str]]) -> list[Written]:
    """Every action spelling the writer calls (and action tables) in *source* pass."""
    tree = ast.parse(source)
    consts = _module_constants(tree)
    found: list[Written] = []
    for name in ACTION_TABLES & consts.keys():
        for kind, value in _table_values(consts[name], enums):
            found.append(Written(rel, consts[name].lineno, name, kind, value))
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        writer = _callee(call)
        node = _action_node(call, WRITERS[writer]) if writer in WRITERS else None
        if node is not None:
            found.extend(Written(rel, call.lineno, writer, k, v) for k, v in _resolve(node, consts, enums))
    return found


def _table_values(table: ast.expr, enums: dict[str, dict[str, str]]) -> Iterator[tuple[str, str]]:
    for value in table.values if isinstance(table, ast.Dict) else ():
        yield from _resolve(value, {}, enums)


def read_enums(root: Path) -> dict[str, dict[str, str]]:
    """The three action vocabularies, parsed from their defining files under *root*."""
    taxonomy = (root / TAXONOMY).read_text(encoding="utf-8")
    identity = (root / IDENTITY).read_text(encoding="utf-8")
    return {
        "AuditAction": enum_members(taxonomy, "AuditAction"),
        "ComplianceEventType": enum_members(taxonomy, "ComplianceEventType"),
        "IdentityAuditAction": enum_members(identity, "IdentityAuditAction"),
    }
