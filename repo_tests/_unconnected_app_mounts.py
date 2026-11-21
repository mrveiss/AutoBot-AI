# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Mount prefixes of a backend with no router registry, read from its ``include_router`` graph (#20910).

The SLM backend has no ``initialization/router_registry``: ``main.py`` mounts each router with
``app.include_router(x, prefix="/api")`` (or ``/api/nodes``, or no prefix for SCIM), and
``api/__init__.py`` nests routers inside others (``monitoring_router.include_router(gpu_router)`` serves
``api/gpu.py`` under ``/api/monitoring/gpu``). Judging those routes at ``own prefix + path`` drops the
parent's prefix, so ``/api/gpu/nodes`` was compared with callers while the app serves
``/api/monitoring/gpu/nodes``.

The graph comes from ``autobot_shared.api_routing.mount_graph`` (the one AST resolver of routers and their
``include_router`` edges; the mount-parity and ``.routes`` guards read it too). This adds only the walk from
the app root, composing at every level::

    parent's mount + parent's own ``APIRouter(prefix=)`` + ``include_router(prefix=)``

The child's own prefix is NOT in the returned value (the caller adds it from the child's file), the same
contract as ``router_prefixes.module_included_router_files`` and ``_unconnected_mounts``.

WHAT THIS CANNOT SEE
--------------------
* What ``mount_graph`` cannot resolve: a mount whose target or parent is computed at runtime, an import
  whose bound name does not contain "router", ``import pkg.mod as m``.
* An ``include_router`` prefix that is not a string literal: it counts as no prefix.
* A router variable other than ``router``/``api_router``: its mounts are not recorded, the same boundary as
  the route decorators the gate reads (``orchestration.py`` nests ``fleet_router``, whose routes are unseen).
* A parent's own prefix is the first ``APIRouter(prefix=)`` in its file, whichever variable it is bound to.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

from autobot_shared.api_routing.mount_graph import APP_ROOT, ModuleScan, build_graph
from tools.lint._parse_cache import parse

#: The router variables whose route decorators the gate reads (``ROUTE_DECORATOR_RE``); ``app`` has no mount.
_JUDGED = ("router", "api_router")


def _key_file(backend_dir: Path, key: str) -> Path | None:
    """The source file of router key ``module:name``: the module, else the package ``__init__``."""
    base = backend_dir.joinpath(*key.rsplit(":", 1)[0].split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


class _Canon:
    """Follows re-exports to the defining key: ``api:monitoring_router`` is ``api.monitoring:router``."""

    def __init__(self, backend_dir: Path, defined: set[str]) -> None:
        self.backend_dir, self.defined = backend_dir, defined
        self._locals: dict[str, dict[str, str]] = {}

    def _local(self, module: str, file: Path) -> dict[str, str]:
        """*module*'s name bindings as ``mount_graph`` resolves them, parsed once per module."""
        if module not in self._locals:
            scan = ModuleScan(module, parse(file.read_text(encoding="utf-8")), self.backend_dir)
            scan.run()
            self._locals[module] = scan.local
        return self._locals[module]

    def __call__(self, key: str, seen: frozenset[str] = frozenset()) -> str:
        file = _key_file(self.backend_dir, key)
        if key == APP_ROOT or key in self.defined or key in seen or file is None:
            return key
        module, name = key.rsplit(":", 1)
        bound = self._local(module, file).get(name)
        return key if bound is None or bound == key else self(bound, seen | {key})


class _Walk:
    """The walk from the app root: ``found`` is ``{file: every mount of its judged router}``."""

    def __init__(self, backend_dir: Path, routing: ModuleType, children: dict[str, list[tuple[str, str]]]) -> None:
        self.backend_dir, self.routing, self.children = backend_dir, routing, children
        self.found: dict[Path, list[str]] = {}

    def descend(self, parent: str, served: str, chain: frozenset[str] = frozenset()) -> None:
        """Record every router *parent* includes (and theirs), composing the prefixes per level."""
        for child, inc_prefix in self.children.get(parent, ()):
            mount, file = f"{served}{inc_prefix}", _key_file(self.backend_dir, child)
            if file is None or child in chain:
                continue  # unresolvable, or an include cycle
            if child.rsplit(":", 1)[1] in _JUDGED:
                known = self.found.setdefault(file, [])
                known.extend([mount] if mount not in known else [])
            own = self.routing.file_router_prefix(file.read_text(encoding="utf-8", errors="ignore"))
            self.descend(child, f"{mount}{own}", chain | {child})


def app_mounts(backend_dir: Path, routing: ModuleType) -> dict[Path, list[str]]:
    """``{file: every mount prefix of its router}`` reached from the app root; own prefix excluded."""
    graph = build_graph(backend_dir, skip_tests=True)
    canon = _Canon(backend_dir, set(graph.routers))
    children: dict[str, list[tuple[str, str]]] = {}
    for edge in graph.edges:
        children.setdefault(canon(edge.parent), []).append((canon(edge.child), edge.prefix or ""))
    walk = _Walk(backend_dir, routing, children)
    walk.descend(APP_ROOT, "")
    return walk.found
