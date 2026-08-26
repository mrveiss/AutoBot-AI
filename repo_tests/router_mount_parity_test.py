# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A router gated on one mount and wide open on another (#15098).

``api/terminal_tools.py`` owns four routes that install packages and run system
commands. It was mounted twice:

* ``api/terminal.py`` — into ``admin_router``, which carries
  ``dependencies=[Depends(check_admin_permission)]``. Correctly gated.
* ``initialization/router_registry/terminal_routers.py`` — as a **top-level
  registry entry with an empty prefix**, which ``app_factory`` mounts at
  ``/api`` with **no** ``dependencies=``.

So ``/api/install-tool``, ``/api/check-tool``, ``/api/validate-command`` and
``/api/package-managers`` were reachable with no admin check
(#15084, fixed by #15096). ``SERVICE_ONLY_PATHS`` in the service-auth
middleware never covered them — it lists ``/api/npu/*``, ``/api/ai-stack/*``
and ``/api/browser/*`` only.

**Why every existing test stayed green.** Each one asserted the gate on the
``terminal.py`` mount. None enumerated *where else* the router is mounted. A
per-mount assertion is structurally blind to a second mount: it passes forever
while the same routes are served ungated from another path.

This guard closes that class rather than that instance. It derives the mount
graph from source and fails when a router is reachable through a mount that
lacks protection its other mounts carry.

Static, not runtime
-------------------

Under fastapi 0.141.1 (what CI resolves) ``include_router`` defers: neither the
prefix nor an inherited ``dependencies=`` is readable off the route object, so
runtime introspection cannot see what this guard needs (#15093). This box
resolves 0.135.2 (#15091), where some of it *is* readable — a runtime guard
would therefore mean one thing locally and another in CI, which is worse than
no guard. Parsing the registration sites is version-independent and answers the
question actually being asked: *is this router mounted somewhere that skips a
gate its other mounts apply?*

The trade this accepts: a gate applied by something other than a
``dependencies=`` argument (middleware path matching, a decorator, an in-body
``Depends``) is invisible here. Those are named in ``EXEMPT_ROUTERS`` with a
reason each — never counted.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Set, Tuple

import pytest

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "autobot-backend"
_REGISTRY_DIRNAME = "router_registry"

# The synthetic parent for a mount performed by the application factory: every
# registry entry is included by `app_factory` with `prefix=f"/api{prefix}"` and
# no `dependencies=`, so the app root contributes no guard.
APP_ROOT = "<app>"

# Routers that legitimately reach the app through a mount carrying less than
# another mount of theirs. Each needs a reason; a bare count is not evidence
# and would hide the next `terminal_tools`.
EXEMPT_ROUTERS: Dict[str, str] = {
    # Self-retiring. #15084 is the instance this guard was written for and is
    # still open on the base branch; #15096 removes the ungated registry entry.
    # `test_exemptions_are_named_and_still_real` FAILS the moment that lands,
    # forcing this line out — an exemption here cannot outlive its reason.
    "api.terminal_tools:router": (
        "#15084: gated via api/terminal.py's admin_router, ungated via the terminal "
        "registry entry. Fix in flight as #15096; this entry expires when it merges."
    ),
}

# Names that read as a gate when they appear in a `dependencies=` list. Used
# only for the non-vacuity check below — the parity comparison itself is
# name-agnostic and compares whatever dependency names it finds.
_GATE_HINTS = ("permission", "auth", "admin", "rbac", "require", "verify", "current_user")


@dataclass(frozen=True)
class RouterDef:
    """A module-level ``X = APIRouter(...)`` binding."""

    key: str
    own_guards: FrozenSet[str]


@dataclass(frozen=True)
class Mount:
    """One ``include_router`` (or registry entry) edge in the mount graph."""

    parent: str
    child: str
    guards: FrozenSet[str]
    site: str


@dataclass
class MountGraph:
    routers: Dict[str, RouterDef] = field(default_factory=dict)
    edges: List[Mount] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)
    dynamic: List[str] = field(default_factory=list)

    def paths_to(self, key: str) -> Set[FrozenSet[str]]:
        """Every distinct guard set that reaches *key* from the app root.

        A guard set is the union of the dependencies named at each hop: the
        ``dependencies=`` of the ``include_router`` call plus those declared on
        the parent's own ``APIRouter(...)`` constructor, all the way up.
        """
        return self._paths(key, frozenset())

    def _paths(self, key: str, seen: FrozenSet[str]) -> Set[FrozenSet[str]]:
        if key in seen:  # a cycle contributes nothing new
            return set()
        seen = seen | {key}
        incoming = [e for e in self.edges if e.child == key]
        if not incoming:
            return set()
        out: Set[FrozenSet[str]] = set()
        for edge in incoming:
            hop = edge.guards | self._own_guards(edge.parent)
            if edge.parent == APP_ROOT:
                out.add(hop)
                continue
            for upstream in self._paths(edge.parent, seen):
                out.add(hop | upstream)
        return out

    def _own_guards(self, key: str) -> FrozenSet[str]:
        found = self.routers.get(key)
        return found.own_guards if found else frozenset()

    def mounted_keys(self) -> List[str]:
        return sorted({e.child for e in self.edges})

    def inconsistent(self) -> Dict[str, Set[FrozenSet[str]]]:
        """Routers whose reachable paths do not all carry the same guards.

        A router mounted once, or mounted many times with identical guards, is
        consistent. One reachable both behind ``check_admin_permission`` and
        without it is the defect.
        """
        bad: Dict[str, Set[FrozenSet[str]]] = {}
        for key in self.mounted_keys():
            if key in EXEMPT_ROUTERS:
                continue
            paths = self.paths_to(key)
            if len(paths) < 2:
                continue
            weakest = frozenset.intersection(*paths)
            strongest = frozenset.union(*paths)
            if weakest != strongest:
                bad[key] = paths
        return bad


# --- source parsing ---------------------------------------------------------


def _module_name(path: Path, backend: Path) -> str:
    return path.relative_to(backend).with_suffix("").as_posix().replace("/", ".")


def _guards_from_keyword(node: ast.AST) -> FrozenSet[str]:
    """Dependency names inside a ``dependencies=[Depends(x), ...]`` argument."""
    names: Set[str] = set()
    if not isinstance(node, (ast.List, ast.Tuple)):
        return frozenset()
    for element in node.elts:
        target = element
        if isinstance(element, ast.Call):
            args = element.args
            target = args[0] if args else element.func
        rendered = _dotted(target)
        if rendered:
            names.add(rendered)
    return frozenset(names)


def _dotted(node: ast.AST) -> str | None:
    """Render ``a.b.c`` / ``a`` from an expression; None for anything else."""
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _call_kwarg(call: ast.Call, name: str) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _is_apirouter(call: ast.Call) -> bool:
    rendered = _dotted(call.func)
    return bool(rendered) and rendered.split(".")[-1] == "APIRouter"


class _ModuleScan:
    """Local-name -> router-key bindings and mounts within one module."""

    def __init__(self, module: str, tree: ast.AST, backend: Path):
        self.module = module
        self.tree = tree
        self.backend = backend
        self.local: Dict[str, str] = {}
        self.defs: List[RouterDef] = []
        self.edges: List[Mount] = []
        self.unresolved: List[str] = []
        self.dynamic: List[str] = []
        self.loop_targets: Set[str] = set()

    def run(self) -> None:
        self._collect_loop_targets()
        self._collect_imports()
        self._collect_definitions()
        self._collect_include_calls()

    def _collect_loop_targets(self) -> None:
        """Names bound by a ``for`` statement.

        ``app_factory`` iterates the loaded registry tuples and calls
        ``include_router`` on the loop variable. That mount is real but its
        target is only known at runtime — it is modelled from the registry
        entries instead, so it must be recorded as *dynamic*, not as an
        unresolvable reference.
        """
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.For):
                continue
            targets = node.target.elts if isinstance(node.target, ast.Tuple) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    self.loop_targets.add(target.id)

    # imports first: `from api.x import router as y` binds y -> api.x:router.
    def _collect_imports(self) -> None:
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            source = node.module
            if node.level:  # relative import, resolve against this package
                package = self.module.rsplit(".", node.level)[0]
                source = f"{package}.{node.module}" if package else node.module
            for alias in node.names:
                if "router" not in alias.name.lower():
                    continue
                self.local[alias.asname or alias.name] = f"{source}:{alias.name}"

    # definitions second, so a module-local `router = APIRouter()` wins over an
    # imported name of the same spelling.
    def _collect_definitions(self) -> None:
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            if not _is_apirouter(node.value):
                continue
            guards = _guards_from_keyword(_call_kwarg(node.value, "dependencies") or ast.List(elts=[]))
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                key = f"{self.module}:{target.id}"
                self.local[target.id] = key
                self.defs.append(RouterDef(key=key, own_guards=guards))

    def _resolve(self, node: ast.AST) -> str | None:
        rendered = _dotted(node)
        if rendered is None:
            return None
        if rendered in self.local:
            return self.local[rendered]
        if "." in rendered:  # `api.terminal.router` style reference
            module, _, attr = rendered.rpartition(".")
            return f"{module}:{attr}"
        return None

    def _collect_include_calls(self) -> None:
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "include_router" or not node.args:
                continue
            site = f"{self.module}:{node.lineno}"
            child_expr = _dotted(node.args[0])
            if child_expr in self.loop_targets:
                self.dynamic.append(site)
                continue
            child = self._resolve(node.args[0])
            if child is None:
                self.unresolved.append(f"{site} child={ast.dump(node.args[0])[:60]}")
                continue
            parent_expr = _dotted(node.func.value) or ""
            parent = self._resolve(node.func.value)
            if parent is None:
                # `app.include_router(...)` and friends: an application object,
                # not a router. Treat as an app-root mount.
                parent = APP_ROOT
                if parent_expr not in {"app", "application", "self.app"}:
                    self.unresolved.append(f"{site} parent={parent_expr or '<expr>'}")
            guards = _guards_from_keyword(_call_kwarg(node, "dependencies") or ast.List(elts=[]))
            self.edges.append(Mount(parent=parent, child=child, guards=guards, site=site))


# --- registry entries -------------------------------------------------------


def _registry_entry(element: ast.AST, module: str, local: Dict[str, str]) -> str | None:
    """Router key named by one ``(module, [attr,] prefix, tags, name)`` tuple.

    Both registry shapes are handled: a 4-tuple whose first element is a module
    path string (``("api.terminal_tools", "", [...], "terminal_tools")``), the
    5-tuple monitoring form that names the attribute second, and the
    ``core_routers`` form whose first element is an already-imported router.
    """
    if not isinstance(element, (ast.Tuple, ast.List)) or len(element.elts) < 4:
        return None
    head = element.elts[0]
    if isinstance(head, ast.Constant) and isinstance(head.value, str):
        attr = "router"
        second = element.elts[1]
        if len(element.elts) >= 5 and isinstance(second, ast.Constant) and isinstance(second.value, str):
            # 5-tuple: (module, router_attr, prefix, tags, name)
            attr = second.value or "router"
        return f"{head.value}:{attr}"
    rendered = _dotted(head)
    if rendered and rendered in local:
        return local[rendered]
    if rendered:
        return f"{module}:{rendered}"
    return None


def _scan_registry(path: Path, backend: Path, local: Dict[str, str]) -> List[Mount]:
    """Registry entries become app-root mounts carrying no guards.

    ``app_factory.register_routers`` includes each loaded tuple with
    ``prefix=f"/api{prefix}"`` and no ``dependencies=`` argument, so nothing a
    registry entry can express adds a gate.
    """
    module = _module_name(path, backend)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mounts: List[Mount] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Tuple)):
            continue
        for element in node.elts:
            key = _registry_entry(element, module, local)
            if key is None:
                continue
            mounts.append(
                Mount(
                    parent=APP_ROOT,
                    child=key,
                    guards=frozenset(),
                    site=f"{module}:{getattr(element, 'lineno', 0)}",
                )
            )
    return mounts


def _python_files(backend: Path) -> Iterable[Path]:
    for path in sorted(backend.rglob("*.py")):
        parts = set(path.parts)
        if parts & {"__pycache__", "tests", "node_modules", ".venv", "venv"}:
            continue
        yield path


def build_graph(backend: Path = _BACKEND) -> MountGraph:
    """Derive the whole mount graph from source — nothing is handed in.

    Three discovery sources, matching the three ways a router reaches the app:
    ``APIRouter`` definitions, ``include_router`` call sites, and
    ``initialization/router_registry/`` entries loaded by the app factory.
    """
    graph = MountGraph()
    registry_files: List[Tuple[Path, Dict[str, str]]] = []
    for path in _python_files(backend):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:  # pragma: no cover
            graph.unresolved.append(f"{path}: {exc}")
            continue
        scan = _ModuleScan(_module_name(path, backend), tree, backend)
        scan.run()
        for definition in scan.defs:
            graph.routers[definition.key] = definition
        graph.edges.extend(scan.edges)
        graph.unresolved.extend(scan.unresolved)
        graph.dynamic.extend(scan.dynamic)
        if _REGISTRY_DIRNAME in path.parts:
            registry_files.append((path, dict(scan.local)))
    for path, local in registry_files:
        graph.edges.extend(_scan_registry(path, backend, local))
    return graph


@pytest.fixture(scope="module")
def graph() -> MountGraph:
    return build_graph()


# --- non-vacuity ------------------------------------------------------------
#
# A discovery step that silently finds nothing reports success while inspecting
# nothing. Each assertion below fails loudly instead.


def test_discovery_found_routers(graph: MountGraph):
    assert len(graph.routers) >= 50, (
        f"non-vacuity: only {len(graph.routers)} APIRouter definitions discovered under "
        f"{_BACKEND.name}. Discovery is broken; the parity check below would inspect nothing."
    )


def test_discovery_found_mounts(graph: MountGraph):
    assert len(graph.edges) >= 100, (
        f"non-vacuity: only {len(graph.edges)} mount edges discovered. "
        "Expected include_router call sites plus every router_registry entry."
    )


def test_discovery_found_registry_mounts(graph: MountGraph):
    registry = [e for e in graph.edges if e.parent == APP_ROOT and _REGISTRY_DIRNAME in e.site]
    assert len(registry) >= 30, (
        f"non-vacuity: only {len(registry)} app-root mounts came from "
        f"initialization/{_REGISTRY_DIRNAME}/. That is where #15084's ungated mount lived."
    )


def test_discovery_can_see_a_gate(graph: MountGraph):
    """Guard detection must actually detect a guard somewhere.

    If ``dependencies=`` parsing broke, every mount would look equally ungated
    and the parity check would pass while comparing nothing but empty sets.
    """
    gated = {key: sorted(definition.own_guards) for key, definition in graph.routers.items() if definition.own_guards}
    gated_edges = [e for e in graph.edges if e.guards]
    assert gated or gated_edges, (
        "non-vacuity: no `dependencies=` was found on any APIRouter definition or any "
        "include_router call. Guard extraction is broken — every mount now compares as ungated."
    )
    hinted = [name for names in gated.values() for name in names if any(hint in name.lower() for hint in _GATE_HINTS)]
    assert hinted, f"non-vacuity: no discovered dependency reads as an auth gate. Found: {sorted(gated)[:10]}"


def test_terminal_tools_router_is_discovered(graph: MountGraph):
    """The #15084 router must be in the graph, whatever its mounts now are.

    #15096 removes its ungated registry entry; this asserts the *discovery*
    still reaches it, so the guard cannot go blind to the file it was built for.
    """
    assert "api.terminal_tools:router" in graph.routers
    mounts = [e for e in graph.edges if e.child == "api.terminal_tools:router"]
    assert mounts, "api.terminal_tools:router is defined but no mount of it was discovered"


def test_every_reference_resolved(graph: MountGraph):
    """An include_router whose target could not be resolved is a blind spot."""
    assert not graph.unresolved, "unresolvable router references:\n  " + "\n  ".join(sorted(graph.unresolved)[:20])


def test_dynamic_mounts_are_only_the_factory_loop(graph: MountGraph):
    """The one mount whose target is runtime-only must stay the factory loop.

    ``app_factory`` includes each loaded registry tuple through a loop
    variable; those mounts are modelled from the registry entries themselves.
    A dynamic ``include_router`` anywhere else is a mount this guard cannot
    see, so it fails here rather than being quietly skipped.
    """
    assert graph.dynamic, "non-vacuity: app_factory's registry loop was not discovered at all"
    stray = sorted({site for site in graph.dynamic if not site.startswith("app_factory:")})
    assert not stray, "include_router on a runtime-computed target outside app_factory:\n  " + "\n  ".join(stray)


# --- the guard --------------------------------------------------------------


def test_no_router_is_mounted_past_a_gate_its_siblings_carry(graph: MountGraph):
    """Fails when one mount of a router skips protection another mount applies.

    This is the named assertion. It does not know about ``terminal_tools`` or
    any other router by name: it compares, for every mounted router, the guard
    sets on every path that reaches it from the app root.
    """
    bad = graph.inconsistent()
    if not bad:
        return
    report: List[str] = []
    for key, paths in sorted(bad.items()):
        weakest = sorted(frozenset.intersection(*paths))
        missing = sorted(frozenset.union(*paths) - frozenset.intersection(*paths))
        sites = [f"{e.parent} -> {e.child} @ {e.site}" for e in graph.edges if e.child == key]
        report.append(
            f"{key}: reachable with guards {weakest or '[]'} while another mount applies {missing}\n"
            + "\n".join(f"    mount: {s}" for s in sorted(sites))
        )
    pytest.fail(
        "router(s) reachable through a mount lacking protection their other mounts carry "
        "(#15098 — the #15084 class):\n" + "\n".join(report)
    )


def test_exemptions_are_named_and_still_real(graph: MountGraph):
    """Every exemption carries a reason, and names a router that still exists.

    A stale exemption is a hole that nothing reports, so it is an error rather
    than a no-op.
    """
    for key, reason in EXEMPT_ROUTERS.items():
        assert reason.strip(), f"exemption {key} has no reason"
        assert key in graph.routers, f"exemption {key} names a router that no longer exists — drop it"
        paths = graph.paths_to(key)
        assert len(paths) >= 2 and frozenset.intersection(*paths) != frozenset.union(
            *paths
        ), f"exemption {key} is no longer needed: its mounts now agree. Remove it."
