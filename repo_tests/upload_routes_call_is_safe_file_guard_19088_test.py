# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every ``UploadFile`` route reaches the upload-filename gate (#19088).

THREAT_MODEL.md section 1 requires ``is_safe_file`` on every upload route. 13
production modules accepted an ``UploadFile`` and never called it. A route
passes when ``is_safe_file`` / ``require_safe_upload`` is called in its body or
in any function it calls, followed by name (same file or another module).

A route that legitimately takes arbitrary bytes is not exempted here: it needs
an ``ARCHITECTURE_EXCEPTIONS.md`` entry and a line in ``_DOCUMENTED_EXCEPTIONS``
naming it, so the exception is greppable from both sides. None exist today.
"""

from __future__ import annotations

import ast
from functools import lru_cache

from repo_tests._paths import repo_root

_REPO_ROOT = repo_root()
_PACKAGES = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
_VERBS = {"get", "post", "put", "patch", "delete", "head", "options"}
_GATES = {"is_safe_file", "require_safe_upload"}
_DOCUMENTED_EXCEPTIONS: frozenset[str] = frozenset()  # "path:function", each with an ARCHITECTURE_EXCEPTIONS.md entry

# Measured when the guard landed: 15 route handlers take an UploadFile annotation, 2 more (knowledge /upload and
# /audio) read ``request.form()``.
# Lower only when the tree genuinely holds fewer -- an extractor that stops
# matching reports zero violations and reads clean.
_UPLOAD_ROUTE_FLOOR = 17


def _is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return "/tests/" in path or name.endswith("_test.py") or name.startswith("test_") or name == "conftest.py"


def _is_route(node: ast.AST) -> bool:
    for decorator in getattr(node, "decorator_list", []):
        func = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(func, ast.Attribute) and func.attr in _VERBS:
            return True
    return False


def _reads_form(node: ast.AST) -> bool:
    """True when the handler calls ``<request>.form()``: the other way a route receives an upload (#19088)."""
    return any(
        isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "form"
        for sub in ast.walk(node)
    )


def _takes_upload(node: ast.AST) -> bool:
    if _reads_form(node):
        return True
    args = node.args.args + node.args.kwonlyargs + node.args.posonlyargs
    for arg in args:
        for sub in ast.walk(arg.annotation) if arg.annotation is not None else ():
            if (isinstance(sub, ast.Name) and sub.id == "UploadFile") or (
                isinstance(sub, ast.Attribute) and sub.attr == "UploadFile"
            ):
                return True
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and "UploadFile" in sub.value:
                return True
    return False


def _import_map(tree: ast.AST) -> dict[str, tuple[str, str | None]]:
    """Local name -> (module stem, original name or None for a module import)."""
    found: dict[str, tuple[str, str | None]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found[alias.asname or alias.name.split(".")[0]] = (alias.name.rsplit(".", 1)[-1], None)
        elif isinstance(node, ast.ImportFrom):
            stem = (node.module or "").rsplit(".", 1)[-1]
            for alias in node.names:
                found[alias.asname or alias.name] = (stem, alias.name)
    return found


def _callees(fn: ast.AST, stem: str, imports: dict[str, tuple[str, str | None]]) -> frozenset:
    """What *fn* calls, as gate names and (module stem, function) keys -- never a bare attribute name.

    A method called ``read`` or ``post`` must not resolve to some unrelated
    function of the same name; only same-file functions, names imported from a
    module, and ``module.function`` calls are followed.
    """
    out: set = set()
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name):
            if func.id in _GATES:
                out.add(func.id)
            imported = imports.get(func.id)
            out.add((imported[0], imported[1] or func.id) if imported and imported[1] else (stem, func.id))
        elif isinstance(func, ast.Attribute):
            if func.attr in _GATES:
                out.add(func.attr)
            base = func.value
            if isinstance(base, ast.Name) and base.id in imports:
                module_stem, original = imports[base.id]
                out.add((module_stem, func.attr))
                if original:  # ``from pkg import module`` then ``module.fn()``
                    out.add((original, func.attr))
    return frozenset(out)


def _call_key(call: ast.Call, stem: str, imports: dict[str, tuple[str, str | None]]) -> frozenset:
    """The ``_callees`` entries of one call expression."""
    wrapper = ast.FunctionDef(
        name="_", args=ast.arguments([], [], None, [], [], None, []), body=[ast.Expr(call)], decorator_list=[]
    )
    return _callees(wrapper, stem, imports)


def _gate_precedes_body_read(fn: ast.AST, stem: str, imports: dict, by_key: dict) -> bool:
    """True unless the handler reads the upload body (``.read(``) on a line before its first gate-reaching call.

    A gate that runs after ``await file.read()`` still lets an unbounded, unchecked body into memory (#19088).
    """
    reads = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "read"]
    gates = [
        n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call) and _reaches_gate(_call_key(n, stem, imports), by_key)
    ]
    return not reads or (bool(gates) and min(gates) <= min(reads))


