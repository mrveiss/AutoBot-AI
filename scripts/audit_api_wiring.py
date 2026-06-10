#!/usr/bin/env python3
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

Exit codes: 0 = clean, 1 = unwired frontend calls found, 2 = unmounted routers
found (combinable: 3 = both). Suitable as a CI gate.

Usage in CI / Claude Code session gate:
    python scripts/audit_api_wiring.py --openapi openapi.json --fail-on-unwired
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "autobot-backend"
FRONTEND_SRC = REPO_ROOT / "autobot-frontend" / "src"

# Frontend files we never treat as real consumers
FE_EXCLUDE_PATTERNS = (
    "__tests__", "/test/", "/tests/", ".test.", ".spec.", "/mocks/",
    ".stories.", "/stories/", "/generated/", "test-config", "template",
)

ROUTE_DECORATOR_RE = re.compile(
    r"@(?:router|app|api_router)\.(get|post|put|delete|patch|websocket|head|options)\(\s*[\'\"]([^\'\"]*)"
)
INCLUDE_ROUTER_RE = re.compile(
    r"include_router\(\s*([A-Za-z_][\w.]*)[^)]*?prefix\s*=\s*[\'\"]([^\'\"]+)", re.S
)
FE_API_RE = re.compile(r"[\'\"`](/api/[A-Za-z0-9_/${}():.\-]+)")
PARAM_RE = re.compile(r"\{[^}]*\}")


def norm_path(p: str) -> str:
    """Normalize a path: collapse params to {p}, strip trailing slash."""
    p = p.split("?")[0]
    p = re.sub(r"\$\{[^}]*\}?", "{p}", p)          # ${id}, ${encodeURIComponent(...
    p = re.sub(r"/:([A-Za-z_]\w*)", "/{p}", p)      # /:id
    p = PARAM_RE.sub("{p}", p)                       # {device_id}
    p = re.sub(r"\{p\}[^/]*", "{p}", p)              # trailing junk after a param
    return p.rstrip("/") or "/"


# ---------------------------------------------------------------- backend ----

def dump_openapi(out_path: str) -> int:
    """Import the app and dump app.openapi() — authoritative route table."""
    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)
    try:
        from app_factory import create_app  # type: ignore
        app = create_app()
        spec = app.openapi()
    except Exception as e:  # noqa: BLE001
        print(f"[dump-openapi] FAILED to build app: {e}", file=sys.stderr)
        return 1
    Path(out_path).write_text(json.dumps(spec, indent=1))
    print(f"[dump-openapi] wrote {len(spec.get('paths', {}))} paths to {out_path}")
    return 0


def backend_paths_from_openapi(src: str) -> set[str]:
    if src.startswith("http://") or src.startswith("https://"):
        with urllib.request.urlopen(src, timeout=10) as r:
            spec = json.load(r)
    else:
        spec = json.loads(Path(src).read_text())
    return {norm_path(p) for p in spec.get("paths", {})}


ROUTER_PREFIX_RE = re.compile(r"APIRouter\([^)]*?prefix\s*=\s*[\'\"]([^\'\"]+)", re.S)


def backend_paths_static() -> tuple[set[str], dict[str, list[str]]]:
    """Best-effort static scan. Returns (normalized paths, module->raw routes)."""
    raw_routes: dict[str, list[str]] = defaultdict(list)
    module_prefix: dict[str, str] = {}
    prefixes: set[str] = set()
    for py in BACKEND.rglob("*.py"):
        sp = str(py)
        if "__pycache__" in sp or "/tests/" in sp or sp.endswith("_test.py") or "/test_" in sp:
            continue
        txt = py.read_text(encoding="utf-8", errors="ignore")
        mp = ROUTER_PREFIX_RE.search(txt)
        if mp:
            module_prefix[sp] = mp.group(1).rstrip("/")
        for _m, path in ROUTE_DECORATOR_RE.findall(txt):
            raw_routes[sp].append(path)
        for _var, prefix in INCLUDE_ROUTER_RE.findall(txt):
            prefixes.add(prefix.rstrip("/"))

    paths: set[str] = set()
    for sp, routes in raw_routes.items():
        own = module_prefix.get(sp, "")
        for r in routes:
            base = own + ("" if (r.startswith("/") or not r) else "/") + r
            for candidate in {r, base}:
                paths.add(norm_path(candidate) if candidate else norm_path(own or "/"))
                for pre in prefixes:       # mount-prefix combinations (loose)
                    paths.add(norm_path(pre + (candidate if candidate.startswith("/")
                                               else "/" + candidate if candidate else "")))
    return paths, raw_routes


