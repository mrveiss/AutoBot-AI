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
* **Static prefix resolution.** A route is judged at ``mount + own prefix + path`` and nowhere else:
  one candidate per mount, and the router's own ``APIRouter(prefix=...)`` is never dropped, since
  FastAPI always applies it (#20910). The mounts are the registry's, including nested
  ``include_router`` mounts and a package entry's router chain (``__init__`` -> ``router.py`` ->
  ``endpoints/*.py``, followed by ``_unconnected_mounts``, #21428). A backend with no registry (the SLM)
  is read from its app's ``include_router`` graph by ``_unconnected_app_mounts``: ``main.py``'s
  ``prefix=`` and every nested include (``/api/monitoring`` + ``/gpu``), with what that cannot see listed
  there. A router no mount reaches (unmounted, or a mount neither reader resolves) is judged at its own
  prefix + path with ``/api`` toggled; a nested mount of such a router is missed. A form without the own
  prefix used to be a candidate too, and let an unrelated caller of the same shape mark the route connected.
* **Which router a decorator is on.** Only ``@router``/``@app``/``@api_router`` decorators are seen,
  and the own prefix is the first ``APIRouter(prefix=...)`` in the file.
* **A caller that builds its path at runtime** (``f"/api/{resource}/{id}"`` from a table) shows
  as a wildcard or not at all. A wildcard segment matches any single segment.
* **A route whose mounted path starts with a parameter** (a router mounted at the root, ``/{id}/x``): no
  caller can be told from an unrelated one, so it is reported unconnected until the call names it.
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
* A decorator is read from code only: one in a ``#`` comment is not a route (#20910), but one quoted in a
  docstring or string literal still reads as one.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from repo_tests._unconnected_app_mounts import app_mounts
from repo_tests._unconnected_clients import client_calls
from repo_tests._unconnected_common import Tree
from repo_tests._unconnected_helper_calls import helper_calls, reached_by_helper
from repo_tests._unconnected_mounts import package_mounts

from tools.lint._comment_syntax import code_lines

ROUTE_ROOTS = ("autobot-backend", "autobot-slm-backend")
FRONTENDS = ("autobot-frontend/src", "autobot-slm-frontend/src")
_CALLER_SUFFIXES = (".py", ".sh", ".yml", ".yaml", ".j2", ".ts", ".js", ".vue", ".service", ".conf")

#: Prefixes whose callers live outside this repository or outside a browser, beyond the
#: agent- and machine-facing ones ``scripts/dead_surface.py`` already declares. Value: who calls.
EXTERNAL_CALLER_PREFIXES: dict[str, str] = {
    # #21048: the knowledge-wipe preview and proposal are called by an administrator over HTTP; there is no
    # UI for it yet. The operator script raises the same proposal directly through the same service.
    "/api/admin/knowledge-wipe": "an administrator, over HTTP (no UI yet)",
    # #20910: SCIM 2.0 inbound provisioning (RFC 7644) is pushed by the identity provider's SCIM client;
    # the SLM mounts it outside /api so the provider reaches it directly. Nothing in this repository calls it.
    "/scim/v2": "an identity provider's SCIM client, over HTTP",
    # #20910: the OAuth2 redirect URI (api/sso_auth.py GET /callback). The identity provider sends the user's browser
    # here after sign-in; nothing in this repository requests it.
    "/api/auth/sso/callback": "the identity provider's browser redirect after sign-in",
}


#: The mount of a router neither the registry nor the app's include graph reaches: judged at its own
#: prefix + path, which ``_reached`` tries with and without ``/api``.
_UNREGISTERED_MOUNT = ""


def load_script(root: Path, name: str) -> ModuleType:
    """``scripts/<name>.py`` as a module, leaving ``sys.path`` and ``sys.modules`` as they were.

    The audit script prepends its own directory to ``sys.path`` and imports ``dead_surface``;
    leaving either installed trips the session-finish leak guard (#13361).
    """
    path_before, modules_before = list(sys.path), dict(sys.modules)
    spec = importlib.util.spec_from_file_location(name, root / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = path_before
        for leaked in set(sys.modules) - set(modules_before):
            sys.modules.pop(leaked, None)
        if name in modules_before:  # a module already installed under this name is put back, not left replaced
            sys.modules[name] = modules_before[name]
    return module


def _merge_prefixes(by_abs: dict[str, list[str]], file: Path, prefixes: list[str]) -> None:
    """Add *prefixes* to the mounts known for *file*, keeping the order and dropping repeats."""
    known = by_abs.setdefault(str(file), [])
    known.extend(p for p in prefixes if p not in known)


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

    def registry_prefixes(self, backend: str) -> dict[str, list[str]]:
        """``{repo-relative served file: every mount prefix}``.

        A router is served at its registry mount AND at every place another registry-mounted module
        ``include_router``s it (nested mounts, #17325), so one file can have several prefixes. A backend
        with no registry (the SLM) is read from its app's ``include_router`` graph instead (#20910).
        """
        base = self.root / backend
        registry_dir = base / "initialization" / "router_registry"
        routing = self.mod._routing
        if not registry_dir.is_dir():
            mounts = app_mounts(base, routing) if base.is_dir() else {}
            return {Path(p).relative_to(self.root).as_posix(): ps for p, ps in mounts.items()}
        entries = routing.registry_entries(registry_dir)
        by_abs = {str(p): list(ps) for p, ps in routing.resolve_registry_target_prefixes(base, entries).items()}
        for module_path, prefix in entries:  # the resolver lets a registry mount hide a nested one: add them back
            module_file = base.joinpath(*module_path.split(".")).with_suffix(".py")
            if not module_file.is_file():
                continue
            for child, prefixes in routing.module_included_router_files(base, module_file, prefix).items():
                _merge_prefixes(by_abs, child, prefixes)
        # a registry entry naming a package: its router is built by a module of the package, not its __init__ (#21428)
        for child, prefixes in package_mounts(base, routing, entries).items():
            _merge_prefixes(by_abs, child, prefixes)
        return {Path(p).relative_to(self.root).as_posix(): ps for p, ps in by_abs.items()}


def route_sites(tree: Tree, audit: Audit) -> list[tuple[str, str, str, tuple[str, ...]]]:
    """``(file, METHOD, raw path, candidate full paths)`` for every route decorator in the backends."""
    mod, out = audit.mod, []
    for backend in ROUTE_ROOTS:
        registry = audit.registry_prefixes(backend)
        for rel in tree.select(".py", under=(backend,)):
            text = tree.text(rel)
            if "@" not in text:
                continue
            found = mod.ROUTE_DECORATOR_RE.findall(_code_text(rel, text))
            if not found:
                continue
            own = mod.apirouter_prefix(text)
            own = own.rstrip("/") if own is not None else ""
            regs = registry.get(rel) or [_UNREGISTERED_MOUNT]
            for method, raw in found:
                out.append((rel, method.upper(), raw, _candidates(mod, raw, own, regs)))
    return out


def _code_text(rel: str, text: str) -> str:
    """*text* without its comments, so ``# Handle @router.get("/path") style`` is not read as a route (#20910)."""
    return "\n".join(line.text for line in code_lines(text, name=rel, strip_trailing=True))


def _candidates(mod: ModuleType, raw: str, own: str, regs: list[str]) -> tuple[str, ...]:
    """Every full path a route is served at: ``mount + own prefix + path``, one per mount (#20910).

    A router can be mounted more than once. The router's own prefix is in every form: FastAPI applies
    it wherever the router is mounted, so a form without it names a path nothing serves.
    """
    glue = "" if (raw.startswith("/") or not raw) else "/"
    return tuple(sorted({mod.norm_path(reg + own + glue + raw or "/") for reg in regs}))


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
        body = mod.ROUTE_DECORATOR_RE.sub("", text) if "@" in text else text
        # a quoted `/api/..` or one behind a URL base (`$BASE/api/..`, `f"{base}/api/.."`, `host:8001/api/..`)
        for hit in (*mod.FE_API_RE.findall(body), *mod.URL_BASE_API_RE.findall(body)):
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


def _leads_with_parameter(cand: str) -> bool:
    """Whether *cand*'s first segment (past a leading ``/api``) is a path parameter, as ``/{p}/x`` is.

    The unmounted form of a route declared ``/{provider}/x`` is ``/{p}/x``; its wildcard first segment
    matches ``/api/devices/x`` or any other two-segment call, so a route whose only caller is that
    coincidence read as connected (#20512). Only the mounted forms, which name the router's own prefix,
    can be reached; a router mounted at the root with a leading parameter reports unconnected.
    """
    segs = cand.strip("/").split("/")
    if segs[0] == "api":
        segs = segs[1:]
    return bool(segs) and segs[0] == "{p}"


def _reached(mod: ModuleType, rel: str, cands: tuple[str, ...], index: _CallerIndex) -> bool:
    """Whether a caller outside *rel* matches a candidate path (the script's segment rule, no bare-base leniency)."""
    for cand in cands:
        if _leads_with_parameter(cand):
            continue
        for v in {cand, _toggle_api(cand)}:
            if any(index.callers[c] - {rel} for c in index.near(v.strip("/").split("/")) if mod._segments_match(c, v)):
                return True
    return False


def _reached_by_helper(rel: str, method: str, cands: tuple[str, ...], helpers) -> bool:
    """The method-aware callers (#21307); a route whose first segment is a parameter is never reached by shape."""
    mounted = tuple(c for c in cands if not _leads_with_parameter(c))
    return reached_by_helper(rel, method, mounted, helpers, _toggle_api)


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
    helpers = helper_calls(tree, FRONTENDS, audit.mod.norm_path, audit.mod.FE_EXCLUDE_PATTERNS)
    out: set[str] = set()
    for rel, method, raw, cands in route_sites(tree, audit) if sites is None else sites:
        if any(c.startswith(audit.external) or ("/api" + c).startswith(audit.external) for c in cands):
            continue
        if not _reached(audit.mod, rel, cands, index) and not _reached_by_helper(rel, method, cands, helpers):
            out.add(f"{rel}:{method} {raw}")
    return sorted(out)


def route_files(tree: Tree, audit: Audit) -> list[str]:
    """The files this detector judges: those in the two backends declaring at least one route."""
    return sorted({site[0] for site in route_sites(tree, audit)})
