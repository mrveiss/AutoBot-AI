# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AST-based safety guard for the compose tool's user scripts (GH#11568).

Validates Python source before sandbox execution (hard gate):
- import allowlist (top-level module names only)
- builtin-call ALLOWLIST: a call to a bare Name that resolves to a Python builtin is
  rejected unless the builtin is in ``SAFE_BUILTINS`` (pure-compute, no I/O, no
  introspection). This is allowlist-not-blocklist, so new dangerous builtins (open,
  input, type, memoryview, exit, help, ...) can never leak. Locally shadowed names
  and injected tool names are exempt.
- reflective accessors getattr/setattr/delattr/hasattr and eval/exec/compile/__import__/
  globals/vars/locals/breakpoint blocked as a bare Name reference ANYWHERE (call,
  decorator, rebind, argument) — closes ``@eval``, ``f = eval``, ``g = getattr; g(...)``
- method-style ``obj.exec()``/``obj.eval()`` calls
- ANY dunder attribute access (``.__class__``, ``.__bases__``, ``.__subclasses__``, ...)
- subscripting ``__builtins__`` (or any dunder name)
- forbidden_work token name references

Protocol note: ``print``/``open``/``input`` are excluded from SAFE_BUILTINS on purpose —
the broker RPC uses the script's stdout for requests and stdin for replies, so a user
``print()`` corrupts the request stream and ``input()`` steals a broker reply.
"""

import ast
import builtins as _builtins
import os
from dataclasses import dataclass, field

CODEEXEC_IMPORT_ALLOWLIST: frozenset[str] = frozenset(
    os.environ.get("AUTOBOT_CODEEXEC_IMPORT_ALLOWLIST", "autobot_tools,asyncio,json,re,math").split(",")
)

# Pure-compute, no-I/O, no-introspection builtins the script may call. Allowlist (not
# blocklist) so dangerous builtins can never leak. Env-extendable, same pattern as the
# import allowlist. Deliberately EXCLUDES: open/input/print (broker stdio channel),
# type/object/super/vars/globals/locals/dir/id/hash/memoryview/compile/eval/exec/
# __import__/exit/quit/help/getattr/setattr/delattr/hasattr/property/staticmethod/
# classmethod (I/O or introspection reach).
_DEFAULT_SAFE_BUILTINS = (
    "len,range,enumerate,zip,sorted,reversed,sum,min,max,abs,round,all,any,map,filter,"
    "str,int,float,bool,list,dict,set,tuple,frozenset,bytes,bytearray,repr,format,"
    "isinstance,issubclass,ord,chr,divmod,pow,hex,oct,bin,slice"
)
SAFE_BUILTINS: frozenset[str] = frozenset(
    b.strip()
    for b in os.environ.get("AUTOBOT_CODEEXEC_BUILTINS_ALLOWLIST", _DEFAULT_SAFE_BUILTINS).split(",")
    if b.strip()
)

# Every real Python builtin name — the universe the allowlist filters against.
_ALL_BUILTINS: frozenset[str] = frozenset(dir(_builtins))

# Names that grant reflective / eval-like reach into the runtime; unrepresentable in v1.
# These are rejected as a bare Name load ANYWHERE (call func, decorator, RHS, arg),
# not only when directly called — ``@eval`` and ``f = eval`` are equally unsafe.
_BLOCKED_CALLS: frozenset[str] = frozenset(
    {"exec", "eval", "compile", "__import__", "globals", "vars", "locals", "breakpoint"}
)
# Reflective attribute accessors — rejected as bare Name references anywhere. They are
# never needed by the clean read-only shims, and permitting them re-opens computed-name,
# dunder-target, and accessor-aliasing (``g = getattr``) smuggling paths.
_GETSET_ATTR: frozenset[str] = frozenset({"getattr", "setattr", "delattr", "hasattr"})


@dataclass
class ASTGuardResult:
    """Result of an AST safety scan."""

    ok: bool
    violations: list[dict] = field(default_factory=list)


def _is_dunder(name: str) -> bool:
    """True for a Python dunder identifier (starts AND ends with ``__``)."""
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def _collect_targets(target: ast.expr, names: set[str]) -> None:
    """Add every Name id in an assignment *target* (incl. tuple/list unpacking)."""
    if isinstance(target, ast.Name):
        names.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _collect_targets(elt, names)


def _local_bindings(tree: ast.AST) -> frozenset[str]:
    """Names the script binds itself (def/class/assign/import-as/params).

    A bare-Name call to one of these is a user symbol, not a builtin, so it is exempt
    from the builtin allowlist (e.g. the script may define its own ``def str(...)``).
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            names.update(a.arg for a in getattr(node.args, "args", []))
            names.update(a.arg for a in getattr(node.args, "posonlyargs", []))
            names.update(a.arg for a in getattr(node.args, "kwonlyargs", []))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                _collect_targets(t, names)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(a.asname or a.name.split(".")[0] for a in node.names)
    return frozenset(names)


