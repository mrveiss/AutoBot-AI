#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
audit_api_wiring.py — AutoBot frontend/backend API contract audit.

Cross-references every /api/ path the frontend calls against the backend's
actual route table, and flags router modules that exist but are never mounted.

Two modes for obtaining the backend route table:

  1. AUTHORITATIVE (preferred, requires backend deps installed):
       python scripts/audit_api_wiring.py --openapi openapi.json
     where openapi.json was produced by:
       python scripts/audit_api_wiring.py --dump-openapi openapi.json
     (imports app_factory.create_app() and dumps app.openapi())
     ...or point it at a live server:
       python scripts/audit_api_wiring.py --openapi http://127.0.0.1:8001/openapi.json

  2. STATIC (no deps needed, best-effort):
       python scripts/audit_api_wiring.py
     Regex-scans @router/@app decorators and include_router(prefix=...) calls.
     Prefix resolution is heuristic; treat results as triage, not gospel.

SLM control-plane backend (#12381): some frontend calls (getSLMUrl()/
slmFetch()) target autobot-slm-backend (:8000), not autobot-backend (:8001).
Union its route table in with --slm-openapi, produced the same way:
    python scripts/audit_api_wiring.py --dump-slm-openapi slm_openapi.json
    python scripts/audit_api_wiring.py --openapi openapi.json \
        --slm-openapi slm_openapi.json --fail-on-unwired

Baseline (#12381): calls with no backend anywhere yet (tracked product
decisions, e.g. #12378/#12364) can be excluded from --fail-on-unwired without
hiding them from the report:
    python scripts/audit_api_wiring.py --openapi openapi.json \
        --baseline scripts/api_wiring_baseline.txt --fail-on-unwired

Exit codes: 0 = clean, 1 = unwired frontend calls found, 2 = unmounted routers
found (combinable: 3 = both). Suitable as a CI gate.

Usage in CI / Claude Code session gate:
    python scripts/audit_api_wiring.py --openapi openapi.json --fail-on-unwired
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Imported here, not inside the dump helpers: each of them prepends a backend
# dir to sys.path and chdirs into it, and the repo root is not on sys.path when
# this script runs as `python3 scripts/audit_api_wiring.py` — so a late import
# fails with "No module named 'autobot_shared'" and takes the whole dump with it.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from autobot_shared.openapi_schema import normalize_pattern_anchors  # noqa: E402
BACKEND = REPO_ROOT / "autobot-backend"
# #12381: the SLM control-plane backend (autobot-slm-backend, :8000) mounts
# its own '/api'-prefixed route table, entirely separate from autobot-backend
# (:8001). Frontend calls made via getSLMUrl()/slmFetch() resolve against
# THIS app, not the one BACKEND builds — see dump_slm_openapi().
SLM_BACKEND = REPO_ROOT / "autobot-slm-backend"
FRONTEND_SRC = REPO_ROOT / "autobot-frontend" / "src"

# Frontend files we never treat as real consumers
FE_EXCLUDE_PATTERNS = (
    "__tests__",
    "/test/",
    "/tests/",
    ".test.",
    ".spec.",
    "/mocks/",
    ".stories.",
    "/stories/",
    "/generated/",
    "test-config",
    "template",
)

ROUTE_DECORATOR_RE = re.compile(
    r"@(?:router|app|api_router)\.(get|post|put|delete|patch|websocket|head|options)\(\s*[\'\"]([^\'\"]*)"
)
INCLUDE_ROUTER_RE = re.compile(r"include_router\(\s*([A-Za-z_][\w.]*)[^)]*?prefix\s*=\s*[\'\"]([^\'\"]+)", re.S)
FE_API_RE = re.compile(r"[\'\"`](/api/[A-Za-z0-9_/${}():.\-]+)")
# #12326: the dominant idiom composes the path from a helper —
# ``apiClient.get(`${getApiBase()}/knowledge_base/health/status`)``. getApiBase()
# resolves to '/api' (see ssot-config.ts:getApiBase), so the real call target is
# ``/api`` + the captured suffix. Without this the audit only saw literal
# ``'/api/...'`` strings (~42% of calls) and reported a clean bill while dozens of
# ``${getApiBase()}/...`` calls hit non-existent routes.
GETAPIBASE_CALL_RE = re.compile(r"\$\{getApiBase\(\)\}(/[A-Za-z0-9_/${}():.\-]+)")
# #10037: ``${getBackendUrl()}/<path>`` calls. getBackendUrl() is host-level
# (no /api), so any <path> that omits /api hits a path the backend doesn't
# serve. We only flag the high-confidence case where /api<path> IS a real
# route (a forgotten /api, the #10036 class) — never legit non-/api mounts.
BACKEND_URL_CALL_RE = re.compile(r"\$\{getBackendUrl\(\)\}(/[A-Za-z0-9_/${}():.\-]+)")
PARAM_RE = re.compile(r"\{[^}]*\}")


def norm_path(p: str) -> str:
    """Normalize a path: collapse params to {p}, strip trailing slash."""
    p = p.split("?")[0]
    p = re.sub(r"\$\{[^}]*\}?", "{p}", p)  # ${id}, ${encodeURIComponent(...
    p = re.sub(r"/:([A-Za-z_]\w*)", "/{p}", p)  # /:id
    p = PARAM_RE.sub("{p}", p)  # {device_id}
    p = re.sub(r"\{p\}[^/]*", "{p}", p)  # trailing junk after a param
    return p.rstrip("/") or "/"


# ---------------------------------------------------------------- backend ----


def _runtime_websocket_paths(app) -> set[str]:  # noqa: ANN001
    """Best-effort runtime WebSocketRoute walk of ``app.routes``.

    Works when the installed FastAPI/Starlette flattens included sub-router
    routes onto ``app.routes`` (true through fastapi<0.139). It is NOT relied
    on alone — see static_websocket_paths() for why (#12381).
    """
    from starlette.routing import WebSocketRoute  # type: ignore

    return {r.path for r in app.routes if isinstance(r, WebSocketRoute)}


def dump_openapi(out_path: str) -> int:
    """Import the app and dump app.openapi() — authoritative route table."""
    # Resolve BEFORE chdir: a relative out_path must land where the caller
    # expects, not inside autobot-backend/ (#9864 — this stranded openapi.json
    # in CI and the audit step crashed with FileNotFoundError every run).
    out = Path(out_path).resolve()
    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)
    try:
        from app_factory import create_app  # type: ignore

        app = create_app()
        # Same anchor normalisation as the SLM path below — the main backend has
        # no Field(pattern=…) today, so this is prophylactic, not a fix. It is
        # here so the first one added does not silently publish `\z`.
        spec = normalize_pattern_anchors(app.openapi())
        # FastAPI omits WebSocket routes from OpenAPI — record them in a
        # custom key so the audit can verify /api/ws* style frontend calls
        # against the real route table instead of flagging them (GH#9864).
        # Union runtime introspection with a static source scan (#12381):
        # fastapi>=0.139's lazy ``_IncludedRouter`` wrapping means
        # include_router()'d routes are no longer flattened onto app.routes,
        # so the runtime walk alone silently returns zero WS routes on newer
        # FastAPI (confirmed in CI: "+0 websocket" despite 25 real handlers).
        # The static scan is version-independent and is the source of truth;
        # the runtime walk is kept as a supplementary safety net.
        ws = _runtime_websocket_paths(app) | static_websocket_paths(BACKEND)
        spec["x-websocket-paths"] = sorted(ws)
    except Exception as e:  # noqa: BLE001
        print(f"[dump-openapi] FAILED to build app: {e}", file=sys.stderr)
        return 1
    out.write_text(json.dumps(spec, indent=1))
    print(
        f"[dump-openapi] wrote {len(spec.get('paths', {}))} paths "
        f"(+{len(spec.get('x-websocket-paths', []))} websocket) to {out}"
    )
    return 0


