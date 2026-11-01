# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Public routes nothing calls (#20512): the "dead surface" half of the api-wiring audit.

``scripts/audit_api_wiring.py`` already fails the build on the other direction (a frontend call
no backend route serves). This asks the converse of every route decorator in the two backends:
does any frontend, any other production client, or any declared external caller reach it? It
reuses that script's own pieces -- ``ROUTE_DECORATOR_RE``, ``apirouter_prefix``, the registry
mount-prefix resolver, ``frontend_calls``, ``norm_path`` and ``_segments_match`` -- loaded from
the script, so the path grammar has one home.

WHAT A CALLER IS
----------------
* a literal ``/api/...`` path, or ``${getApiBase()}/...``, in ``autobot-frontend/src`` or
  ``autobot-slm-frontend/src`` (what ``frontend_calls`` extracts; tests, mocks and comments out);
* a relative path through a base-URL client (``slmApiClient.get('/api-keys')``), resolved with that
  client's base by ``_unconnected_clients`` (which lists every client form it knows);
* a literal ``/api/...`` path in any other production file (a Python client, a script, a shell
  health check, an Ansible template), outside the route's own file and off decorator lines;
* a route under a *declared external* prefix: agent-facing or machine-facing paths the script's
  ``dead_surface`` classifier already names (webhooks, health, metrics, agent APIs), plus
  ``EXTERNAL_CALLER_PREFIXES`` below, each with who calls it.

WHAT THIS CANNOT SEE
--------------------
* **Static prefix resolution.** The route's mount path is the registry prefix and the router's
  own prefix, combined every way the script combines them. The union is deliberately loose, so a
  route whose real path differs from every candidate can read as called by an unrelated caller
  (it errs toward "connected", never toward a false failure).
* **A caller that builds its path at runtime** (``f"/api/{resource}/{id}"`` from a table) shows
  as a wildcard or not at all. A wildcard segment matches any single segment.
