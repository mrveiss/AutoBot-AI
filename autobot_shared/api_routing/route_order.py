# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The routes of an app IN REGISTRATION ORDER, read from source alone (#18720).

Starlette matches a request against routes in the order they were registered and the first FULL match
wins. A ``{param}`` (or ``{x:path}``) route registered before a literal route of the same method
therefore captures the literal's requests, and the literal handler never runs. Nothing in the suite saw
this: a per-router test mounts one router, and ``mount_graph`` / ``router_routes`` answer *which* routes
exist, not *in what order* the app tries them.

This module is the order-preserving read. It never imports the app (importing the backend pulls in the
whole service stack), so it reads source with ``ast`` and is blind to what only exists at runtime:

* routes added by a loop or a computed path -- counted in :attr:`RouteOrder.unresolved`, never dropped;
* ``include_router`` calls whose receiver or child is not a plain imported name;
* a router mounted with a non-literal ``prefix=``.

Ordering rules it models, each matching how FastAPI builds the list:

* a router's own decorators in source order, then the routers included into it (``X.include_router(Y)``
  anywhere in the tree), in file then line order -- the includes run after the defining module;
* a registry/``main.py`` mount appends that router's whole flattened list at that point.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

__all__ = ["OrderedRoute", "RouteOrder", "shadowed_literals"]

_VERBS = ("get", "post", "put", "patch", "delete", "head", "options")
_SKIP_PARTS = frozenset({"tests", "node_modules", ".venv", "venv", "__pycache__", "migrations"})
Key = Tuple[str, str]


@dataclass(frozen=True)
class OrderedRoute:
    """One HTTP route as the app would try it: position in the list is registration order."""

    method: str
    path: str
    site: str


@dataclass
class _Module:
    is_package: bool
    imports: Dict[str, Key] = field(default_factory=dict)
    prefixes: Dict[str, str] = field(default_factory=dict)
    routes: Dict[str, List[Tuple[int, str, str]]] = field(default_factory=dict)


def _const_str(node: Optional[ast.AST]) -> Optional[str]:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _kwarg(call: ast.Call, name: str) -> Optional[ast.AST]:
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def is_test_path(path: Path) -> bool:
    name = path.name
    return name.endswith("_test.py") or name.startswith("test_") or bool(_SKIP_PARTS & set(path.parts))