def dump_slm_openapi(out_path: str) -> int:
    """Import the SLM backend app and dump app.openapi() (#12381).

    Mirrors dump_openapi() but imports the module-level ``app`` from
    autobot-slm-backend/main.py instead of calling autobot-backend's
    app_factory.create_app(). Both backends mount their routers under the
    same ``/api`` prefix (verified: autobot-slm-backend/main.py:617-677 all
    use ``prefix="/api"``), so the resulting path sets are directly unionable
    with backend_paths_from_openapi() output — no extra prefix normalization
    needed.
    """
    out = Path(out_path).resolve()
    sys.path.insert(0, str(SLM_BACKEND))
    os.chdir(SLM_BACKEND)
    try:
        from main import app  # type: ignore

        # Must match autobot-slm-backend/scripts/dump_openapi.py exactly: CI
        # regenerates through THIS path and diffs against the file the other
        # path produced, so any divergence is reported as stale generated types.
        spec = normalize_pattern_anchors(app.openapi())
        # Same runtime+static WebSocket union as dump_openapi() (GH#9864, #12381).
        ws = _runtime_websocket_paths(app) | static_websocket_paths(SLM_BACKEND)
        spec["x-websocket-paths"] = sorted(ws)
    except Exception as e:  # noqa: BLE001
        print(f"[dump-slm-openapi] FAILED to build app: {e}", file=sys.stderr)
        return 1
    out.write_text(json.dumps(spec, indent=1))
    print(
        f"[dump-slm-openapi] wrote {len(spec.get('paths', {}))} paths "
        f"(+{len(spec.get('x-websocket-paths', []))} websocket) to {out}"
    )
    return 0


def backend_paths_from_openapi(src: str) -> set[str]:
    if src.startswith("http://") or src.startswith("https://"):
        with urllib.request.urlopen(src, timeout=10) as r:
            spec = json.load(r)
    else:
        spec = json.loads(Path(src).read_text())
    paths = {norm_path(p) for p in spec.get("paths", {})}
    # Websocket routes recorded by dump_openapi (absent from live-server specs).
    paths |= {norm_path(p) for p in spec.get("x-websocket-paths", [])}
    return paths


