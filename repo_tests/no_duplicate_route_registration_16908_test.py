# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Two modules must not register the same (method, path) (#16908).

FastAPI matches in registration order, so the first wins and the second is
unreachable -- dead code that reads as a live endpoint. Nothing checked which
one won, and the answer was decided by the order of two lists in two files.

#16908 recorded four such pairs. Three are resolved and the fourth's shadowing
module was deleted; this guard is what stops the fifth, and it found one the
issue does not list.

The expansion is deliberately picky about WHICH router object a registration
names. `from api.voice import realtime_router as voice_realtime_router`
registers `realtime_router`, not the module's `router`; attributing decorators
by file instead invents collisions inside a module that registers twice and
hides real ones between modules. A package registering through its
`__init__.py` is resolved too -- `api.redis_mcp` is one, and treating an
unresolvable module as "no routes" would be the familiar defect of reading
"could not look" as "found nothing".
"""

import ast
import collections
import re

from repo_tests._paths import repo_root

# #15925: the canonical spelling. A hand-rolled parent.parent is the thing
# that guard exists to stop, and it is also simply wrong from a worktree.
ROOT = repo_root()
REG = ROOT / "autobot-backend" / "initialization" / "router_registry"
API = ROOT / "autobot-backend"
VERBS = {"get", "post", "put", "patch", "delete", "head", "options", "websocket"}


def _registrations():
    """(module_dotted, registry_prefix) for both registry forms."""
    out = []
    # feature_routers: first element is the literal string "api.module"
    ft = (REG / "feature_routers.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(ft)):
        if isinstance(node, ast.Tuple) and len(node.elts) >= 2:
            a, b = node.elts[0], node.elts[1]
            if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.startswith("api."):
                if isinstance(b, ast.Constant) and isinstance(b.value, str):
                    out.append((a.value, b.value, "router"))
    # core_routers: first element is a Name bound by `from api.X import router as Y`
    ct = (REG / "core_routers.py").read_text(encoding="utf-8")
    tree = ast.parse(ct)
    alias_to_module = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("api"):
            for al in node.names:
                # `from api.voice import realtime_router as voice_realtime_router`
                # registers realtime_router, NOT the module's `router`. Attributing
                # by file instead of by object invents collisions and hides real ones.
                alias_to_module[al.asname or al.name] = (node.module, al.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Tuple) and len(node.elts) >= 2:
            a, b = node.elts[0], node.elts[1]
            if isinstance(a, ast.Name) and a.id in alias_to_module:
                if isinstance(b, ast.Constant) and isinstance(b.value, str):
                    mod, var = alias_to_module[a.id]
                    out.append((mod, b.value, var))
    return out


def _routes(module_dotted, router_var="router"):
    stem = API / module_dotted.replace(".", "/")
    path = stem.with_suffix(".py")
    if not path.is_file():
        path = stem / "__init__.py"  # a package registers through its __init__
    if not path.is_file():
        return None  # cannot look -- reported, never counted as "no routes"
    text = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(text)
    router_prefix = ""
    for node in ast.walk(tree):
        # only the prefix of the router actually registered
        if isinstance(node, ast.Assign) and any(
            isinstance(t_, ast.Name) and t_.id == router_var for t_ in node.targets
        ):
            if isinstance(node.value, ast.Call) and getattr(node.value.func, "id", "") == "APIRouter":
                for kw in node.value.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        router_prefix = kw.value.value
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            f = dec.func
            if not (isinstance(f, ast.Attribute) and f.attr in VERBS):
                continue
            if not (isinstance(f.value, ast.Name) and f.value.id == router_var):
                continue
            if not dec.args or not isinstance(dec.args[0], ast.Constant):
                continue
            found.append((f.attr.upper(), router_prefix + dec.args[0].value))
    return found


def collisions():
    seen = collections.defaultdict(set)
    unresolved = []
    for module, prefix, var in _registrations():
        r = _routes(module, var)
        if r is None:
            unresolved.append(module)
            continue
        for verb, sub in r:
            full = re.sub(r"/+", "/", f"/api{prefix}{sub}")
            seen[(verb, full)].add(f"{module}:{var}")
    dupes = {k: sorted(v) for k, v in seen.items() if len(v) > 1}
    return dupes, unresolved, len(seen)


#: The one collision that exists today, recorded rather than silently tolerated.
#: SHRINK-ONLY: entries leave when fixed, and none may be added -- a new
#: duplicate is what this guard is for.
#:
#: POST /api/voice/realtime/tools/call is registered by both
#: `api.voice:realtime_router` (core, so it wins) and `api.realtime_session:router`
#: (feature, so it is dead). Not resolved here because the resolution is a
#: judgement, not a cleanup: the two handlers are different implementations, and
#: they differ in DECLARED AUTH -- the winner takes `Depends(get_current_user)`
#: and checks `is_admin_role` (#12717); the dead one declares neither and passes
#: a `session_id` through `realtime_mcp_bridge`, which the winner has no
#: equivalent for. Deleting the dead one drops a capability; re-pathing it makes
#: a handler with no declared auth reachable. Asked on the issue rather than
#: decided here.
KNOWN_DUPLICATES = {
    ("POST", "/api/voice/realtime/tools/call"),
}


def test_no_new_duplicate_route_registration() -> None:
    dupes, unresolved, total = collisions()
    assert not unresolved, (
        f"could not resolve the source of {unresolved} -- this guard has NOT checked them, "
        "which is not the same as finding them clean"
    )
    assert total > 500, f"only {total} routes expanded; the registry parse has drifted and this guard is blind"
    new = {k: v for k, v in dupes.items() if k not in KNOWN_DUPLICATES}
    assert not new, "\n".join(
        f"{verb} {path} registered by {', '.join(mods)}" for (verb, path), mods in sorted(new.items())
    )


def test_the_baseline_only_lists_duplicates_that_still_exist() -> None:
    """A stale entry silently re-licenses the collision it named."""
    dupes, _, _ = collisions()
    gone = KNOWN_DUPLICATES - set(dupes)
    assert not gone, f"these are fixed; remove them from KNOWN_DUPLICATES: {sorted(gone)}"


def test_the_expansion_attributes_routes_to_the_registered_router() -> None:
    """api.voice registers two different router objects at the same prefix.

    If decorators were attributed by file, both registrations would claim every
    route in voice.py and the module would collide with itself -- noise that
    buries the real cross-module collision.
    """
    main = _routes("api.voice", "router")
    realtime = _routes("api.voice", "realtime_router")
    assert main and realtime, "both routers in api.voice should expand to routes"
    assert not (set(main) & set(realtime)), "the two routers in api.voice must not share a route"
    assert ("POST", "/realtime/tools/call") in realtime
    assert ("POST", "/realtime/tools/call") not in main