class RouteOrder:
    """Parse once per module; resolve router keys and flatten them in registration order."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.unresolved: List[str] = []
        self.parsed: List[str] = []
        self._modules: Dict[str, Optional[_Module]] = {}
        self._includes: Optional[Dict[Key, List[Tuple[Key, str]]]] = None

    # -- module loading ---------------------------------------------------------------------------

    def module_file(self, dotted: str) -> Optional[Path]:
        stem = self.root.joinpath(*dotted.split("."))
        for candidate in (stem.with_suffix(".py"), stem / "__init__.py"):
            if candidate.is_file():
                return candidate
        return None

    def load(self, dotted: str) -> Optional[_Module]:
        if dotted not in self._modules:
            self._modules[dotted] = self._parse(dotted)
        return self._modules[dotted]

    def _parse(self, dotted: str) -> Optional[_Module]:
        path = self.module_file(dotted)
        if path is None:
            return None
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            self.unresolved.append(f"{dotted}: unparseable")
            return None
        mod = _Module(is_package=path.name == "__init__.py")
        self.parsed.append(path.relative_to(self.root).as_posix())
        _collect_imports(tree, dotted, mod)
        _collect_routers(tree, mod)
        _collect_routes(tree, dotted, mod, self.unresolved)
        return mod

    # -- identity ---------------------------------------------------------------------------------

    def canon(self, dotted: str, name: str) -> Optional[Key]:
        """The ``(module, var)`` that actually defines router *name* as seen from *dotted*."""
        for _ in range(6):
            mod = self.load(dotted)
            if mod is None:
                return None
            if name in mod.prefixes:
                return (dotted, name)
            if name not in mod.imports:
                return None
            dotted, name = mod.imports[name]
        return None

    def canon_expr(self, dotted: str, expr: ast.expr) -> Optional[Key]:
        """:meth:`canon` for ``router`` or ``imported_module.router``."""
        if isinstance(expr, ast.Name):
            return self.canon(dotted, expr.id)
        mod = self.load(dotted)
        if not (isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name) and mod):
            return None
        base, name = mod.imports.get(expr.value.id, ("", ""))
        return self.canon(f"{base}.{name}", expr.attr) if base else None

    # -- includes ---------------------------------------------------------------------------------

    def includes(self) -> Dict[Key, List[Tuple[Key, str]]]:
        """parent key -> [(child key, include prefix)], in file then line order."""
        if self._includes is None:
            found: Dict[Key, List[Tuple[Key, str]]] = {}
            for path in sorted(self.root.rglob("*.py")):
                if not is_test_path(path.relative_to(self.root)):
                    self._scan_includes(path, found)
            self._includes = found
        return self._includes

    def _scan_includes(self, path: Path, found: Dict[Key, List[Tuple[Key, str]]]) -> None:
        text = path.read_text(encoding="utf-8", errors="replace")
        if ".include_router(" not in text:
            return
        dotted = _dotted(path.relative_to(self.root))
        calls = [n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Call) and _is_include(n)]
        for call in sorted(calls, key=lambda c: c.lineno):
            parent, child = call.func.value.id, call.args[0]  # type: ignore[attr-defined]
            pkey, ckey = self.canon(dotted, parent), self.canon_expr(dotted, child)
            if parent == "app":  # the FastAPI app itself, mounted by the caller in registration order
                continue
            if pkey is None or ckey is None:
                self.unresolved.append(f"{dotted}:{call.lineno} include_router({ast.unparse(child)}) unresolved")
                continue
            found.setdefault(pkey, []).append((ckey, _const_str(_kwarg(call, "prefix")) or ""))

    # -- flattening -------------------------------------------------------------------------------

    def flatten(self, key: Key, _seen: Tuple[Key, ...] = ()) -> List[OrderedRoute]:
        """Routes of router *key*, own prefix applied, own decorators then included routers."""
        mod = self.load(key[0])
        if mod is None or key in _seen:
            return []
        prefix = mod.prefixes[key[1]]
        out = [
            OrderedRoute(method, _join(prefix, path), f"{key[0]}:{line}")
            for line, method, path in sorted(mod.routes.get(key[1], []))
        ]
        for child, inc_prefix in self.includes().get(key, []):
            for route in self.flatten(child, _seen + (key,)):
                out.append(OrderedRoute(route.method, _join(prefix, inc_prefix, route.path), route.site))
        return out

    def mount(self, key: Key, prefix: str) -> List[OrderedRoute]:
        """*key* mounted on the app at *prefix*."""
        return [OrderedRoute(r.method, _join(prefix, r.path), r.site) for r in self.flatten(key)]


def _join(*parts: str) -> str:
    joined = "".join(parts)
    while "//" in joined:
        joined = joined.replace("//", "/")
    return joined


def _dotted(rel: Path) -> str:
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _is_include(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "include_router"
        and isinstance(node.func.value, ast.Name)
        and bool(node.args)
        and isinstance(node.args[0], (ast.Name, ast.Attribute))
    )


def _collect_imports(tree: ast.AST, dotted: str, mod: _Module) -> None:
    package = dotted if mod.is_package else dotted.rpartition(".")[0]
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        base = node.module or ""
        if node.level:
            anchor = package.split(".") if package else []
            anchor = anchor[: len(anchor) - (node.level - 1)] if node.level > 1 else anchor
            base = ".".join(anchor + ([node.module] if node.module else []))
        for alias in node.names:
            mod.imports[alias.asname or alias.name] = (base, alias.name)


def _collect_routers(tree: ast.AST, mod: _Module) -> None:
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        func = node.value.func
        if getattr(func, "id", getattr(func, "attr", "")) != "APIRouter":
            continue
        prefix = _const_str(_kwarg(node.value, "prefix")) or ""
        for target in node.targets:
            if isinstance(target, ast.Name):
                mod.prefixes[target.id] = prefix


def _decorator_routes(func: ast.AST, mod: _Module) -> Iterable[Tuple[str, int, str, Optional[str]]]:
    for dec in getattr(func, "decorator_list", []):
        if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
            continue
        owner = dec.func.value
        if not (isinstance(owner, ast.Name) and owner.id in mod.prefixes and dec.func.attr in _VERBS):
            continue
        arg = dec.args[0] if dec.args else _kwarg(dec, "path")
        yield owner.id, dec.lineno, dec.func.attr.upper(), _const_str(arg)


def _collect_routes(tree: ast.AST, dotted: str, mod: _Module, unresolved: List[str]) -> None:
    for node in ast.walk(tree):
        for var, line, method, path in _decorator_routes(node, mod):
            if path is None:
                unresolved.append(f"{dotted}:{line} non-literal route path")
                continue
            mod.routes.setdefault(var, []).append((line, method, path))


# -- the two apps -------------------------------------------------------------------------------------

#: ``load_optional_routers`` order after ``load_core_routers`` (initialization/routers.py).
BACKEND_REGISTRIES = (
    "core_routers",
    "analytics_routers",
    "terminal_routers",
    "monitoring_routers",
    "integration_routers",
    "feature_routers",
    "mcp_routers",
)


def _registry_entry(elts: List[ast.expr]) -> Optional[Tuple[ast.expr, str, str]]:
    """``(module-or-router expr, attr, prefix)`` for one registry tuple, else ``None``."""
    if len(elts) < 4:
        return None
    five = len(elts) >= 5 and _const_str(elts[1]) is not None and _const_str(elts[2]) is not None
    attr, prefix = (_const_str(elts[1]), _const_str(elts[2])) if five else ("router", _const_str(elts[1]))
    return (elts[0], attr or "router", prefix) if prefix is not None else None


def backend_routes(order: RouteOrder) -> List[OrderedRoute]:
    """The backend app's routes, in the order ``app_factory._register_routers`` includes them."""
    out: List[OrderedRoute] = []
    for name in BACKEND_REGISTRIES:
        dotted = f"initialization.router_registry.{name}"
        path = order.module_file(dotted)
        if path is None:
            order.unresolved.append(f"{dotted}: registry missing")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        tuples = sorted((n for n in ast.walk(tree) if isinstance(n, ast.Tuple)), key=lambda n: (n.lineno, n.col_offset))
        for node in tuples:
            entry = _registry_entry(node.elts)
            if entry is not None:
                out.extend(_mount_entry(order, dotted, *entry))
    return out