ROUTER_PREFIX_RE = re.compile(r"APIRouter\([^)]*?prefix\s*=\s*[\'\"]([^\'\"]+)", re.S)
# #12432: feature/core routers are mounted via *data-driven config tuples* in
# initialization/router_registry/*.py — e.g.
#   ("api.advanced_control", "/advanced-control", ["advanced-control"], "advanced_control")
# in feature_routers.py, or
#   (overseer_router, "/overseer", ["overseer", "agent"], "overseer")
# + a top-level ``from api.overseer_handlers import router as overseer_router``
# in core_routers.py — never a literal ``include_router(prefix=...)`` call
# (app_factory.py does that generically: ``prefix=f"/api{prefix}"``), so
# INCLUDE_ROUTER_RE never sees these prefixes at all. Without resolving them,
# a sub-router's routes (including websocket ones) get NO prefix, not merely
# the wrong one — e.g. advanced_control.py's ``/ws/monitoring`` never becomes
# ``/advanced-control/ws/monitoring``.
ROUTER_CONFIG_ENTRY_RE = re.compile(
    r"\(\s*(?:[\'\"](?P<mod>api(?:\.\w+)+)[\'\"]|(?P<var>[A-Za-z_]\w*))"
    r"\s*,\s*(?:[\'\"]router[\'\"]\s*,\s*)?[\'\"](?P<prefix>[^\'\"]*)[\'\"]\s*,\s*\["
)
ROUTER_IMPORT_ALIAS_RE = re.compile(r"from\s+(api(?:\.\w+)+)\s+import\s+router\s+as\s+(\w+)")


def _registry_module_prefixes(root: Path) -> dict[str, str]:
    """Map ``api/<module>.py`` -> its registry-configured mount prefix (#12432).

    Scans ``initialization/router_registry/*.py`` for the config-tuple
    patterns described above, resolving variable-alias entries (core_routers.py
    style) via their ``from api.X import router as X_router`` import line.
    Returns {} for backends (e.g. autobot-slm-backend) with no such directory.
    """
    registry_dir = root / "initialization" / "router_registry"
    if not registry_dir.is_dir():
        return {}
    alias_to_module: dict[str, str] = {}
    entries: list[tuple[str, str]] = []
    for py in registry_dir.glob("*.py"):
        txt = py.read_text(encoding="utf-8", errors="ignore")
        alias_to_module.update({alias: mod for mod, alias in ROUTER_IMPORT_ALIAS_RE.findall(txt)})
        entries.extend(
            (m.group("mod") or m.group("var"), m.group("prefix")) for m in ROUTER_CONFIG_ENTRY_RE.finditer(txt)
        )
    module_prefix: dict[str, str] = {}
    for mod_or_var, prefix in entries:
        mod = mod_or_var if mod_or_var.startswith("api.") else alias_to_module.get(mod_or_var)
        if mod:
            module_prefix[mod.replace(".", "/") + ".py"] = prefix.rstrip("/")
    return module_prefix


def _scan_route_decorators(
    root: Path,
) -> tuple[dict[str, list[tuple[str, str]]], dict[str, str], set[str]]:
    """Regex-scan `root` for @router.<method>(...) decorators, APIRouter
    prefixes, and include_router() mount prefixes. Returns
    (module -> [(method, path), ...], module -> own prefix, mount prefixes).
    """
    raw: dict[str, list[tuple[str, str]]] = defaultdict(list)
    module_prefix: dict[str, str] = {}
    prefixes: set[str] = set()
    for py in root.rglob("*.py"):
        sp = str(py)
        if "__pycache__" in sp or "/tests/" in sp or sp.endswith("_test.py") or "/test_" in sp:
            continue
        txt = py.read_text(encoding="utf-8", errors="ignore")
        mp = ROUTER_PREFIX_RE.search(txt)
        if mp:
            module_prefix[sp] = mp.group(1).rstrip("/")
        for method, path in ROUTE_DECORATOR_RE.findall(txt):
            raw[sp].append((method, path))
        for _var, prefix in INCLUDE_ROUTER_RE.findall(txt):
            prefixes.add(prefix.rstrip("/"))
    return raw, module_prefix, prefixes