def _functions(source: str) -> list[ast.AST]:
    return [n for n in ast.walk(ast.parse(source)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


_CONTEXT: dict[tuple[str, str], tuple[ast.AST, str, dict]] = {}


@lru_cache(maxsize=None)
def _index() -> tuple[dict[tuple[str, str], list[frozenset]], list[tuple[str, str, int, frozenset]]]:
    """((stem, function) -> callee sets, every UploadFile route as (file, name, line, callees))."""
    by_key: dict[tuple[str, str], list[frozenset]] = {}
    routes: list[tuple[str, str, int, frozenset]] = []
    for package in _PACKAGES:
        for module in sorted((_REPO_ROOT / package).rglob("*.py")):
            rel = module.relative_to(_REPO_ROOT).as_posix()
            if _is_test(rel) or "node_modules" in rel:
                continue
            try:
                tree = ast.parse(module.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            imports = _import_map(tree)
            for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
                callees = _callees(fn, module.stem, imports)
                by_key.setdefault((module.stem, fn.name), []).append(callees)
                if _is_route(fn) and _takes_upload(fn):
                    routes.append((rel, fn.name, fn.lineno, callees))
                    _CONTEXT[(rel, fn.name)] = (fn, module.stem, imports)
    return by_key, routes


def _reaches_gate(callees: frozenset, by_key: dict[tuple[str, str], list[frozenset]]) -> bool:
    seen: set = set()
    stack = list(callees)
    while stack:
        item = stack.pop()
        if item in _GATES:
            return True
        if item in seen:
            continue
        seen.add(item)
        for nxt in by_key.get(item, ()):
            stack.extend(nxt)
    return False


def ungated_upload_routes() -> list[str]:
    by_key, routes = _index()
    out = []
    for rel, name, line, called in routes:
        if f"{rel}:{name}" in _DOCUMENTED_EXCEPTIONS:
            continue
        fn, stem, imports = _CONTEXT[(rel, name)]
        if not _reaches_gate(called, by_key):
            out.append(f"{rel}:{line} {name} (no gate)")
        elif not _gate_precedes_body_read(fn, stem, imports, by_key):
            out.append(f"{rel}:{line} {name} (reads the body before the gate)")
    return out


def test_the_sweep_finds_the_upload_routes():
    _, routes = _index()
    assert len(routes) >= _UPLOAD_ROUTE_FLOOR, (
        f"FIX THE SWEEP: found {len(routes)} UploadFile routes, floor is {_UPLOAD_ROUTE_FLOOR}; "
        "a clean result here means nothing."
    )


def test_every_upload_route_reaches_is_safe_file():
    missing = ungated_upload_routes()
    assert not missing, (
        "UploadFile route(s) never reach is_safe_file / require_safe_upload "
        "(security.upload_filename_policy), or document an ARCHITECTURE_EXCEPTIONS.md entry: " + ", ".join(missing)
    )


def test_control_an_ungated_route_is_detected_and_a_gated_one_is_not():
    def callees(src: str) -> frozenset:
        tree = ast.parse(src)
        fn = _functions(src)[0]
        assert _is_route(fn) and _takes_upload(fn)
        return _callees(fn, "mod", _import_map(tree))

    head = '@router.post("/x")\nasync def up(file: UploadFile = File(...)):\n'
    # `read` is a method name; it must not resolve to an unrelated gated function.
    assert not _reaches_gate(
        callees(head + "    return await file.read()\n"), {("mod", "read"): [frozenset({"is_safe_file"})]}
    )
    assert _reaches_gate(callees(head + "    require_safe_upload(file.filename)\n"), {})
    delegated = "from helpers import helper\n" + head + "    return await helper(file)\n"
    assert _reaches_gate(callees(delegated), {("helpers", "helper"): [frozenset({"is_safe_file"})]})
    module_call = "import theme_install\n" + head + "    return await theme_install.go(file)\n"
    assert _reaches_gate(callees(module_call), {("theme_install", "go"): [frozenset({"require_safe_upload"})]})


def test_control_a_form_reading_route_is_an_upload_route_and_needs_the_gate():
    src = '@router.post("/u")\nasync def up(req: Request):\n    form = await req.form()\n    return await form.get("file").read()\n'
    fn = _functions(src)[0]
    assert _is_route(fn) and _takes_upload(fn)
    assert not _reaches_gate(_callees(fn, "mod", _import_map(ast.parse(src))), {})
    gated = src.replace("    return", "    require_safe_upload(form.get('file').filename)\n    return")
    fn = _functions(gated)[0]
    assert _reaches_gate(_callees(fn, "mod", _import_map(ast.parse(gated))), {})
    plain = '@router.post("/u")\nasync def up(req: Request):\n    return await req.json()\n'
    assert not _takes_upload(_functions(plain)[0])


def test_control_a_gate_after_the_body_read_is_flagged():
    head = '@router.post("/u")\nasync def up(file: UploadFile):\n'
    late = head + "    data = await file.read()\n    require_safe_upload(file.filename)\n"
    early = head + "    require_safe_upload(file.filename)\n    data = await file.read()\n"
    for src, expected in ((late, False), (early, True)):
        fn = _functions(src)[0]
        assert _gate_precedes_body_read(fn, "mod", _import_map(ast.parse(src)), {}) is expected
