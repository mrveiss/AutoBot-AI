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


#: Modules whose routes this guard CANNOT see, counted rather than ignored.
#: The expansion reads `@router.<verb>` decorators on the registered object. A
#: module that composes with `router.include_router(other)` mounts routes this
#: never visits, so the pair count below is a floor, not a total.
#:
#: Sixteen non-test modules, measured. An earlier count of 77 was this same
#: grep including `*_test.py`, which is why the pin is computed and asserted
#: rather than written down from a shell one-liner.
#:
#: A better guard already exists and is not mine: commit f4e2d6badb on the
#: abandoned branch `issue-16908-duplicate-routes` rebuilt it on REAL router
#: objects -- calling load_core_routers()/load_optional_routers() and walking
#: effective_routes(), which resolves nested include_router() properly. It was
#: removed from that branch by a later commit ("split guard out of #16918 per
#: review") and never landed. It cannot be verified on this machine: importing
#: real routers pulls llc.scheduler.base, which requires Python 3.11+ and this
#: interpreter is 3.10 (CI runs 3.14). Adopting it is #17325.
#:
#: Until then the blind spot is PINNED, so it cannot quietly grow: if a module
#: starts composing with include_router, this fails and the next person learns
#: the guard got blinder rather than discovering it years later.
COMPOSING_MODULES_PIN = 16


def _modules_using_include_router() -> list[str]:
    api = ROOT / "autobot-backend" / "api"
    hits = []
    for path in sorted(api.glob("*.py")):
        if "test" in path.name:
            continue
        if "include_router" in path.read_text(encoding="utf-8", errors="replace"):
            hits.append(path.name)
    return hits


def test_the_blind_spot_is_pinned_not_ignored() -> None:
    """This guard under-counts, and by how much must be visible.

    A count a guard cannot actually establish is the defect this repository
    governs. Reporting "1518 pairs, 1 duplicate" while structurally unable to
    see include_router-composed routes would be exactly that, so the size of
    what it cannot see is pinned here instead.
    """
    composing = _modules_using_include_router()
    assert len(composing) == COMPOSING_MODULES_PIN, (
        f"{len(composing)} api modules compose with include_router, pin says {COMPOSING_MODULES_PIN}. "
        "This guard cannot see routes mounted that way, so the blind spot changed size. "
        "Update the pin deliberately, or adopt the real-router enumeration (#17325)."
    )


# -- the guard proved by mutation (#16908 AC4) --------------------------------
#
# The tests above prove the EXPANSION attributes routes correctly. None of them
# proved the guard FIRES: that a planted duplicate reddens it and names both
# sides. Those are different claims, and only the second is what the guard is
# for.
#
# Proved here against the real detector -- `collisions()` itself, with its tree
# roots pointed at a synthetic checkout -- rather than by reimplementing the
# comparison in the test, which would prove only that the test can find a
# duplicate.
#
# The second case is the one that makes the first honest. A duplicate planted
# where the AST detector cannot look (a route mounted through include_router)
# does NOT redden the guard, so "I planted a duplicate and it went red" means
# nothing unless the plant was in the reached region. Both directions are
# asserted, so a future change that quietly widens or narrows the reachable
# region fails here instead of being discovered the next time someone trusts a
# green run.


def _synthetic_checkout(tmp_path, gamma_via_include_router=False):
    """A miniature tree with the two registry files and colliding modules."""
    reg = tmp_path / "autobot-backend" / "initialization" / "router_registry"
    api = tmp_path / "autobot-backend" / "api"
    reg.mkdir(parents=True)
    api.mkdir(parents=True)

    entries = ['("api.alpha", "/alpha", None)', '("api.beta", "", None)']
    if gamma_via_include_router:
        entries.append('("api.gamma", "", None)')
    (reg / "feature_routers.py").write_text(f"ROUTERS = [{', '.join(entries)}]\n", encoding="utf-8")
    # core_routers is read unconditionally; an empty one keeps the parse honest.
    (reg / "core_routers.py").write_text("CORE = []\n", encoding="utf-8")

    # /api + "/alpha" + "" + "/dup"
    (api / "alpha.py").write_text(
        'router = APIRouter()\n\n\n@router.get("/dup")\nasync def a():\n    return {}\n', encoding="utf-8"
    )
    # /api + "" + "/alpha" + "/dup" -- same full path, different module
    (api / "beta.py").write_text(
        'router = APIRouter(prefix="/alpha")\n\n\n@router.get("/dup")\nasync def b():\n    return {}\n',
        encoding="utf-8",
    )
    if gamma_via_include_router:
        # The same collision again, mounted the way the detector cannot see.
        (api / "gamma.py").write_text(
            'router = APIRouter()\nsub = APIRouter(prefix="/alpha")\n\n\n'
            '@sub.get("/dup")\nasync def c():\n    return {}\n\n\n'
            "router.include_router(sub)\n",
            encoding="utf-8",
        )
    return reg, api


def _collisions_against(monkeypatch, tmp_path, **kw):
    import repo_tests.no_duplicate_route_registration_16908_test as guard

    reg, api = _synthetic_checkout(tmp_path, **kw)
    monkeypatch.setattr(guard, "REG", reg)
    monkeypatch.setattr(guard, "API", api.parent)
    # `total > 500` is a real-tree sanity check; the synthetic tree has three routes.
    return guard.collisions()


def test_a_planted_duplicate_reddens_the_guard_and_names_both_modules(monkeypatch, tmp_path):
    """#16908 AC4, the positive half."""
    dupes, unresolved, total = _collisions_against(monkeypatch, tmp_path)

    assert not unresolved, f"the synthetic tree should resolve cleanly, got {unresolved}"
    assert (
        "GET",
        "/api/alpha/dup",
    ) in dupes, f"the planted duplicate was not detected; expansion produced {total} route(s): {dupes}"
    assert dupes[("GET", "/api/alpha/dup")] == [
        "api.alpha:router",
        "api.beta:router",
    ], "the failure must name BOTH sides -- naming one is how the wrong module gets edited"


def test_a_duplicate_mounted_through_include_router_is_missed(monkeypatch, tmp_path):
    """#16908 AC4, the half that proves the plant site mattered (#17325).

    `api.gamma` mounts exactly the same (GET, /api/alpha/dup) through
    include_router. The detector reads decorators on the REGISTERED object, so
    gamma contributes nothing and the three-way collision reports as two-way.
    This is the pinned blind spot, asserted as behaviour rather than described
    in a comment: when #17325 adopts real-router enumeration, this test is the
    one that must change, and it says so by failing.
    """
    dupes, unresolved, _ = _collisions_against(monkeypatch, tmp_path, gamma_via_include_router=True)

    assert not unresolved
    assert dupes[("GET", "/api/alpha/dup")] == [
        "api.alpha:router",
        "api.beta:router",
    ], "gamma's include_router-mounted duplicate should be invisible to the AST detector"
    assert "api.gamma:router" not in dupes[("GET", "/api/alpha/dup")]