def _combine_prefixed_paths(
    raw_routes: dict[str, list[str]],
    module_prefix: dict[str, str],
    prefixes: set[str],
    registry_prefixes: dict[str, str] | None = None,
) -> set[str]:
    """Combine each module's raw route strings with its own APIRouter prefix,
    its registry-resolved mount prefix if any (#12432 — precise, per-module),
    and every known literal mount prefix (loose — mount-prefix combos aren't
    scoped per-module, matching the pre-existing heuristic)."""
    paths: set[str] = set()
    registry_prefixes = registry_prefixes or {}
    for sp, routes in raw_routes.items():
        own = module_prefix.get(sp, "")
        reg = next((p for suffix, p in registry_prefixes.items() if sp.endswith("/" + suffix)), None)
        for r in routes:
            base = own + ("" if (r.startswith("/") or not r) else "/") + r
            candidates = {r, base}
            if reg is not None:
                candidates.add(reg + ("" if (r.startswith("/") or not r) else "/") + r)
            for candidate in candidates:
                paths.add(norm_path(candidate) if candidate else norm_path(own or reg or "/"))
                for pre in prefixes:
                    paths.add(
                        norm_path(
                            pre + (candidate if candidate.startswith("/") else "/" + candidate if candidate else "")
                        )
                    )
    return paths


def backend_paths_static(root: Path = BACKEND) -> tuple[set[str], dict[str, list[str]]]:
    """Best-effort static scan. Returns (normalized paths, module->raw routes)."""
    raw, module_prefix, prefixes = _scan_route_decorators(root)
    raw_routes = {sp: [path for _method, path in entries] for sp, entries in raw.items()}
    registry_prefixes = _registry_module_prefixes(root)
    return (
        _combine_prefixed_paths(raw_routes, module_prefix, prefixes, registry_prefixes),
        raw_routes,
    )


def static_websocket_paths(root: Path) -> set[str]:
    """Static-scan websocket-only paths under `root` (#12381, #12432).

    Runtime WebSocketRoute introspection of a live app is unreliable across
    FastAPI versions: fastapi>=0.139's lazy ``_IncludedRouter`` wrapping means
    ``app.routes`` no longer flattens include_router()'d routes, so a naive
    ``isinstance(r, WebSocketRoute)`` walk silently finds nothing. Websocket
    declarations are structurally simple (one ``@router.websocket(...)`` per
    handler + static string prefixes), so a source scan — reusing the same
    prefix-combination algorithm as backend_paths_static() — is both simpler
    and version-independent. No `add_websocket_route()`/programmatic
    registrations exist in this codebase (verified by grep), so decorator
    scanning has full coverage. #12432: also resolves data-driven registry
    mount prefixes (see _registry_module_prefixes) so sub-router WS routes
    (advanced_control.py, overseer_handlers.py, ...) get their real prefix
    instead of none at all.
    """
    raw, module_prefix, prefixes = _scan_route_decorators(root)
    ws_routes = {sp: [path for method, path in entries if method == "websocket"] for sp, entries in raw.items()}
    ws_routes = {sp: paths for sp, paths in ws_routes.items() if paths}
    registry_prefixes = _registry_module_prefixes(root)
    return _combine_prefixed_paths(ws_routes, module_prefix, prefixes, registry_prefixes)


def _module_served_by_openapi(txt: str, backend: set[str]) -> bool:
    """Authoritative suppression: a module is mounted when ALL of its declared
    routes appear in the real route table (any-route matching would let one
    coincidental suffix like /status suppress a whole unmounted module)."""
    own = ROUTER_PREFIX_RE.search(txt)
    prefix = own.group(1).rstrip("/") if own else ""
    checked = 0
    for _m, route in ROUTE_DECORATOR_RE.findall(txt):
        full = norm_path(prefix + (route if route.startswith("/") or not route else "/" + route))
        if full == "/":
            continue
        checked += 1
        if not any(b.endswith(full) for b in backend):
            return False
    return checked > 0


def find_unmounted_routers(backend: set[str] | None = None) -> list[str]:
    """Router modules under api/ and llc/api/ never reachable from the
    registry/factory — directly or via sibling-module include_router chains
    (e.g. api/analytics.py sub-including analytics_engagement, GH#9864)."""
    registry_txt = ""
    for src in [BACKEND / "initialization", BACKEND / "app_factory.py", REPO_ROOT / "main.py", BACKEND / "llc"]:
        if src.is_dir():
            for py in src.rglob("*.py"):
                if "api" in py.parts and py.parent.name == "api":
                    continue  # don't let router files vouch for themselves
                registry_txt += py.read_text(encoding="utf-8", errors="ignore")
        elif src.exists():
            registry_txt += src.read_text(encoding="utf-8", errors="ignore")

    unmounted = []
    for api_dir in [BACKEND / "api", BACKEND / "llc" / "api"]:
        if not api_dir.exists():
            continue
        module_txt = {
            py.stem: py.read_text(encoding="utf-8", errors="ignore")
            for py in api_dir.glob("*.py")
            if py.stem != "__init__" and not py.stem.endswith("_test") and not py.stem.startswith("test_")
        }
        init_txt = (
            (api_dir / "__init__.py").read_text(encoding="utf-8", errors="ignore")
            if (api_dir / "__init__.py").exists()
            else ""
        )

        # Transitive vouching: registry-mounted modules vouch for siblings
        # they sub-include via `<name>.router`, to a fixpoint (GH#9864 —
        # e.g. api/analytics.py sub-includes analytics_engagement). Word
        # boundary required: bare substring matching would let
        # `gpu_monitoring.router` vouch an unmounted `monitoring` module.
        mounted = {n for n in module_txt if n in registry_txt or n in init_txt}
        changed = True
        while changed:
            changed = False
            for parent in list(mounted):
                for child in module_txt:
                    if child not in mounted and re.search(
                        rf"(?<![A-Za-z0-9_.]){re.escape(child)}\.router",
                        module_txt[parent],
                    ):
                        mounted.add(child)
                        changed = True

        for name in sorted(module_txt):
            txt = module_txt[name]
            if "APIRouter" not in txt or name in mounted:
                continue
            if backend and _module_served_by_openapi(txt, backend):
                continue
            unmounted.append(str((api_dir / f"{name}.py").relative_to(REPO_ROOT)))
    return unmounted


