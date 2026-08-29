# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The router mount graph, derived from source rather than from a running app.

Two repo guards need the same three facts — which ``APIRouter`` objects exist,
which ``include_router`` calls mount which of them, and what each hop carries:

* ``repo_tests/router_mount_parity_test.py`` (#15098) — is a router reachable
  through a mount that skips a gate its other mounts apply?
* ``repo_tests/router_routes_traversal_test.py`` (#15093) — does anything read
  ``<router>.routes`` on a router that has children?

They were one file's private machinery until #15093. Two copies of an AST
resolver drift the way the two ``include_router`` regexes in
``router_prefixes.py`` drifted (#12985): one gets a resolution fix, the other
does not, and the gate that decides whether a PR may merge disagrees with the
report a human reads to judge it. This is the single copy.

## Why static

Under ``fastapi>=0.139`` ``include_router`` defers, and neither the include-time
``prefix=`` nor an include-time ``dependencies=`` list is recoverable through
the *public* route objects afterwards (#15093, and see
``autobot_shared/api_routing/router_routes.py`` for the runtime half). Correction
(#15126, verified against fastapi 0.141.1's own ``routing.py``): the prefix is
not actually gone -- ``_IncludedRouter.include_context.prefix`` carries the
combined value -- it is only unreachable from the *public* surface every
runtime consumer here reads. Depending on that private, underscore-prefixed
pair would mean trusting an implementation detail with no stability guarantee
across a version bump, which is a worse bet than the deferral itself. A
development checkout may resolve a lower FastAPI where some of it *is* publicly
readable (#15091), so a runtime-introspection guard would mean one thing
locally and another in CI regardless — worse than no guard. Parsing the
registration sites is version-independent, which is the property both
consumers need.

## What it cannot see

* A mount whose target is computed at runtime. ``app_factory`` iterates the
  registry tuples and includes a loop variable; those are recorded as
  ``dynamic`` and modelled from the registry entries instead. Any *other*
  dynamic mount is recorded too, so it can be failed on rather than skipped.
* An attribute chain rooted in a local variable — ``bridge.router.routes``
  resolves no further than the literal text. Such reads are returned with
  ``target=None`` rather than silently dropped.
* A gate applied by anything other than a ``dependencies=`` argument:
  middleware path matching, a decorator, an in-body ``Depends``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

__all__ = [
    "APP_ROOT",
    "Mount",
    "MountGraph",
    "ModuleScan",
    "RouterDef",
    "RoutesRead",
    "build_graph",
    "is_relevant",
    "module_name",
    "python_files",
    "registry_dirname",
]

#: Directory name under ``initialization/`` whose tuples the app factory mounts.
_REGISTRY_DIRNAME = "router_registry"

#: Never walked: build output, vendored trees, virtualenvs.
_SKIP_DIRS: FrozenSet[str] = frozenset({"__pycache__", "node_modules", ".venv", "venv", ".git"})

# The synthetic parent for a mount performed by the application factory: every
# registry entry is included by `app_factory` with `prefix=f"/api{prefix}"` and
# no `dependencies=`, so the app root contributes no guard.
APP_ROOT = "<app>"


def registry_dirname() -> str:
    """The registry directory name, so consumers do not re-spell it."""
    return _REGISTRY_DIRNAME


@dataclass(frozen=True)
class RoutesRead:
    """One ``<expr>.routes`` read found in source."""

    site: str
    expr: str
    target: Optional[str]


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
    #: The literal ``prefix=`` argument at *this* ``include_router`` call, or
    #: ``None`` when absent or not a plain string literal (#15126) -- the
    #: include-time term #15093 found unreadable from the route objects after
    #: the fact (see ``router_routes.py``). A registry-entry edge always leaves
    #: this ``None``: ``app_factory`` mounts those with a computed
    #: ``prefix=f"/api{prefix}"``, not a literal at the call site. ``None`` and
    #: ``""`` are distinct, matching ``router_prefixes.apirouter_prefix``.
    prefix: Optional[str] = None


@dataclass
class MountGraph:
    routers: Dict[str, RouterDef] = field(default_factory=dict)
    edges: List[Mount] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)
    dynamic: List[str] = field(default_factory=list)
    routes_reads: List[RoutesRead] = field(default_factory=list)

    def paths_to(self, key: str) -> Set[FrozenSet[str]]:
        """Every distinct guard set that reaches *key* from the app root.

        A guard set is the union of the dependencies named at each hop: the
        ``dependencies=`` of the ``include_router`` call plus those declared on
        the parent's own ``APIRouter(...)`` constructor, all the way up --
        **and the router's own constructor dependencies**, which apply at every
        mount by construction.

        That last term is the one that matters. A router protected on its own
        constructor is protected everywhere, which is exactly how #15084 was
        fixed and how every other gated router in this repo is written. Omitting
        it made such a router read as ungated on every path, so the comparison
        was empty-set against empty-set: agreement reached by seeing nothing
        rather than by seeing a gate.
        """
        own = self._own_guards(key)
        return {path | own for path in self._paths(key, frozenset())}

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

    def inconsistent(self, exempt: Iterable[str] = ()) -> Dict[str, Set[FrozenSet[str]]]:
        """Routers whose reachable paths do not all carry the same guards.

        A router mounted once, or mounted many times with identical guards, is
        consistent. One reachable both behind ``check_admin_permission`` and
        without it is the defect. *exempt* names keys to skip; the caller owns
        that list because it also owns the reason each entry carries.
        """
        bad: Dict[str, Set[FrozenSet[str]]] = {}
        exempt_keys = set(exempt)
        for key in self.mounted_keys():
            if key in exempt_keys:
                continue
            paths = self.paths_to(key)
            if len(paths) < 2:
                continue
            weakest = frozenset.intersection(*paths)
            strongest = frozenset.union(*paths)
            if weakest != strongest:
                bad[key] = paths
        return bad

    def routers_with_children(self) -> Set[str]:
        """Keys of routers that receive at least one ``include_router`` call.

        Reading ``.routes`` on one of these is the #15093 defect: under
        ``fastapi>=0.139`` the list holds a deferred wrapper per included child
        rather than the children's routes. Every other router's ``.routes`` is
        built from decorators alone and is the same on both FastAPI shapes.
        """
        return {edge.parent for edge in self.edges if edge.parent != APP_ROOT}


# --- source parsing ---------------------------------------------------------


def module_name(path: Path, root: Path) -> str:
    """Dotted import name for *path* relative to *root*.

    ``__init__`` is stripped, so ``llc/api/__init__.py`` is ``llc.api`` — the
    name every importer actually writes and the name a registry entry spells.
    Leaving it in produced two spellings of one router: definitions landed under
    ``llc.api.__init__:router`` while mounts and imports named ``llc.api:router``,
    so a package router's own constructor guards were attached to a key nothing
    else referenced and read as absent everywhere.
    """
    parts = path.relative_to(root).with_suffix("").as_posix().split("/")
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


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


def _string_literal(node: ast.AST | None) -> str | None:
    """*node*'s value if it is a plain string constant, else ``None``.

    An f-string or a name reference is real but not statically resolvable here;
    treated the same as "no ``prefix=``" rather than guessed at (#15126).
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _routes_subject(node: ast.AST) -> Optional[ast.AST]:
    """The expression whose ``routes`` *node* reads, or ``None``.

    Both spellings count. ``x.routes`` is the obvious one; ``getattr(x, "routes", [])``
    is the same read written so it cannot raise, which is the strictly more
    dangerous form — on the deferred shape it turns "this router has children I
    cannot see" into an empty list and an assertion over nothing (#15087).
    """
    if isinstance(node, ast.Attribute) and node.attr == "routes" and isinstance(node.ctx, ast.Load):
        return node.value
    if not isinstance(node, ast.Call) or _dotted(node.func) != "getattr" or len(node.args) < 2:
        return None
    name = node.args[1]
    if isinstance(name, ast.Constant) and name.value == "routes":
        return node.args[0]
    return None


def _is_apirouter(call: ast.Call) -> bool:
    """Whether *call* constructs an ``APIRouter``, plain or dotted.

    The ``None`` branch is explicit rather than folded into ``bool(rendered) and
    rendered.split(...)``. That spelling never reached ``.split`` with ``None`` —
    ``and`` short-circuits — so this is a narrowing the checker can follow, not a
    bug fix, and the two forms select exactly the same calls. ``_dotted`` cannot
    return ``""`` either: it always joins at least one identifier.
    """
    rendered = _dotted(call.func)
    if rendered is None:
        return False
    return rendered.split(".")[-1] == "APIRouter"


@dataclass
class _Buckets:
    """The node kinds one ``ast.walk`` collects, each keeping its own type.

    A ``Dict[type, List[ast.AST]]`` would be shorter and is what this was first
    written as, but it erases the element type: every later pass then reads
    ``.func`` / ``.module`` / ``.targets`` off a bare ``ast.AST``, which the type
    checker cannot verify and a future edit could get wrong with nothing saying
    so. Five named lists cost five lines and make each pass's assumption explicit.

    ``isinstance`` rather than ``type(node) is ...`` when filling these: it is
    what the passes used before they were merged into one walk, and it stays
    correct if a node kind ever gains a subclass. None of these five has one
    today — ``AsyncFor`` is a sibling of ``For``, not a subclass, and
    ``AnnAssign``/``AugAssign`` are siblings of ``Assign`` — so the two spellings
    select the same nodes now, and ``isinstance`` is the one that keeps doing so.
    """

    fors: List[ast.For] = field(default_factory=list)
    imports: List[ast.ImportFrom] = field(default_factory=list)
    assigns: List[ast.Assign] = field(default_factory=list)
    calls: List[ast.Call] = field(default_factory=list)
    attributes: List[ast.Attribute] = field(default_factory=list)


class ModuleScan:
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
        self.routes_reads: List[RoutesRead] = []
        self._nodes = _Buckets()

    def run(self) -> None:
        """One ``ast.walk``, then five passes over what it bucketed.

        Walking the tree once per pass was five full traversals of every module
        in the repo — around four minutes for the trees this scans. The passes
        still run in order, because it is load-bearing: imports bind names first,
        module-local definitions then override an imported name of the same
        spelling, and only after both can a mount or a ``.routes`` read resolve.
        """
        buckets = _Buckets()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.For):
                buckets.fors.append(node)
            elif isinstance(node, ast.ImportFrom):
                buckets.imports.append(node)
            elif isinstance(node, ast.Assign):
                buckets.assigns.append(node)
            elif isinstance(node, ast.Call):
                buckets.calls.append(node)
            elif isinstance(node, ast.Attribute):
                buckets.attributes.append(node)
        self._nodes = buckets
        self._collect_loop_targets()
        self._collect_imports()
        self._collect_definitions()
        self._collect_include_calls()
        self._collect_routes_reads()

    def _collect_routes_reads(self) -> None:
        """Every ``<expr>.routes`` attribute read in this module.

        The expression is resolved with the same bindings the mount graph uses,
        so ``from llc.api import router as llc_router`` followed by
        ``llc_router.routes`` yields ``llc.api:router`` — the key the graph knows
        as a parent of thirty-eight inclusions.

        An unresolvable expression is kept with ``target=None`` rather than
        dropped. It is a blind spot either way, but a recorded one can be
        counted and reported; a dropped one cannot be told apart from a scan
        that matched nothing.
        """
        reads: List[ast.expr] = [*self._nodes.attributes, *self._nodes.calls]
        for node in reads:
            subject = _routes_subject(node)
            if subject is None:
                continue
            expr = _dotted(subject) or "<expr>"
            self.routes_reads.append(
                RoutesRead(site=f"{self.module}:{node.lineno}", expr=expr, target=self._resolve(subject))
            )

    def _collect_loop_targets(self) -> None:
        """Names bound by a ``for`` statement.

        ``app_factory`` iterates the loaded registry tuples and calls
        ``include_router`` on the loop variable. That mount is real but its
        target is only known at runtime — it is modelled from the registry
        entries instead, so it must be recorded as *dynamic*, not as an
        unresolvable reference.
        """
        for node in self._nodes.fors:
            targets = node.target.elts if isinstance(node.target, ast.Tuple) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    self.loop_targets.add(target.id)

    # imports first: `from api.x import router as y` binds y -> api.x:router.
    def _collect_imports(self) -> None:
        for node in self._nodes.imports:
            if node.module is None:
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
        for node in self._nodes.assigns:
            if not isinstance(node.value, ast.Call):
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
        for node in self._nodes.calls:
            if not isinstance(node.func, ast.Attribute):
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
            prefix = _string_literal(_call_kwarg(node, "prefix"))
            self.edges.append(Mount(parent=parent, child=child, guards=guards, site=site, prefix=prefix))


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
    module = module_name(path, backend)
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


#: A file with none of these tokens defines no router, mounts none, and reads
#: no ``routes`` attribute, so parsing it can only produce empty results. Kept
#: as a whole-word-ish substring test rather than a regex: it runs once per file
#: over thousands of files and is pure cost when it does not match.
_RELEVANT_TOKENS = ("APIRouter", "include_router", ".routes", '"routes"', "'routes'")


def is_relevant(source: str) -> bool:
    """Whether *source* can contribute anything to a mount graph.

    ``initialization/router_registry/*.py`` is exempted by its caller rather
    than by a token here: those files are pure data — tuples of module paths the
    app factory mounts — so a registry naming only modules contains none of
    these tokens and dropping it silently loses every app-root mount it declares.
    """
    return any(token in source for token in _RELEVANT_TOKENS)


def python_files(root: Path, skip: FrozenSet[str] = _SKIP_DIRS) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if set(path.parts) & skip:
            continue
        yield path


def build_graph(backend: Path, skip: FrozenSet[str] = _SKIP_DIRS | frozenset({"tests"})) -> MountGraph:
    """Derive the whole mount graph from source — nothing is handed in.

    Three discovery sources, matching the three ways a router reaches the app:
    ``APIRouter`` definitions, ``include_router`` call sites, and
    ``initialization/router_registry/`` entries loaded by the app factory.
    """
    graph = MountGraph()
    registry_files: List[Tuple[Path, Dict[str, str]]] = []
    for path in python_files(backend, skip):
        try:
            source = path.read_text(encoding="utf-8")
            if not is_relevant(source) and _REGISTRY_DIRNAME not in path.parts:
                continue
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError) as exc:  # pragma: no cover
            graph.unresolved.append(f"{path}: {exc}")
            continue
        scan = ModuleScan(module_name(path, backend), tree, backend)
        scan.run()
        for definition in scan.defs:
            graph.routers[definition.key] = definition
        graph.edges.extend(scan.edges)
        graph.unresolved.extend(scan.unresolved)
        graph.dynamic.extend(scan.dynamic)
        graph.routes_reads.extend(scan.routes_reads)
        if _REGISTRY_DIRNAME in path.parts:
            registry_files.append((path, dict(scan.local)))
    for path, local in registry_files:
        graph.edges.extend(_scan_registry(path, backend, local))
    return graph
