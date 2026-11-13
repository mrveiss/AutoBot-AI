# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Mount prefixes of routes served through a package-level router (#21428).

The router registry mounts ``("api.codebase_analytics", "/analytics/codebase", ...)``: a **package**. The
router it serves is not in ``__init__.py`` -- ``__init__`` re-exports it (``from .routes import router``),
``routes.py`` re-exports it again (``from .router import router``), and ``router.py`` builds it and mounts
every endpoint module under ``endpoints/`` with ``router.include_router(charts.router)``. The shared
resolver (``router_prefixes.package_router_files``) reads only ``__init__.py`` and only
``from .x import router as alias``, so it found no mounted submodule and the gate judged those routes as if
they had no mount prefix at all: ``/analytics/charts`` instead of ``/analytics/codebase/analytics/charts``.

This follows the chain by reading source, composing the prefix at every level::

    registry prefix + router's own ``APIRouter(prefix=)`` + ``include_router(prefix=)`` + child's own prefix

The child's own prefix is NOT in the returned value (callers add it from the child's file), the same
contract as ``router_prefixes.module_included_router_files``.

WHY THIS LIVES IN THE GATE AND NOT IN ``router_prefixes``
---------------------------------------------------------
The shared resolver is read by the blocking ``api-wiring`` audit, the analytics endpoint inventory
(``api_endpoint_scanner``) and four repo_tests oracles that pin its exact output (for example
``router_prefix_convergence_test`` asserts every ``llc.api`` file resolves to exactly ``{"/llc"}``, a value
that includes the package router's own prefix, which this module deliberately leaves to the caller). Changing
it re-measures all of them, and none can be re-measured from this gate's change. This reads the shared
grammar (``file_router_prefix``, ``include_router_prefixes``, ``INCLUDE_ROUTER_NAME_RE``) and adds only the
walk the shared resolver lacks. Moving the walk into the shared resolver must re-measure those consumers
first (#21428).

WHAT THIS CANNOT SEE
--------------------
* A router that is not bound by a ``from <module> import <name>`` (``import pkg.mod as m``, a router built
  in a function, one looked up by ``getattr`` or ``importlib``).
* An include whose prefix is a variable or an f-string: ``include_router_prefixes`` reads only literals.
* A router included at the same name twice with and without a prefix: the prefixed form wins.
* A module that declares several routers, with different prefixes: the first ``APIRouter(prefix=)`` is used.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType

_FROM_IMPORT_RE = re.compile(r"^from\s+(\.*)([\w.]*)\s+import\s+(\([^)]*\)|[^\n]+)", re.MULTILINE)
_COMMENT_RE = re.compile(r"#[^\n]*")
_ROUTER_DEF_RE = re.compile(r"^router\s*(?::[^=\n]+)?=\s*APIRouter\(", re.MULTILINE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _imported_names(clause: str) -> list[tuple[str, str]]:
    """``(imported name, bound name)`` for each name of an import clause (parentheses already comment-free)."""
    pairs = []
    for part in clause.strip("() \t\n").replace("\n", " ").split(","):
        words = part.split()
        if words and words[0] != "*":
            pairs.append((words[0], words[2] if len(words) == 3 and words[1] == "as" else words[0]))
    return pairs


def _anchor(backend_dir: Path, file: Path, dots: str, module: str) -> Path:
    """The path an import's module part names: relative to *file*'s package, or from the backend root."""
    parts = module.split(".") if module else []
    if not dots:
        return backend_dir.joinpath(*parts)
    return file.parent.joinpath(*([".."] * (len(dots) - 1)), *parts)


def _source_file(anchor: Path, name: str) -> Path | None:
    """The file *name* is served from when imported out of *anchor*: a submodule, else the module itself."""
    for candidate in (
        anchor / f"{name}.py",
        anchor / name / "__init__.py",
        anchor.with_suffix(".py"),
        anchor / "__init__.py",
    ):
        if candidate.is_file():
            return Path(os.path.normpath(candidate))
    return None


def _bindings(backend_dir: Path, file: Path, source: str) -> dict[str, Path]:
    """``{bound name: file}`` for every ``from <module> import <name>`` that names a file of this tree."""
    bound: dict[str, Path] = {}
    for dots, module, clause in _FROM_IMPORT_RE.findall(_COMMENT_RE.sub("", source)):
        anchor = _anchor(backend_dir, file, dots, module)
        for name, alias in _imported_names(clause):
            found = _source_file(anchor, name)
            if found is not None:
                bound[alias] = found
    return bound


def _router_home(backend_dir: Path, file: Path, seen: frozenset[Path] = frozenset()) -> Path | None:
    """The file that builds the ``router`` *file* exports, following ``from .x import router`` re-exports."""
    source = _read(file)
    if _ROUTER_DEF_RE.search(source):
        return file
    target = _bindings(backend_dir, file, source).get("router")
    if target is None or target in seen or target == file:
        return None
    return _router_home(backend_dir, target, seen | {file})


def _add(found: dict[Path, list[str]], file: Path, prefix: str) -> None:
    known = found.setdefault(file, [])
    if prefix not in known:
        known.append(prefix)


def _walk(
    backend_dir: Path, routing: ModuleType, file: Path, mount: str, found: dict[Path, list[str]], seen: frozenset[Path]
) -> None:
    """Record every module *file* includes (and theirs) with its mount prefix, composing prefixes per level."""
    source = _read(file)
    served = f"{mount}{routing.file_router_prefix(source)}"
    bound = _bindings(backend_dir, file, source)
    prefixes: dict[str, list[str]] = {}
    for target, prefix in routing.include_router_prefixes(source):
        prefixes.setdefault(target.split(".")[0], []).append(prefix)
    for name in dict.fromkeys(routing.INCLUDE_ROUTER_NAME_RE.findall(source)):
        child = bound.get(name)
        if child is None or child in seen:
            continue
        child = _router_home(backend_dir, child) or child
        for inc_prefix in prefixes.get(name, [""]):
            _add(found, child, f"{served}{inc_prefix}")
            _walk(backend_dir, routing, child, f"{served}{inc_prefix}", found, seen | {child})


def package_mounts(backend_dir: Path, routing: ModuleType, entries: Iterable[tuple[str, str]]) -> dict[Path, list[str]]:
    """``{file: every mount prefix}`` for the registry entries that name a *package*, through its router chain.

    *routing* is ``autobot_shared.api_routing.router_prefixes`` as the audit script loaded it. Module entries
    are not touched here: ``routing.resolve_registry_target_prefixes`` owns them.
    """
    found: dict[Path, list[str]] = {}
    for module_path, prefix in entries:
        target = backend_dir.joinpath(*module_path.split("."))
        if target.with_suffix(".py").is_file() or not (target / "__init__.py").is_file():
            continue
        home = _router_home(backend_dir, target / "__init__.py")
        if home is not None:
            _add(found, home, prefix)
            _walk(backend_dir, routing, home, prefix, found, frozenset({home}))
    return found