# --------------------------------------------------------------- frontend ----


def frontend_calls() -> dict[str, set[str]]:
    """Normalized /api/ path -> set of consuming files (tests/mocks excluded)."""
    calls: dict[str, set[str]] = defaultdict(set)
    for ext in ("*.ts", "*.vue", "*.js", "*.tsx"):
        for f in FRONTEND_SRC.rglob(ext):
            sp = str(f)
            if "node_modules" in sp or any(x in sp for x in FE_EXCLUDE_PATTERNS):
                continue
            txt = f.read_text(encoding="utf-8", errors="ignore")
            for line in txt.splitlines():
                # Comment lines hold doc EXAMPLES (`* apiClient.get('/api/users')`),
                # not real calls — skip them.
                if line.lstrip()[:2] in ("* ", "//", "/*") or line.strip() == "*":
                    continue
                # Literal '/api/...' strings and getApiBase()-composed paths
                # (#12326). getApiBase() -> '/api', so prepend it to the suffix.
                matched = list(FE_API_RE.findall(line))
                matched += ["/api" + s for s in GETAPIBASE_CALL_RE.findall(line)]
                for m in matched:
                    p = norm_path(m)
                    # Unbalanced braces = extraction artifact (brace-expansion
                    # notation inside comments, e.g. `/api/x/{a,b}/y`), not a call.
                    if p.count("{") != p.count("}"):
                        continue
                    calls[p].add(str(f.relative_to(REPO_ROOT)))
    return calls


def find_missing_api_prefix(backend: set[str]) -> dict[str, set[str]]:
    """``${getBackendUrl()}/<path>`` calls that omit ``/api`` but whose
    ``/api<path>`` form IS a real backend route — a guaranteed 404 from
    forgetting the prefix (#10037, the #10036 class). High-confidence only:
    legitimate non-/api mounts (no /api equivalent) are never flagged."""
    missing: dict[str, set[str]] = defaultdict(set)
    for ext in ("*.ts", "*.vue", "*.js", "*.tsx"):
        for f in FRONTEND_SRC.rglob(ext):
            sp = str(f)
            if "node_modules" in sp or any(x in sp for x in FE_EXCLUDE_PATTERNS):
                continue
            txt = f.read_text(encoding="utf-8", errors="ignore")
            for line in txt.splitlines():
                if line.lstrip()[:2] in ("* ", "//", "/*") or line.strip() == "*":
                    continue
                for raw in BACKEND_URL_CALL_RE.findall(line):
                    p = norm_path(raw)
                    if p.startswith("/api") or p.count("{") != p.count("}"):
                        continue  # already prefixed, or an extraction artifact
                    if matches("/api" + p, backend) and not matches(p, backend):
                        missing[p].add(str(f.relative_to(REPO_ROOT)))
    return missing


# ------------------------------------------------------------------ match ----


def _segments_match(fe: str, b: str) -> bool:
    """Segment-wise comparison where {p} (a runtime-resolved template segment
    or a path parameter) matches any single concrete segment on either side."""
    sa, sb = fe.strip("/").split("/"), b.strip("/").split("/")
    if len(sa) != len(sb):
        return False
    return all(x == y or x == "{p}" or y == "{p}" for x, y in zip(sa, sb))


def matches(fe: str, backend: set[str]) -> bool:
    """fe like /api/devices/paired vs backend paths possibly without /api."""
    candidates = {fe}
    # /api-stripped variant (static-mode tables lack the /api prefix) — but
    # not when the next segment is a wildcard: /{p}/x would re-match /api/x.
    if fe.startswith("/api/") and not fe.startswith("/api/{p}"):
        candidates.add(fe[len("/api") :])
    # `…x${qs}` template tails are usually query strings appended to the path
    # (norm turns them into a glued `x{p}`) — also try the stripped path.
    for c in list(candidates):
        if c.endswith("{p}") and not c.endswith("/{p}"):
            candidates.add(c[: -len("{p}")].rstrip("/") or "/")
    for c in candidates:
        if c in backend:
            return True
        if any(_segments_match(c, b) for b in backend):
            return True
        # Bare base-URL string (`/api/transcriber` + path concatenation):
        # treat as wired when real routes exist beneath it. Known trade-off:
        # this also masks a missing collection-root endpoint (GET /api/x when
        # only /api/x/{id} exists) — static extraction cannot tell a base
        # constant from a full call.
        if any(b.startswith(c + "/") for b in backend):
            return True
    return False


