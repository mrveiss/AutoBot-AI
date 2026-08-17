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
    "INCLUDE_ROUTER_NAME_RE",
    "apirouter_prefix",
    "include_router_prefixes",
    "RELATIVE_ROUTER_IMPORT_RE",
    "ROUTER_CONFIG_ENTRY_RE",
    "ROUTER_IMPORT_ALIAS_RE",
    "file_router_prefix",
    "package_router_files",
    "registry_entries",
    "resolve_registry_targets",
]


# ── The grammar ──────────────────────────────────────────────────────────────

#: The first positional argument of an ``include_router`` call — the router name.
#:
#: Both lookaheads are load-bearing. ``(?!\s*=)`` alone rejects a keyword-only
#: call, but the name is greedy and backtracks: given a keyword named ``prefix``
#: it matches ``prefi`` so the next character is ``x`` rather than ``=``, and the
#: keyword is captured as a router under a truncated name. ``(?![\w.])`` forces
#: the token to be maximal first, so the ``=`` test is applied to the whole name.
_INCLUDE_ROUTER_TARGET_RE = re.compile(r"include_router\(\s*([A-Za-z_][\w.]*)(?![\w.])(?!\s*=)")

#: ``prefix="/y"`` anywhere in a call's own argument list.
_PREFIX_KWARG_RE = re.compile(r"prefix\s*=\s*['\"]([^'\"]+)")

#: ``include_router(name)`` — which routers a package actually mounts (#12956).
#: Distinct from ``include_router_prefixes``: here the *name* matters and the
#: prefix may be absent, because it lives on the imported router itself.
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


# ── Call scanning ────────────────────────────────────────────────────────────
#
# These calls are read with a paren-balanced scan rather than a regex (#14356).
# The previous grammar reached its own `prefix=` through `[^)]*?`, which cannot
# cross a `)`. So an argument containing parentheses — the common
# `dependencies=[Depends(get_current_user)]` — hid every later keyword, and the
# mount's prefix was dropped with NO error. A consumer defaulting to `""` then
# reports that module's routes one segment short: an endpoint at a path nothing
# answers on. Silent omission, never a wrong pairing, which is what made it
# survivable for so long.
#
# Bounding the nesting instead (allowing one level of `(...)`) was rejected: it
# fails identically at two levels and fails the same silent way, so it would
# leave the defect in place at a depth nobody would think to check.


def _call_end(text: str, open_paren: int) -> int:
    """Index just past the ``)`` closing the call whose ``(`` is at *open_paren*.

    Quoted strings are skipped. A parenthesis inside a string literal would
    otherwise unbalance the count and reintroduce a silent miscount of exactly
    the kind this replaces. Returns ``-1`` for an unterminated call.
    """
    depth = 0
    index = open_paren
    quote = ""
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return -1


def _own_arguments(call: str) -> str:
    """*call* with the contents of nested calls blanked out.

    Keeps the text length stable so offsets still line up, and stops a nested
    call's ``prefix=`` being read as this call's own.
    """
    chars = list(call)
    depth = 0
    quote = ""
    for index, char in enumerate(chars):
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth > 1:
            chars[index] = " "
    return "".join(chars)


def _calls(text: str, function: str) -> Iterable[str]:
    """Each complete ``function(...)`` call in *text*, parentheses balanced."""
    for match in re.finditer(rf"\b{function}\(", text):
        end = _call_end(text, match.end() - 1)
        if end > 0:
            yield text[match.start() : end]


def include_router_prefixes(text: str) -> list[Tuple[str, str]]:
    """``(router_name, prefix)`` for each ``include_router`` naming a literal prefix.

    Replaces the former ``INCLUDE_ROUTER_RE.findall`` and returns the same shape,
    so call sites read identically.
    """
    found = []
    for call in _calls(text, "include_router"):
        target = _INCLUDE_ROUTER_TARGET_RE.match(call)
        prefix = _PREFIX_KWARG_RE.search(_own_arguments(call))
        if target and prefix:
            found.append((target.group(1), prefix.group(1)))
    return found


# ── Resolution ───────────────────────────────────────────────────────────────


def apirouter_prefix(source: str) -> str | None:
    """The raw ``APIRouter(prefix=...)`` a file declares, or ``None``.

    Scanned the same way as ``include_router`` and for the same reason: the old
    ``APIRouter\\([^)]*?prefix=`` carried the identical defect, so a constructor
    passing ``dependencies`` before ``prefix`` silently reported no prefix at
    all (#14356).

    The example is described rather than written out. A literal constructor call
    in this docstring is found by this module's own scanner when the file is
    read as source — the doc becoming a false positive in the tool it documents.

    Returns the prefix verbatim. ``None`` and ``""`` are distinct answers here —
    "no prefix declared" versus "a declared empty prefix" — so callers that
    normalise choose to, rather than being unable to tell the two apart.
    """
    for call in _calls(source, "APIRouter"):
        prefix = _PREFIX_KWARG_RE.search(_own_arguments(call))
        if prefix:
            return prefix.group(1)
    return None


def file_router_prefix(source: str) -> str:
    """The ``APIRouter(prefix=...)`` a file declares, trailing slash removed, or ``""``.

    #14355 settled the normalisation both consumers now share. The analytics
    scanner used to read this prefix verbatim while the audit gate stripped the
    trailing slash, so the two disagreed for any prefix written ``"/x/"``.
    Stripping is the correct half: prefixes are concatenated, so the verbatim
    form yields ``/x//y`` — a path nothing serves, reported as if it did.
    FastAPI refuses such a prefix outright ("A path prefix must not end with
    '/', as the routes will start with '/'"), so a trailing slash in source can
    only ever be a mistake, never a served path either tool should reproduce.
    """
    prefix = apirouter_prefix(source)
    return prefix.rstrip("/") if prefix is not None else ""


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
            targets.update(package_router_files(target, prefix))
    return targets


def package_router_files(package: Path, registry_prefix: str) -> Dict[Path, str]:
    """Submodules a registry-mounted package actually serves, and their prefix.

    The single implementation, called by both source-reading consumers: the
    blocking ``api-wiring`` gate through ``resolve_registry_targets`` above, and
    the analytics endpoint inventory through
    ``api_endpoint_scanner._registry_router_files``. It was public-by-copy until
    #14355 — the scanner owned a second, separately maintained version, so the
    gate that decides whether a PR may merge and the report a human reads to
    judge that gate could describe different APIs with nothing saying which was
    right. Consumers call this; nobody reimplements it.

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
    mounted = set(INCLUDE_ROUTER_NAME_RE.findall(init_content))
    if not mounted:
        return {}

    served_prefix = f"{registry_prefix}{file_router_prefix(init_content)}"
    # #13582: a prefix given on the mount call applies to every route in the
    # mounted module and is invisible to APIRouter(prefix=) parsing.
    mount_prefixes = dict(include_router_prefixes(init_content))

    files: Dict[Path, str] = {}
    for module_name, alias in RELATIVE_ROUTER_IMPORT_RE.findall(init_content):
        if alias not in mounted:
            continue  # declared but never mounted: it serves nothing
        mounted_prefix = f"{served_prefix}{mount_prefixes.get(alias, '')}"
        module_file = (package / module_name).with_suffix(".py")
        if module_file.is_file():
            files[module_file] = mounted_prefix
            continue
        subpackage = package / module_name
        if (subpackage / "__init__.py").is_file():
            files.update(package_router_files(subpackage, mounted_prefix))
    return files