* **A "bare base" call** (``'/api/x'`` plus a concatenated suffix) does NOT count the routes
  beneath it as called. ``audit_api_wiring.matches`` does, as its own comment concedes, and that
  rule hid ``POST /chats/{chat_id}/resume`` (#20401) behind the unrelated ``/api/chats`` list
  call. A route reached only through a concatenated path is therefore reported; add the full
  path to the caller or baseline the route.
* **A client it does not recognise** (a field, a parameter, a factory other than those listed in
  ``_unconnected_clients``) or a path held in a variable: reported unconnected until the call names it.
* **A call that is dead**: a frontend function that makes the call but nothing invokes.
* **Method.** A caller of ``GET /x`` marks ``POST /x`` connected; paths are matched, not verbs.
* Routes registered programmatically (``add_api_route``) have no decorator and are not seen.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from repo_tests._unconnected_clients import client_calls
from repo_tests._unconnected_common import Tree

ROUTE_ROOTS = ("autobot-backend", "autobot-slm-backend")
FRONTENDS = ("autobot-frontend/src", "autobot-slm-frontend/src")
_CALLER_SUFFIXES = (".py", ".sh", ".yml", ".yaml", ".j2", ".ts", ".js", ".vue", ".service", ".conf")

#: Prefixes whose callers live outside this repository or outside a browser, beyond the
#: agent- and machine-facing ones ``scripts/dead_surface.py`` already declares. Value: who calls.
EXTERNAL_CALLER_PREFIXES: dict[str, str] = {}


def load_script(root: Path, name: str) -> ModuleType:
    """``scripts/<name>.py`` as a module, leaving ``sys.path`` and ``sys.modules`` as they were.

    The audit script prepends its own directory to ``sys.path`` and imports ``dead_surface``;
    leaving either installed trips the session-finish leak guard (#13361).
    """
    path_before, modules_before = list(sys.path), set(sys.modules)
    spec = importlib.util.spec_from_file_location(name, root / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = path_before
        for leaked in set(sys.modules) - modules_before:
            sys.modules.pop(leaked, None)
    return module


class Audit:
    """The audit script's grammar, bound to one tree root."""

    def __init__(self, root: Path, scripts_root: Path | None = None) -> None:
        """*root* is the tree being judged; *scripts_root* (default *root*) is where the scripts live."""
        self.root = root
        self.mod = load_script(scripts_root or root, "audit_api_wiring")
        self.dead = load_script(scripts_root or root, "dead_surface")
        self.external = tuple(self.dead._AGENT_FACING_PREFIXES + self.dead._MACHINE_FACING_PREFIXES) + tuple(
            EXTERNAL_CALLER_PREFIXES
        )

    def frontend_calls(self, src: str) -> dict[str, set[str]]:
        """The script's own ``frontend_calls``, pointed at *src* under this root."""
        saved = self.mod.FRONTEND_SRC, self.mod.REPO_ROOT
        self.mod.FRONTEND_SRC, self.mod.REPO_ROOT = self.root / src, self.root
        try:
            return self.mod.frontend_calls()
        finally:
            self.mod.FRONTEND_SRC, self.mod.REPO_ROOT = saved

    def registry_prefixes(self, backend: str) -> dict[str, str]:
        """``{repo-relative served file: mount prefix}``; empty when the backend has no registry."""
        base = self.root / backend
        if not (base / "initialization" / "router_registry").is_dir():
            return {}
        by_abs = self.mod._registry_module_prefixes(base)
        return {Path(p).relative_to(self.root).as_posix(): prefix for p, prefix in by_abs.items()}


def route_sites(tree: Tree, audit: Audit) -> list[tuple[str, str, str, tuple[str, ...]]]:
    """``(file, METHOD, raw path, candidate full paths)`` for every route decorator in the backends."""
    mod, out = audit.mod, []
    for backend in ROUTE_ROOTS:
        registry = audit.registry_prefixes(backend)
        for rel in tree.select(".py", under=(backend,)):
            text = tree.text(rel)
            if "@" not in text:
                continue
            found = mod.ROUTE_DECORATOR_RE.findall(text)
            if not found:
                continue
            own = mod.apirouter_prefix(text)
            own = own.rstrip("/") if own is not None else ""
            reg = registry.get(rel)
            for method, raw in found:
                out.append((rel, method.upper(), raw, _candidates(mod, raw, own, reg)))
    return out


def _candidates(mod: ModuleType, raw: str, own: str, reg: str | None) -> tuple[str, ...]:
    glue = "" if (raw.startswith("/") or not raw) else "/"
    forms = {raw, own + glue + raw}
    if reg is not None:
        forms.update({reg + glue + raw, reg + own + glue + raw})
    return tuple(sorted({mod.norm_path(f) if f else mod.norm_path(own or reg or "/") for f in forms}))


def other_callers(tree: Tree, audit: Audit) -> dict[str, set[str]]:
    """Normalised ``/api/`` paths named by production files outside the two frontends' ``src``.

    Route decorators are blanked first, so a backend file declaring ``@router.get("/api/x")`` is
    not its own caller. Comments are not stripped: a comment naming a path counts as a caller.
    """
    mod, calls = audit.mod, {}
    skip = (*(f"{f}/" for f in FRONTENDS), "docs/")
    for rel in tree.select(*_CALLER_SUFFIXES):
        text = tree.text(rel)
        if rel.startswith(skip) or "/api/" not in text:
            continue
        for hit in mod.FE_API_RE.findall(mod.ROUTE_DECORATOR_RE.sub("", text) if "@" in text else text):
            path = mod.norm_path(hit)
            if path.count("{") == path.count("}"):
                calls.setdefault(path, set()).add(rel)
    return calls


class _CallerIndex:
    """Caller paths bucketed by segment count and second segment, so a route meets a handful of them."""

    def __init__(self, callers: dict[str, set[str]]) -> None:
        self.callers = callers
        self.by_key: dict[tuple[int, str], list[str]] = {}
        self.by_len: dict[int, list[str]] = {}
        for call in callers:
            parts = call.strip("/").split("/")
            self.by_len.setdefault(len(parts), []).append(call)
            self.by_key.setdefault((len(parts), parts[1] if len(parts) > 1 else ""), []).append(call)

    def near(self, parts: list[str]) -> list[str]:
        """Callers that could match *parts*: same length, and the same or a wildcard second segment."""
        second = parts[1] if len(parts) > 1 else ""
        if second == "{p}":
            return self.by_len.get(len(parts), [])
        return self.by_key.get((len(parts), second), []) + self.by_key.get((len(parts), "{p}"), [])


def _toggle_api(cand: str) -> str:
    """*cand* with the ``/api`` mount prefix added, or removed when it is a whole leading segment.

    ``/api-keys`` does not start with the ``/api`` prefix; a plain ``startswith`` treated it as if it
    did and compared the route as ``-keys`` (#20512).
    """
    if cand == "/api" or cand.startswith("/api/"):
        return cand[len("/api") :] or "/"
    return "/api" + cand


def _reached(mod: ModuleType, rel: str, cands: tuple[str, ...], index: _CallerIndex) -> bool:
    """Whether a caller outside *rel* matches a candidate path (the script's segment rule, no bare-base leniency)."""
    for cand in cands:
        for v in {cand, _toggle_api(cand)}:
            if any(index.callers[c] - {rel} for c in index.near(v.strip("/").split("/")) if mod._segments_match(c, v)):
                return True
    return False


def unconnected(tree: Tree, audit: Audit, sites: list | None = None) -> list[str]:
    """Route keys ``"<file>:<METHOD> <raw path>"`` that no caller and no declared prefix reaches."""
    callers: dict[str, set[str]] = {}
    for src in FRONTENDS:
        for path, files in audit.frontend_calls(src).items():
            callers.setdefault(path, set()).update(files)
    for path, files in other_callers(tree, audit).items():
        callers.setdefault(path, set()).update(files)
    for path, files in client_calls(tree, FRONTENDS, audit.mod.norm_path, audit.mod.FE_EXCLUDE_PATTERNS).items():
        callers.setdefault(path, set()).update(files)
    index = _CallerIndex(callers)
    out: set[str] = set()
    for rel, method, raw, cands in route_sites(tree, audit) if sites is None else sites:
        if any(c.startswith(audit.external) or ("/api" + c).startswith(audit.external) for c in cands):
            continue
        if not _reached(audit.mod, rel, cands, index):
            out.add(f"{rel}:{method} {raw}")
    return sorted(out)


def route_files(tree: Tree, audit: Audit) -> list[str]:
    """The files this detector judges: those in the two backends declaring at least one route."""
    return sorted({site[0] for site in route_sites(tree, audit)})