def find_unmounted_routers() -> list[str]:
    """Router modules under api/ and llc/api/ never referenced by registry/factory."""
    registry_txt = ""
    for src in [BACKEND / "initialization", BACKEND / "app_factory.py",
                REPO_ROOT / "main.py", BACKEND / "llc"]:
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
        for py in sorted(api_dir.glob("*.py")):
            name = py.stem
            if name == "__init__" or name.endswith("_test") or name.startswith("test_"):
                continue
            txt = py.read_text(encoding="utf-8", errors="ignore")
            if "APIRouter" not in txt:
                continue
            init_txt = (api_dir / "__init__.py").read_text(encoding="utf-8", errors="ignore") \
                if (api_dir / "__init__.py").exists() else ""
            if name not in registry_txt and name not in init_txt:
                unmounted.append(str(py.relative_to(REPO_ROOT)))
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
            for m in FE_API_RE.findall(txt):
                calls[norm_path(m)].add(str(f.relative_to(REPO_ROOT)))
    return calls


# ------------------------------------------------------------------ match ----

def matches(fe: str, backend: set[str]) -> bool:
    """fe like /api/devices/paired vs backend paths possibly without /api."""
    candidates = {fe}
    if fe.startswith("/api/"):
        candidates.add(fe[len("/api"):])
    for c in candidates:
        if c in backend:
            return True
        # allow backend paths that are suffix/superset matches (prefix-mounted)
        for b in backend:
            if b.endswith(c) or c.endswith(b) and len(b) > 3:
                return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--openapi", help="openapi.json path or URL (authoritative mode)")
    ap.add_argument("--dump-openapi", metavar="OUT",
                    help="import app_factory.create_app() and dump spec, then exit")
    ap.add_argument("--dead-surface", action="store_true",
                    help="also report backend paths with no frontend consumer")
    ap.add_argument("--fail-on-unwired", action="store_true",
                    help="exit non-zero if any unwired call or unmounted router found")
    ap.add_argument("--only-prefix", metavar="PREFIX",
                    help="restrict unwired-call reporting and exit code to frontend "
                         "calls under PREFIX (e.g. /api/llc). Lets CI gate one module "
                         "while other pre-existing findings are tracked separately.")
    args = ap.parse_args()

    if args.dump_openapi:
        return dump_openapi(args.dump_openapi)

    if args.openapi:
        backend = backend_paths_from_openapi(args.openapi)
        mode = "AUTHORITATIVE (openapi)"
    else:
        backend, _ = backend_paths_static()
        mode = "STATIC (regex, heuristic — prefer --openapi)"

    fe = frontend_calls()
    print(f"mode: {mode}")
    print(f"backend paths: {len(backend)} | frontend distinct /api/ paths: {len(fe)}\n")

    unwired = {p: files for p, files in sorted(fe.items()) if not matches(p, backend)}
    if args.only_prefix:
        unwired = {p: files for p, files in unwired.items() if p.startswith(args.only_prefix)}
        print(f"(scoped to {args.only_prefix})")
    print(f"== UNWIRED FRONTEND CALLS: {len(unwired)} ==")
    for p, files in unwired.items():
        print(f"  {p}")
        for f in sorted(files)[:3]:
            print(f"      <- {f}")

    unmounted = find_unmounted_routers()
    print(f"\n== UNMOUNTED ROUTER MODULES: {len(unmounted)} ==")
    for m in unmounted:
        print(f"  {m}")

    if args.dead_surface:
        fe_norm = set(fe)
        dead = [b for b in sorted(backend)
                if not any(matches(f, {b}) for f in fe_norm)]
        print(f"\n== BACKEND PATHS WITH NO FRONTEND CONSUMER: {len(dead)} ==")
        for d in dead[:100]:
            print(f"  {d}")
        if len(dead) > 100:
            print(f"  ... and {len(dead) - 100} more")

    rc = 0
    if args.fail_on_unwired:
        if unwired:
            rc |= 1
        # When scoped to a single module, don't fail on repo-wide unmounted
        # routers — those are tracked outside the scoped gate.
        if unmounted and not args.only_prefix:
            rc |= 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