# ------------------------------------------------------------- suggestions ----

# Below this score a "closest match" is noise — an unrelated route that merely
# shares a prefix. Better to print nothing than to send someone rewiring a call
# to the wrong endpoint (#12738).
SUGGESTION_FLOOR = 0.55


def _leading_agreement(fe_segs: list[str], cand_segs: list[str]) -> int:
    """Number of segments the two paths agree on from the left."""
    count = 0
    for x, y in zip(fe_segs, cand_segs):
        if x != y:
            break
        count += 1
    return count


def _similarity(fe: str, candidate: str) -> float:
    """Segment-aware similarity in [0, 1] between a call and a real route.

    A rename almost always changes the LAST segment and keeps the namespace, so
    agreement on the leading segments is weighted alongside overall positional
    agreement; raw string distance only breaks ties. Pure ``difflib`` on the
    whole path ranks by character overlap, which favours long unrelated routes
    over the short renamed sibling that is usually the right answer.

    Leading agreement also suppresses static mode's route-table artifacts: it
    combines every registry prefix with every route, so ``/voice/<x>`` and
    ``/ai-stack/<x>`` shadow the real ``/<x>`` and would otherwise score well on
    positional agreement alone despite belonging to another namespace entirely.
    """
    fe_segs, cand_segs = fe.strip("/").split("/"), candidate.strip("/").split("/")
    span = max(len(fe_segs), len(cand_segs))
    aligned = sum(1 for x, y in zip(fe_segs, cand_segs) if x == y)
    leading = _leading_agreement(fe_segs, cand_segs)
    text_score = difflib.SequenceMatcher(None, fe, candidate).ratio()
    return 0.45 * (aligned / span) + 0.35 * (leading / span) + 0.20 * text_score


def suggest_routes(fe: str, backend: set[str], limit: int = 3) -> list[str]:
    """Closest surviving routes for an unwired call — "did you mean …?" (#12738).

    Turns detection into guided repair: the gate already says ``/api/foo/removed``
    is dead, but not that ``/api/foo/renamed`` is what replaced it.

    Both the call and its ``/api``-stripped variant are scored, because static
    mode's route table has no ``/api`` prefix while authoritative (OpenAPI) mode
    does — the same reason ``matches()`` tries both.

    Returns up to *limit* routes, best first; empty when nothing scores above
    ``SUGGESTION_FLOOR`` or shares a path segment with the call.
    """
    if not backend:
        return []

    variants = {fe}
    if fe.startswith("/api/"):
        variants.add(fe[len("/api") :])

    fe_segments = {s for v in variants for s in v.strip("/").split("/") if s and s != "{p}"}
    scored: list[tuple[float, str]] = []
    for candidate in backend:
        # Require a shared concrete segment: without it a "closest match" is
        # just the least-dissimilar unrelated route.
        if not fe_segments & set(candidate.strip("/").split("/")):
            continue
        score = max(_similarity(v, candidate) for v in variants)
        if score >= SUGGESTION_FLOOR:
            scored.append((score, candidate))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, path in scored[:limit]]


def _print_call(path: str, files: set[str], backend: set[str]) -> None:
    """Print one finding with its callers and closest-match suggestions."""
    print(f"  {path}")
    for suggestion in suggest_routes(path, backend):
        print(f"      ?  did you mean {suggestion}")
    for f in sorted(files)[:3]:
        print(f"      <- {f}")


# ---------------------------------------------------------------- baseline ----


def load_baseline(path: str | None) -> set[str]:
    """Load a committed list of known/tracked-unwired frontend paths (#12381).

    One normalized path per line (the same ``/api/...`` form printed under
    ``== UNWIRED FRONTEND CALLS ==``); blank lines and ``#``-comments ignored.
    Calls in the baseline are still *reported* (as tracked) but excluded from
    the ``--fail-on-unwired`` exit code — the standard gradually-fixed-lint
    baseline pattern, so the gate only fails on NEW drift.
    """
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    baseline: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        baseline.add(line)
    return baseline