def _mount_entry(order: RouteOrder, registry: str, head: ast.expr, attr: str, prefix: str) -> List[OrderedRoute]:
    module = _const_str(head)
    key = order.canon(module, attr) if module else None
    if module is None and isinstance(head, ast.Name):
        key = order.canon(registry, head.id)
    if key is None:
        if module is not None or isinstance(head, ast.Name):
            order.unresolved.append(f"{registry}: registry entry {module or getattr(head, 'id', '?')} unresolved")
        return []
    return order.mount(key, f"/api{prefix}")


def slm_routes(order: RouteOrder) -> List[OrderedRoute]:
    """The SLM app's routes, in ``main.py``'s ``app.include_router`` order."""
    path = order.module_file("main")
    if path is None:
        order.unresolved.append("main: missing")
        return []
    calls = [
        n
        for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "include_router"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "app"
        and n.args
        and isinstance(n.args[0], ast.Name)
    ]
    out: List[OrderedRoute] = []
    for call in sorted(calls, key=lambda c: c.lineno):
        key = order.canon("main", call.args[0].id)  # type: ignore[attr-defined]
        if key is None:
            order.unresolved.append(f"main:{call.lineno} include_router unresolved")
            continue
        out.extend(order.mount(key, _const_str(_kwarg(call, "prefix")) or ""))
    return out


# -- the check ----------------------------------------------------------------------------------------


_PARAM = re.compile(r"\{([^}:]+)(:[^}]+)?\}")


def sample_url(path: str) -> str:
    """A concrete URL the route *path* serves: ``{x}`` -> ``x``, ``{x:path}`` -> ``x/y``."""
    return _PARAM.sub(lambda m: "x/y" if m.group(2) == ":path" else "x", path)


def shadowed_literals(routes: List[OrderedRoute]) -> List[Tuple[OrderedRoute, OrderedRoute]]:
    """``(route, earlier route)`` for every route whose URL a prior same-method route already takes.

    A literal is tested as-is; a param route through :func:`sample_url`, so a ``{x:path}``
    swallowing a later ``{x:path}/audit`` (#18720's a2a and vnc-proxy shapes) is caught by the
    walk, not only by pinned cases. The match is Starlette's own compiled regex, anchored. Same
    method only: a different method is a partial match and Starlette keeps looking. An earlier
    route with the identical path is a duplicate registration, not a shadow (#17325's job).
    """
    from starlette.routing import compile_path

    seen: Dict[str, List[Tuple[OrderedRoute, object]]] = {}
    registered: set = set()
    hits: List[Tuple[OrderedRoute, OrderedRoute]] = []
    for route in routes:
        if (route.method, route.path) in registered:  # a repeat: its first registration already answered
            continue
        registered.add((route.method, route.path))
        earlier = seen.setdefault(route.method, [])
        url = sample_url(route.path) if "{" in route.path else route.path
        for prior, regex in earlier:
            if regex.match(url):  # type: ignore[attr-defined]
                hits.append((route, prior))
                break
        earlier.append((route, compile_path(route.path)[0]))
    return hits