def _check_import_node(node: ast.stmt) -> list[dict]:
    violations: list[dict] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top not in CODEEXEC_IMPORT_ALLOWLIST:
                violations.append({"line": node.lineno, "message": f"forbidden import: {top!r}"})
    elif isinstance(node, ast.ImportFrom):
        top = (node.module or "").split(".")[0]
        if top not in CODEEXEC_IMPORT_ALLOWLIST:
            violations.append({"line": node.lineno, "message": f"forbidden import: {top!r}"})
    return violations


def _check_call_node(node: ast.Call, exempt: frozenset[str]) -> list[dict]:
    """Enforce the builtin-call allowlist and reject method-style ``obj.exec()``.

    A call whose func is a bare Name resolving to a real Python builtin is rejected
    unless that builtin is in ``SAFE_BUILTINS``. Names in *exempt* (local bindings +
    injected tool names) are user/tool symbols, not builtins, and pass through.
    Bare-Name references to blocked builtins/accessors are also caught by
    ``_check_name_node``; this adds the allowlist gate and the attribute-call form.
    """
    lineno = getattr(node, "lineno", 0)
    func = node.func
    if isinstance(func, ast.Name):
        name = func.id
        if name in exempt or name in SAFE_BUILTINS:
            return []
        if name in _ALL_BUILTINS:
            return [{"line": lineno, "message": f"forbidden builtin: {name!r} (not in SAFE_BUILTINS)"}]
    elif isinstance(func, ast.Attribute) and func.attr in _BLOCKED_CALLS:
        return [{"line": lineno, "message": f"forbidden call: .{func.attr!r}"}]
    return []


def _check_attribute_node(node: ast.Attribute) -> list[dict]:
    """Reject any dunder attribute access (blocks __class__/__bases__/__subclasses__)."""
    if _is_dunder(node.attr):
        return [{"line": getattr(node, "lineno", 0), "message": f"dunder attribute access: .{node.attr}"}]
    return []


def _check_subscript_node(node: ast.Subscript) -> list[dict]:
    """Reject ``__builtins__[...]`` and subscripting any dunder name."""
    value = node.value
    if isinstance(value, ast.Name) and _is_dunder(value.id):
        return [{"line": getattr(node, "lineno", 0), "message": f"subscript of dunder name: {value.id}"}]
    return []


def _check_name_node(node: ast.Name, forbidden_work_tokens: frozenset[str], exempt: frozenset[str]) -> list[dict]:
    """Reject an unsafe-builtin, reflective-accessor, forbidden-token, or dunder name.

    Blocking these as a bare Name (not just a call func) closes decorator (``@eval``),
    rebind (``f = eval``, ``g = getattr``), and bare-reference (``super``) escapes.
    A Name resolving to a real builtin that is NOT in SAFE_BUILTINS and NOT locally
    bound / injected is rejected — the allowlist applies to references, not just calls.
    """
    name = node.id
    lineno = getattr(node, "lineno", 0)
    if name in _GETSET_ATTR:
        return [{"line": lineno, "message": f"reflective accessor reference: {name!r}"}]
    if name in forbidden_work_tokens:
        return [{"line": lineno, "message": f"forbidden token reference: {name!r}"}]
    if _is_dunder(name):
        return [{"line": lineno, "message": f"dunder name reference: {name!r}"}]
    if name in _ALL_BUILTINS and name not in SAFE_BUILTINS and name not in exempt:
        return [{"line": lineno, "message": f"forbidden builtin reference: {name!r} (not in SAFE_BUILTINS)"}]
    return []


def check_script(
    script: str,
    forbidden_work_tokens: frozenset[str],
    injected_tools: "frozenset[str] | None" = None,
) -> ASTGuardResult:
    """Parse and safety-scan *script*; return ASTGuardResult (hard gate).

    *injected_tools* are the shim names available to the script (e.g. ``web_search``);
    together with the script's own local bindings they are exempt from the builtin
    allowlist so a tool/user symbol shadowing is never mistaken for a builtin.
    """
    try:
        tree = ast.parse(script)
    except SyntaxError as exc:
        return ASTGuardResult(ok=False, violations=[{"line": 0, "message": f"SyntaxError: {exc}"}])

    exempt = _local_bindings(tree) | (injected_tools or frozenset())
    violations: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            violations.extend(_check_import_node(node))
        elif isinstance(node, ast.Call):
            violations.extend(_check_call_node(node, exempt))
        elif isinstance(node, ast.Attribute):
            violations.extend(_check_attribute_node(node))
        elif isinstance(node, ast.Subscript):
            violations.extend(_check_subscript_node(node))
        elif isinstance(node, ast.Name):
            violations.extend(_check_name_node(node, forbidden_work_tokens, exempt))
    return ASTGuardResult(ok=len(violations) == 0, violations=violations)