def partition_baseline(
    unwired: dict[str, set[str]], baseline: set[str]
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Split unwired calls into (tracked, new) by baseline membership."""
    tracked = {p: files for p, files in unwired.items() if p in baseline}
    new = {p: files for p, files in unwired.items() if p not in baseline}
    return tracked, new


def _resource(path: str) -> str:
    """The last concrete (non-parameter) segment — what the route acts on.

    ``/api/kb/documents/{id}/similar`` -> ``similar``; ``/api/kb/fact/{id}`` -> ``fact``.
    """
    concrete = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
    return concrete[-1].lower() if concrete else ""


def _namespace(path: str) -> str:
    """The top-level namespace segment, ignoring a leading ``/api``.

    Static and authoritative mode disagree about the ``/api`` prefix, so it is
    stripped before comparing — the same reason ``matches()`` tries both forms.
    """
    segs = [s for s in path.strip("/").split("/") if s]
    if segs and segs[0] == "api":
        segs = segs[1:]
    return segs[0].lower() if segs else ""


def _same_resource(a: str, b: str) -> bool:
    """Whether two resource segments name the same thing, modulo plurality.

    ``category``/``categories`` is a rename; ``restart``/``health`` is not.

    Each word expands to every singular form it could reduce to, and a shared
    form means a match. Reducing each word to one canonical form is not enough:
    ``services`` reduces to ``servic`` via ``-es`` while ``service`` is already
    singular, so the pair would miss.
    """

    def forms(word: str) -> set[str]:
        out = {word}
        for suffix, base in (("ies", "y"), ("es", ""), ("s", "")):
            if word.endswith(suffix) and len(word) > len(suffix):
                out.add(word[: -len(suffix)] + base)
        return out

    return bool(forms(a) & forms(b))


def rename_candidates(path: str, suggestions: list[str]) -> list[str]:
    """Suggestions that actually look like *path* renamed, not merely nearby.

    ``suggest_routes`` ranks by similarity, which is the right tool for "here
    are the closest surviving routes" but a poor test for "this endpoint was
    renamed": every sibling in a surviving namespace clears the floor, because
    ``_similarity`` weights leading-segment agreement heavily. That made
    ``/api/system/restart -> /api/system/health`` indistinguishable from a real
    rename, and a baseline of genuinely-unimplemented endpoints (#12378) read
    as 29 renamed ones.

    A rename keeps the resource and moves the path around it, so require both:
    the same top-level namespace (ruling out ``/api/browser/execute`` matching
    ``/api/workflow/execute``) and the same resource segment (ruling out
    ``restart`` matching ``health``).
    """
    return [
        s
        for s in suggestions
        if _namespace(s) == _namespace(path) and _same_resource(_resource(s), _resource(path))
    ]


def audit_baseline(
    baseline: set[str],
    unwired_all: dict[str, set[str]],
    frontend: dict[str, set[str]],
    backend: set[str],
) -> dict[str, list[tuple[str, list[str]]]]:
    """Classify baseline entries so removals cannot hide in there forever (#12738).

    The baseline suppresses "known unwired" calls from the gate. That is the
    right pattern for endpoints nobody has implemented yet, but it also
    silently absorbs endpoints that were REMOVED or RENAMED after their caller
    was baselined: the gate stays green while the button is dead. Nothing
    distinguished the two cases.

    Returns four buckets:

    ``rematch``
        Baselined calls whose resource survives under a new path in the same
        namespace — a rename. These want rewiring, not suppression, so they are
        reported with the matching routes instead of being swallowed.
    ``namespace_only``
        The namespace is alive but nothing in it preserves the resource. This
        is *not* evidence of a rename (#12894): it is the expected shape of an
        unimplemented endpoint sitting beside implemented siblings, so it stays
        informational and the nearest routes are shown only as context.
    ``resolved``
        Baselined calls that now match a real route. The entry is stale and
        should be pruned, otherwise the baseline only ever grows.
    ``absent``
        Baselined calls no caller makes any more. Also prunable — the frontend
        code moved on and the entry is pure residue.
    """
    resolved: list[tuple[str, list[str]]] = []
    absent: list[tuple[str, list[str]]] = []
    rematch: list[tuple[str, list[str]]] = []
    namespace_only: list[tuple[str, list[str]]] = []

    for path in sorted(baseline):
        if path not in frontend:
            absent.append((path, []))
        elif path not in unwired_all:
            resolved.append((path, []))
        else:
            suggestions = suggest_routes(path, backend)
            if not suggestions:
                continue
            renames = rename_candidates(path, suggestions)
            if renames:
                rematch.append((path, renames))
            else:
                namespace_only.append((path, suggestions))

    return {
        "rematch": rematch,
        "namespace_only": namespace_only,
        "resolved": resolved,
        "absent": absent,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--openapi", help="openapi.json path or URL (authoritative mode)")
    ap.add_argument("--dump-openapi", metavar="OUT", help="import app_factory.create_app() and dump spec, then exit")
    ap.add_argument(
        "--slm-openapi",
        metavar="FILE",
        help="second openapi.json (SLM control-plane backend, "
        "autobot-slm-backend) whose paths are UNIONed into the known "
        "backend route table (#12381) — produce it with "
        "--dump-slm-openapi first",
    )
    ap.add_argument(
        "--dump-slm-openapi", metavar="OUT", help="import autobot-slm-backend/main.py's app and dump spec, " "then exit"
    )
    ap.add_argument(
        "--baseline",
        metavar="FILE",
        help="file of known/tracked unwired frontend paths (one per line) "
        "excluded from the --fail-on-unwired exit code (#12381) — "
        "still reported, just not gated",
    )
    ap.add_argument("--dead-surface", action="store_true", help="also report backend paths with no frontend consumer")
    ap.add_argument(
        "--fail-on-unwired", action="store_true", help="exit non-zero if any unwired call or unmounted router found"
    )
    ap.add_argument(
        "--only-prefix",
        metavar="PREFIX",
        help="restrict unwired-call reporting and exit code to frontend "
        "calls under PREFIX (e.g. /api/llc). Lets CI gate one module "
        "while other pre-existing findings are tracked separately.",
    )
    args = ap.parse_args()

    if args.dump_openapi:
        return dump_openapi(args.dump_openapi)

    if args.dump_slm_openapi:
        return dump_slm_openapi(args.dump_slm_openapi)

    if args.openapi:
        backend = backend_paths_from_openapi(args.openapi)
        mode = "AUTHORITATIVE (openapi)"
        if args.slm_openapi:
            slm_backend = backend_paths_from_openapi(args.slm_openapi)
            backend |= slm_backend
            mode += f" + SLM ({len(slm_backend)} paths unioned)"
    else:
        backend, _ = backend_paths_static()
        mode = "STATIC (regex, heuristic — prefer --openapi)"

    fe = frontend_calls()
    print(f"mode: {mode}")
    print(f"backend paths: {len(backend)} | frontend distinct /api/ paths: {len(fe)}\n")

    unwired_all = {p: files for p, files in sorted(fe.items()) if not matches(p, backend)}
    if args.only_prefix:
        unwired_all = {p: files for p, files in unwired_all.items() if p.startswith(args.only_prefix)}
        print(f"(scoped to {args.only_prefix})")
    baseline = load_baseline(args.baseline)
    tracked, unwired = partition_baseline(unwired_all, baseline)
    if tracked:
        print(f"== TRACKED UNWIRED CALLS (baselined, non-gating): {len(tracked)} ==")
        for p, files in tracked.items():
            _print_call(p, files, backend)
    print(f"== UNWIRED FRONTEND CALLS: {len(unwired)} ==")
    for p, files in unwired.items():
        _print_call(p, files, backend)

    # #12738: a removed endpoint whose caller is already baselined would leave
    # the gate green while the button is dead. Report what the baseline is
    # absorbing — non-gating, so the blocking behaviour is unchanged.
    if baseline:
        health = audit_baseline(baseline, unwired_all, fe, backend)
        rematch, resolved, absent = health["rematch"], health["resolved"], health["absent"]
        namespace_only = health["namespace_only"]
        print(
            f"\n== BASELINE HEALTH: {len(rematch)} renamed, "
            f"{len(namespace_only)} namespace-only, "
            f"{len(resolved)} resolved, {len(absent)} no-longer-called =="
        )
        for path, suggestions in rematch:
            print(f"  RENAMED ENDPOINT (rewire the caller)  {path}")
            for suggestion in suggestions:
                print(f"      ->  now served by {suggestion}")
        for path, suggestions in namespace_only:
            print(f"  NAMESPACE ALIVE, NO MATCHING ROUTE  {path}")
            for suggestion in suggestions:
                print(f"      ~  nearest, NOT a rename: {suggestion}")
        for path, _ in resolved:
            print(f"  RESOLVED (prune from baseline)  {path}")
        for path, _ in absent:
            print(f"  NO LONGER CALLED (prune from baseline)  {path}")

    # #10037: getBackendUrl() calls that forgot /api (only when /api<path> is real).
    missing_api = find_missing_api_prefix(backend) if args.openapi else {}
    if args.only_prefix:
        missing_api = {p: f for p, f in missing_api.items() if ("/api" + p).startswith(args.only_prefix)}
    print(f"\n== getBackendUrl() CALLS MISSING /api: {len(missing_api)} ==")
    for p, files in sorted(missing_api.items()):
        print(f"  {p}  (should be /api{p})")
        for f in sorted(files)[:3]:
            print(f"      <- {f}")

    unmounted = find_unmounted_routers(backend if args.openapi else None)
    print(f"\n== UNMOUNTED ROUTER MODULES: {len(unmounted)} ==")
    for m in unmounted:
        print(f"  {m}")

    if args.dead_surface:
        fe_norm = set(fe)
        dead = [b for b in sorted(backend) if not any(matches(f, {b}) for f in fe_norm)]
        print(f"\n== BACKEND PATHS WITH NO FRONTEND CONSUMER: {len(dead)} ==")
        for d in dead[:100]:
            print(f"  {d}")
        if len(dead) > 100:
            print(f"  ... and {len(dead) - 100} more")

    rc = 0
    if args.fail_on_unwired:
        if unwired or missing_api:
            rc |= 1
        # When scoped to a single module, don't fail on repo-wide unmounted
        # routers — those are tracked outside the scoped gate.
        if unmounted and not args.only_prefix:
            rc |= 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
