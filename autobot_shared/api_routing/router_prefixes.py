# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical parsing of FastAPI router mount prefixes from source (#12985).

Two tools derive served API paths by reading source rather than a running app:

* ``scripts/audit_api_wiring.py`` — the **blocking** ``api-wiring`` CI gate
* ``autobot-backend/api/codebase_analytics/api_endpoint_scanner.py`` — the
  analytics endpoint inventory

They had **separate regexes for the same grammar**, and had already diverged.
``api_endpoint_scanner.py`` received two rounds of package-resolution fixes
(#12945, #12956); ``audit_api_wiring.py`` received neither, so a registry entry
naming a *package* — ``("llc.api", "", …)`` — resolved to a non-existent
``llc/api.py`` and contributed no prefix at all.

That matters more for the audit than for the scanner: a required gate that
under-resolves prefixes either emits false reds that get worked around, eroding
trust in it, or masks real frontend/backend contract drift.

This module is the single grammar. The scanner's post-#12956 behaviour is the
correct baseline and is what is reproduced here.

## The shape being parsed

A route's served path is the concatenation of up to three prefixes:

    /api  +  <registry entry prefix>  +  <package __init__ router prefix>
          +  <submodule router prefix>  +  <@router.get("...") path>

The middle two only exist for registry-mounted packages, which is exactly the
case the audit was missing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, Tuple

__all__ = [
    "APIROUTER_PREFIX_RE",
    "INCLUDE_ROUTER_RE",
    "INCLUDE_ROUTER_NAME_RE",
    "RELATIVE_ROUTER_IMPORT_RE",
    "ROUTER_CONFIG_ENTRY_RE",
    "ROUTER_IMPORT_ALIAS_RE",
    "file_router_prefix",
    "registry_entries",
    "resolve_registry_targets",
]


# ── The grammar ──────────────────────────────────────────────────────────────

#: ``router = APIRouter(prefix="/x")`` — a module's own prefix.
APIROUTER_PREFIX_RE = re.compile(r"APIRouter\([^)]*?prefix\s*=\s*['\"]([^'\"]+)", re.S)

#: ``app.include_router(x, prefix="/y")`` — a literal mount prefix.
INCLUDE_ROUTER_RE = re.compile(r"include_router\(\s*([A-Za-z_][\w.]*)[^)]*?prefix\s*=\s*['\"]([^'\"]+)", re.S)

#: ``include_router(name)`` — which routers a package actually mounts (#12956).
#: Distinct from INCLUDE_ROUTER_RE: here the *name* matters and the prefix may
#: be absent, because the prefix lives on the imported router itself.
INCLUDE_ROUTER_NAME_RE = re.compile(r"include_router\(\s*(\w+)")

#: ``from .costs import router as costs_router`` — binds an alias to a submodule.
RELATIVE_ROUTER_IMPORT_RE = re.compile(r"^from\s+\.(\w+)\s+import\s+router\s+as\s+(\w+)", re.MULTILINE)

#: Data-driven registry tuples in ``initialization/router_registry/*.py`` (#12432):
#:     ("api.advanced_control", "/advanced-control", [...], "advanced_control")
#:     (overseer_router,        "/overseer",         [...], "overseer")
#: ``app_factory`` mounts these generically with ``prefix=f"/api{prefix}"``, so
#: no literal ``include_router(prefix=...)`` call exists for them to be found by.
ROUTER_CONFIG_ENTRY_RE = re.compile(
    r"\(\s*(?:['\"](?P<mod>\w+(?:\.\w+)+)['\"]|(?P<var>[A-Za-z_]\w*))"
    r"\s*,\s*(?:['\"]router['\"]\s*,\s*)?['\"](?P<prefix>[^'\"]*)['\"]\s*,\s*\["
)

#: ``from api.overseer_handlers import router as overseer_router`` — resolves the
#: variable form of a registry entry back to its module.
ROUTER_IMPORT_ALIAS_RE = re.compile(r"from\s+([\w.]+)\s+import\s+router\s+as\s+(\w+)")


# ── Resolution ───────────────────────────────────────────────────────────────


def file_router_prefix(source: str) -> str:
    """The ``APIRouter(prefix=...)`` a file declares, or ``""``."""
    match = APIROUTER_PREFIX_RE.search(source)
    return match.group(1).rstrip("/") if match else ""


def registry_entries(registry_dir: Path) -> list[Tuple[str, str]]:
    """``(dotted_module, prefix)`` for every entry in ``router_registry/*.py``.

    Variable-form entries are resolved through their ``import router as`` alias.
    Returns ``[]`` when the directory does not exist — backends without a
    registry (autobot-slm-backend) are a normal case, not an error.
    """
    if not registry_dir.is_dir():
        return []

    alias_to_module: Dict[str, str] = {}
    raw: list[Tuple[str, str]] = []
    for py in sorted(registry_dir.glob("*.py")):
        text = py.read_text(encoding="utf-8", errors="ignore")
        alias_to_module.update({alias: mod for mod, alias in ROUTER_IMPORT_ALIAS_RE.findall(text)})
        raw.extend((m.group("mod") or m.group("var"), m.group("prefix")) for m in ROUTER_CONFIG_ENTRY_RE.finditer(text))

    resolved: list[Tuple[str, str]] = []
    for mod_or_var, prefix in raw:
        module = mod_or_var if "." in mod_or_var else alias_to_module.get(mod_or_var)
        if module:
            resolved.append((module, prefix.rstrip("/")))
    return resolved


def resolve_registry_targets(backend_dir: Path, entries: Iterable[Tuple[str, str]]) -> Dict[Path, str]:
    """Map each registry entry to the files it serves, and their mount prefix.

    A **module** entry maps to one file. A **package** entry (#12945) maps to its
    mounted submodules, each carrying ``registry prefix + the package's own
    router prefix`` — the package ``__init__.py``'s ``APIRouter(prefix=...)``
    sits between the two, and applying the registry prefix alone yields paths
    that do not exist.

    The returned prefix deliberately excludes each submodule's *own* prefix:
    callers apply that from the file they are scanning.
    """
    targets: Dict[Path, str] = {}
    for module_path, prefix in entries:
        target = backend_dir.joinpath(*module_path.split("."))
        module_file = target.with_suffix(".py")
        if module_file.is_file():
            targets[module_file] = prefix
        elif (target / "__init__.py").is_file():
            targets.update(_package_router_files(target, prefix))
    return targets


def _package_router_files(package: Path, registry_prefix: str) -> Dict[Path, str]:
    """Submodules a registry-mounted package actually serves, and their prefix.

    A submodule counts only when the package imports its router under an alias
    **and** mounts that exact alias (#12956). Checking merely that the package
    mounts *something* let a declared-but-unmounted router contribute routes.

    Nested router subpackages recurse rather than being globbed, so their
    modules resolve under their own prefix instead of the parent's — globbing
    skipped the ``__init__.py`` carrying that prefix and invented endpoints,
    which is worse than missing them: they resurface as phantom findings.
    """
    init_file = package / "__init__.py"
    init_content = init_file.read_text(encoding="utf-8", errors="ignore")
    if not INCLUDE_ROUTER_NAME_RE.search(init_content):
        return {}

    mounted = set(INCLUDE_ROUTER_NAME_RE.findall(init_content))
    if not mounted:
        return {}

    served_prefix = f"{registry_prefix}{file_router_prefix(init_content)}"

    files: Dict[Path, str] = {}
    for module_name, alias in RELATIVE_ROUTER_IMPORT_RE.findall(init_content):
        if alias not in mounted:
            continue  # declared but never mounted: it serves nothing
        module_file = (package / module_name).with_suffix(".py")
        if module_file.is_file():
            files[module_file] = served_prefix
            continue
        subpackage = package / module_name
        if (subpackage / "__init__.py").is_file():
            files.update(_package_router_files(subpackage, served_prefix))
    return files
