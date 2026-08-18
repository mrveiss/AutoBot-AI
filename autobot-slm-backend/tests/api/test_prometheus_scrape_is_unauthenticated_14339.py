# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The prometheus scrape route must not require authentication (#14339).

Prometheus reported the `slm` job `down` with `server returned HTTP status 401
Unauthorized`. The route sat on the performance router, which `main.py` mounts
with `dependencies=_SM`, and a scraper cannot authenticate — so the job had
never yielded a single sample and anything built on SLM performance metrics had
never had data to show. The only visible symptom was an empty panel, which looks
exactly like a quiet system.

The fix puts the scrape route on its own router mounted without that dependency,
matching what the backend already does for the same reason (#1288). The path is
unchanged, so a deployed scrape config needs no rewrite.

Both directions are asserted. Checking only that the metrics route is reachable
would stay green if someone dropped the dependency from the whole performance
router, which would expose every service-management endpoint on this service.

Two further bypasses of the registry this file enforces were found after the
above shipped, and are closed here rather than in a second, parallel check:

* A route added with `@app.get(...)`, `@app.post(...)`, or
  `app.add_api_route(...)` never passed through the `include_router` matcher,
  so it was neither gated nor declared — reachable and invisible at once
  (#14363). `_decorator_calls` and `_add_api_route_calls` extend the same
  matcher to these idioms.
* Binding another name to the app object before mounting through it —
  `application = app; application.include_router(...)` — read as a receiver
  that is not literally named `app` and was skipped as if it were an
  unrelated object (#14366). `_app_aliases` resolves simple, module-level
  aliases before any receiver is classified, for all three idioms.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from api import performance  # noqa: E402

_SCRAPE_PATH = "/performance/metrics/prometheus"
_MOUNTED_AT = "/api/performance/metrics/prometheus"

_HTTP_VERB_DECORATORS = {
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "options",
    "head",
    "trace",
    "websocket",
}


def _paths(router) -> set[str]:
    return {route.path for route in router.routes}


def test_the_scrape_route_lives_on_the_unauthenticated_router():
    assert _SCRAPE_PATH in _paths(performance.metrics_router)


def test_the_scrape_route_is_not_also_on_the_authenticated_router():
    """Registered twice, the authenticated copy could win and restore the 401."""
    assert _SCRAPE_PATH not in _paths(performance.router)


def test_the_authenticated_router_still_serves_everything_else():
    """The split must move one route, not empty the router.

    If the fix had moved more than the scrape surface, those endpoints would
    silently lose their auth — a far worse outcome than the bug being fixed.
    """
    remaining = _paths(performance.router)
    assert len(remaining) > 5, f"the authenticated performance router has only {remaining}"


def test_the_two_routers_share_a_prefix_so_the_path_is_unchanged():
    """The deployed scrape config points at the existing path.

    Changing it would mean the fix only takes effect after the monitoring role
    is also redeployed — two coupled deployments instead of one.
    """
    assert performance.metrics_router.prefix == performance.router.prefix


def _main_source() -> str:
    return (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")


def _main_tree() -> ast.Module:
    return ast.parse(_main_source())


def _app_aliases(tree: ast.Module) -> frozenset[str]:
    """Module-level names bound directly (transitively) to `app` (#14366).

    One pass over `tree.body` in source order: `x = app` followed later by
    `y = x` extends the known set, because `known` already contains `x` by
    the time the second assignment is read. Deliberately scoped to the
    module's *top-level* statements — an alias introduced inside a function
    body (a helper that takes the app as a parameter, a closure) is a
    different, open-ended problem that #14366 records as future work rather
    than one this pass closes.
    """
    known = {"app"}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not (isinstance(node.value, ast.Name) and node.value.id in known):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                known.add(target.id)
    known.discard("app")
    return frozenset(known)


def _is_app_receiver(receiver: ast.expr, aliases: frozenset[str] = frozenset()) -> bool:
    """Whether a call's receiver is the application object itself, or a known
    module-level alias of it (#14366).

    A named helper, not an inline condition, so the tests below can pin the
    decision rather than restate it. Restating it is how two tests here came
    to pass while the production branch they claimed to guard was deleted.
    """
    return isinstance(receiver, ast.Name) and (receiver.id == "app" or receiver.id in aliases)


def _receiver_kind(receiver: ast.expr, aliases: frozenset[str]) -> str:
    """Classify a call's receiver as `"app"`, `"skip"`, or `"unparseable"`.

    Shared by every matcher below so the fail-closed rule is defined once:
    `app` or a known alias resolves; a *different* bare name is a legitimately
    different object — a router mounting its own sub-router, a route
    decorator on some other router entirely — and is skipped; anything else
    (an attribute chain like `app.router`, a call result, a subscript) cannot
    be proven to miss the app, so it is reported rather than silently
    skipped. `app.router.include_router(...)` proved that an attribute chain
    can reach the app just as directly as a bare name.
    """
    if _is_app_receiver(receiver, aliases):
        return "app"
    if isinstance(receiver, ast.Name):
        return "skip"
    return "unparseable"


def _is_plain_name_arg(call: ast.Call) -> bool:
    """Whether the first argument is a bare router name this parser can read."""
    return bool(call.args) and isinstance(call.args[0], ast.Name)


def _record(calls: dict, unparseable: list, name: str, node, lineno: int) -> None:
    """Store a public-surface call, reporting a repeat rather than overwriting it.

    The three collectors keyed by name and the merge did `dict.update`, so two
    registrations of the same name collapsed and the LAST one won. That made an
    ungated registration invisible whenever the same name was also registered
    with the gate somewhere else — and FastAPI resolves first-match-wins, so the
    ungated one is the registration that actually serves.

    Demonstrated against the real file: mounting `errors_router` ungated before
    its existing gated mount left all 22 tests green while the ungated route was
    the live one.

    A repeat is reported rather than silently kept, because once a name maps to
    two calls this check cannot say which one it is answering about — the same
    reason an unreadable call fails instead of being skipped.
    """
    if name in calls:
        unparseable.append(f"line {lineno}: {name} registered more than once; this check cannot say which gates it")
        return
    calls[name] = node


def _app_mounts(tree: ast.Module | None = None) -> tuple[dict[str, ast.Call], list[str]]:
    """`app.include_router(...)` calls, split into readable and unreadable.

    Read structurally rather than executed: importing `main` works from a shell
    but not under pytest, where `api` resolves as a different namespace package
    and the import dies on an unrelated router. Parsing gets at the same wiring
    without depending on which of the two import environments is in play.

    This asserts on the shape of the call — which keywords it carries — not on
    the text of the line, so reformatting cannot make it pass or fail.

    Scope limit, stated because review demonstrated it: `ast.walk` finds the call
    wherever it sits, so wrapping the mount in a branch that never runs leaves
    these tests green. What is verified is that the wiring is *declared*
    correctly, not that it *executes*. The direction of that blind spot is
    "looks mounted but is not" — a 404, not an exposure — so it cannot hide a
    leak. Closing it means making `main` importable under pytest, which is a
    separate problem from this one.

    Two further gaps recorded here previously are now closed rather than
    open: a route added with `@app.get(...)` or `app.add_api_route(...)`
    instead of `include_router` is now caught by `_decorator_calls` and
    `_add_api_route_calls` (#14363), and a receiver reached through a
    module-level alias of `app` is now resolved by `_app_aliases` before
    `_receiver_kind` classifies it (#14366).
    """
    tree = tree if tree is not None else _main_tree()
    aliases = _app_aliases(tree)
    calls: dict[str, ast.Call] = {}
    unparseable: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "include_router":
            continue
        receiver = node.func.value
        kind = _receiver_kind(receiver, aliases)
        if kind == "skip":
            # Not `app` (or an alias of it). A plain name that resolves to
            # something else is a router-on-router include — a different
            # question, correctly skipped.
            continue
        if kind == "unparseable":
            unparseable.append(f"line {node.lineno}: receiver {ast.dump(receiver)[:70]}")
            continue
        if _is_plain_name_arg(node):
            _record(calls, unparseable, node.args[0].id, node, node.lineno)
        else:
            shape = ast.dump(node.args[0])[:80] if node.args else "no arguments"
            unparseable.append(f"line {node.lineno}: argument {shape}")
    return calls, unparseable


def _decorator_calls(tree: ast.Module, aliases: frozenset[str]) -> tuple[dict[str, ast.Call], list[str]]:
    """Every `@app.<verb>(...)` route decorator in `main.py` (#14363).

    Keyed by the decorated function's name — the identifier the registry
    block can name, the same way it names a router variable. Only recognised
    HTTP-verb attributes (`get`, `post`, ... `websocket`) are treated as
    route registration; other decorators on `app` (`exception_handler`,
    `on_event`, ...) are not routes and are correctly ignored. Among the
    recognised verbs, a receiver this parser cannot resolve to either `app`
    or a clearly different object is reported rather than skipped, matching
    `_app_mounts`'s fail-closed rule.
    """
    calls: dict[str, ast.Call] = {}
    unparseable: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if not (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)):
                continue
            if deco.func.attr not in _HTTP_VERB_DECORATORS:
                continue
            receiver = deco.func.value
            kind = _receiver_kind(receiver, aliases)
            if kind == "skip":
                continue
            if kind == "unparseable":
                unparseable.append(f"line {deco.lineno}: receiver {ast.dump(receiver)[:70]}")
                continue
            _record(calls, unparseable, node.name, deco, node.lineno)
    return calls, unparseable


def _endpoint_arg(call: ast.Call) -> ast.expr | None:
    """The `endpoint` argument of an `add_api_route(...)` call, positional or keyword."""
    if len(call.args) >= 2:
        return call.args[1]
    for kw in call.keywords:
        if kw.arg == "endpoint":
            return kw.value
    return None


def _add_api_route_calls(tree: ast.Module, aliases: frozenset[str]) -> tuple[dict[str, ast.Call], list[str]]:
    """Every `app.add_api_route(...)` call in `main.py` (#14363).

    Keyed by the endpoint callable's name when it is a bare function name;
    anything else — a lambda, an attribute, a call result — is unparseable
    rather than silently skipped, the same "cannot read this must not look
    like nothing here" rule `_app_mounts` already applies to router mounts.
    """
    calls: dict[str, ast.Call] = {}
    unparseable: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "add_api_route":
            continue
        receiver = node.func.value
        kind = _receiver_kind(receiver, aliases)
        if kind == "skip":
            continue
        if kind == "unparseable":
            unparseable.append(f"line {node.lineno}: receiver {ast.dump(receiver)[:70]}")
            continue
        endpoint = _endpoint_arg(node)
        if isinstance(endpoint, ast.Name):
            _record(calls, unparseable, endpoint.id, node, node.lineno)
        else:
            shape = ast.dump(endpoint)[:80] if endpoint is not None else "no endpoint argument"
            unparseable.append(f"line {node.lineno}: endpoint {shape}")
    return calls, unparseable


def _all_bypass_calls(tree: ast.Module | None = None) -> tuple[dict[str, ast.AST], list[str]]:
    """Every route-adding call in `main.py` that can make a route reachable
    from outside, across all three idioms the registry must see (#14363,
    #14366): `app.include_router(...)`, `@app.<verb>(...)`, and
    `app.add_api_route(...)`, each resolved through any module-level alias of
    `app`.

    Merged into one map rather than checked with three separate registry
    tests, because the registry answers a single question per name — is this
    declared? — regardless of which idiom put the name there. Extending the
    one gate, not adding a second one beside it.
    """
    tree = tree if tree is not None else _main_tree()
    aliases = _app_aliases(tree)
    router_calls, unparseable = _app_mounts(tree)
    decorator_calls, decorator_unparseable = _decorator_calls(tree, aliases)
    api_route_calls, api_route_unparseable = _add_api_route_calls(tree, aliases)

    calls: dict[str, ast.AST] = dict(router_calls)
    calls.update(decorator_calls)
    calls.update(api_route_calls)
    return calls, [*unparseable, *decorator_unparseable, *api_route_unparseable]


def _bypass_calls() -> dict[str, ast.AST]:
    """`_all_bypass_calls()` against the real `main.py`, asserting every call
    was readable.

    Mirrors `_mount_calls`'s contract for the merged surface: an unreadable
    call must fail the suite, not be silently dropped from what the registry
    checks.
    """
    calls, unparseable = _all_bypass_calls()
    assert not unparseable, (
        f"bypass-surface calls this check cannot read: {unparseable}. A shape it "
        "does not recognise used to be skipped in silence, which let an ungated "
        "route be invisible rather than flagged. Use a plain `app`/alias receiver "
        "and a bare endpoint name, or teach this parser the new shape (#14363, #14366)."
    )
    return calls


def _mount_calls() -> dict[str, ast.Call]:
    """`app.include_router(...)` calls, asserting every one was readable."""
    calls, unparseable = _app_mounts()
    assert not unparseable, (
        f"mount calls this check cannot read: {unparseable}. A shape it does not "
        "recognise used to be skipped in silence, which let an ungated router be "
        "invisible rather than flagged. Mount with a plain router name, or teach "
        "this parser the new shape (#14339)."
    )
    return calls


def _keywords(call: ast.Call) -> set[str]:
    return {kw.arg for kw in call.keywords if kw.arg}


def _is_declared(name: str, declared: str) -> bool:
    """Whether *name* appears in the registry block as a whole word.

    A function rather than an inline expression so a test can pin the decision
    itself. Inline, reverting this to a substring check went undetected: the
    whole-word test asserted the technique on its own synthetic string and never
    touched the line that actually decides.
    """
    return bool(re.search(rf"\b{re.escape(name)}\b", declared))


_REGISTRY_OPENS = "# Routers intentionally left open"
_REGISTRY_CLOSES = "# Service-management gate"


def _registry_block() -> str:
    """The text between the registry's two markers.

    Both markers are required. Review found the first version took
    ``split(closing, 1)[0]``, and ``str.split`` on a separator it cannot find
    returns a single element — so a reworded closing comment silently made the
    block *the rest of the file*, which contains every router's own name in its
    own mount call. Every router then read as declared and the check passed over
    all of them.

    That is the same shape as the bug being guarded: something stops matching,
    and the result is indistinguishable from having nothing to report. So a
    missing marker is an error here, never an empty block.
    """
    source = _main_source()
    assert source.count(_REGISTRY_OPENS) == 1, f"expected exactly one {_REGISTRY_OPENS!r} marker in main.py"
    assert source.count(_REGISTRY_CLOSES) == 1, (
        f"the registry's closing marker {_REGISTRY_CLOSES!r} is missing from main.py. "
        "Without it this check cannot tell where the declarations end, and would "
        "treat the rest of the file as declarations (#14339)."
    )
    return source.split(_REGISTRY_OPENS, 1)[1].split(_REGISTRY_CLOSES, 1)[0]


def test_the_app_mounts_the_scrape_router_without_auth_and_the_rest_with_it():
    """The mount is where the defect lived — the route was always fine, the
    router-level dependency it inherited was not."""
    calls = _mount_calls()
    assert "performance_metrics_router" in calls, "the scrape router is never mounted on the app"
    assert "performance_router" in calls, "the authenticated performance router is not mounted"

    assert "dependencies" not in _keywords(calls["performance_metrics_router"]), (
        "the scrape router is mounted with a router-level dependency; prometheus "
        "cannot authenticate and every scrape will 401 again (#14339)"
    )
    assert "dependencies" in _keywords(
        calls["performance_router"]
    ), "the authenticated performance router lost its service-management dependency"


def test_the_scrape_router_is_mounted_under_the_same_prefix(tmp_path):
    """A different mount prefix moves the endpoint out from under the deployed
    scrape config, and every other assertion here would still pass."""
    calls = _mount_calls()

    def prefix_of(name: str) -> str | None:
        for kw in calls[name].keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                return kw.value.value
        return None

    assert prefix_of("performance_metrics_router") == prefix_of("performance_router") == "/api"


def test_the_mounted_path_is_the_one_prometheus_scrapes():
    """Guard the guard: the route path already carries the router's own prefix,
    so only the app-level mount prefix is added to reach the scraped URL."""
    assert f"/api{_SCRAPE_PATH}" == _MOUNTED_AT


def test_every_ungated_router_is_named_in_the_registry():
    """`main.py` keeps a list of surfaces deliberately mounted without the gate.

    Nothing enforced it, and it had already gone stale before this change — a
    public surface that is not in the one inventory the file maintains is a
    public surface nobody reviewing auth will see. So the list is checked here
    rather than trusted: mount a router without `dependencies`, or add a route
    with `@app.get(...)`/`app.add_api_route(...)` (directly or through an
    alias of `app`) without `dependencies`, and this fails until it is
    declared, which makes adding public surface a visible act regardless of
    which of the three idioms did it (#14363, #14366).

    Deliberately keyed on the mount/route, not on the comment. A name can be
    removed from the list and the test still fails, because the call is what
    decides who can reach the route.
    """
    declared = _registry_block()

    ungated = {name for name, call in _bypass_calls().items() if "dependencies" not in _keywords(call)}
    undeclared = sorted(name for name in ungated if not _is_declared(name, declared))
    assert not undeclared, (
        f"reachable without the service-management gate but not declared in the registry: "
        f"{undeclared}. Add each with the reason it must be reachable unauthenticated, "
        f"or mount/decorate it with `dependencies=_SM` (#14339, #14363, #14366)."
    )


def _code_lines(block: str) -> str:
    """*block* with comment-only lines removed, leaving only executable code.

    A comment line is allowed to *name* `include_router` in prose — the
    explanatory text in this very block does exactly that, describing what
    the check used to miss — without tripping the "has this block swallowed
    real code" guard below. Only a line that is not a comment can contain an
    actual mount call, so stripping comments first measures code, not prose.
    The registry block is legitimately all comments, so on the real file this
    reduces to the empty string; an over-run block would still carry real
    `app.include_router(...)` statements, which are not comment lines and
    survive the strip.
    """
    return "\n".join(line for line in block.splitlines() if not line.strip().startswith("#"))


def test_the_registry_block_is_bounded_at_both_ends():
    """The block must not run past its closing marker.

    Review demonstrated the fail-open: with the closing marker reworded, the
    block became the rest of the file, every router matched its own mount line,
    and an undeclared ungated router passed unnoticed. Sized rather than merely
    non-empty, because "the rest of the file" is also non-empty.

    The substring check below is deliberately run against comment-stripped
    text, not the raw block. A prior version matched the raw block, which
    means an explanatory comment that *names* `include_router` while
    describing what it guards against would trip the guard it is standing
    next to — reworded here after review demonstrated exactly that (#14363).
    """
    block = _registry_block()
    source = _main_source()
    assert block.strip(), "the registry block is empty"
    assert len(block) < len(source) / 4, (
        f"the registry block is {len(block)} chars of a {len(source)}-char file — "
        "it has run past its closing marker and would declare everything (#14339)"
    )
    assert "include_router" not in _code_lines(block), (
        "the registry block contains mount calls, so it has swallowed code rather "
        "than stopping at the comment that ends it"
    )


def test_a_name_is_declared_only_as_a_whole_word():
    """A router must not be declared by a longer neighbour containing its name.

    Asserted against synthetic text, not the live registry. An earlier version
    used the real block and was decorative: `auth_router` is declared there on
    its own line *as well as* being a substring of `sso_auth_router`, so it
    matched under both the buggy and the fixed logic. Review proved it by
    reinstating the substring bug and watching this test stay green.

    So the input here contains the name ONLY as a substring — the one condition
    under which the two behaviours differ. Seven such collisions exist among the
    real router names in this file (`services_router` inside
    `fleet_services_router`, `agents_router` inside `external_agents_router`,
    and five more), so it is the shape a future router would hit.
    """
    declared = "#   sso_auth_router - OAuth callback; must complete before a token exists"

    assert "auth_router" in declared, "the substring collision this guards against is real"
    assert not _is_declared(
        "auth_router", declared
    ), "a name present only inside a longer neighbour must not count as declared"
    assert _is_declared("sso_auth_router", declared), "the neighbour itself is still declared"


def test_an_unreadable_mount_is_a_failure_not_a_skip():
    """The parser must not treat "I cannot read this" as "there is nothing here".

    Review demonstrated two working exploits against the earlier version, both
    ordinary FastAPI idioms: `app.include_router(*routers)` and
    `app.include_router(module.router)`. Neither has a bare name as its first
    argument, so both were skipped in silence, leaving a genuinely ungated,
    undeclared router reachable with every test green.
    """
    calls, unparseable = _app_mounts()
    assert not unparseable, f"main.py has mounts this check cannot read: {unparseable}"
    assert calls, "no app-level mounts found at all - the matcher is broken"

    for source in ("app.include_router(*routers, prefix='/api')", "app.include_router(module.router, prefix='/x')"):
        node = ast.parse(source).body[0].value
        assert not _is_plain_name_arg(
            node
        ), f"{source!r} would be read as a plain named mount instead of flagged as unreadable"


def test_only_app_level_mounts_are_checked():
    """A router included on another router is a different question.

    The registry answers which surfaces are reachable from outside, and that is
    decided by the `app` mounts. Matching every receiver made an inner include
    look ungated even when the outer app mount gated it.
    """
    empty_aliases: frozenset[str] = frozenset()
    assert _receiver_kind(ast.parse("sub_router.include_router(x)").body[0].value.func.value, empty_aliases) == "skip"
    assert _receiver_kind(ast.parse("app.include_router(x)").body[0].value.func.value, empty_aliases) == "app"
    # `app.router.include_router(...)` reaches the app just as directly, and is
    # NOT a plain `app` receiver — so it must be reported, never skipped.
    assert (
        _receiver_kind(ast.parse("app.router.include_router(x)").body[0].value.func.value, empty_aliases)
        == "unparseable"
    )


def test_the_registry_check_actually_sees_the_ungated_mounts():
    """An empty `ungated` set would make the assertion above vacuous.

    If the mount matcher stopped matching — a rename, a different idiom — every
    router would look gated and the registry check would pass over all of them.
    """
    ungated = {name for name, call in _bypass_calls().items() if "dependencies" not in _keywords(call)}
    assert "performance_metrics_router" in ungated
    assert "root" in ungated, "the @app.get('/') banner route is not seen as an ungated bypass"
    assert "prometheus_registry_metrics" in ungated, "the @app.get('/metrics') route is not seen as an ungated bypass"
    assert len(ungated) >= 5, f"only {len(ungated)} ungated mounts found — the matcher is broken"


def test_a_bare_app_get_route_is_caught_as_an_ungated_bypass():
    """The concrete exploit demonstrated in #14363.

    Inserting this into `main.py` used to leave all 13 registry tests green
    while the route was reachable with no authentication::

        @app.get("/api/services/sneaky-list")
        async def sneaky_list():
            return {"leaked": "everything"}

    It must now be found by the same matcher an `include_router` mount goes
    through, and land in the ungated set because it carries no `dependencies`.
    """
    tree = ast.parse(
        "@app.get('/api/services/sneaky-list')\n" "async def sneaky_list():\n" "    return {'leaked': 'everything'}\n"
    )
    calls, unparseable = _decorator_calls(tree, frozenset())
    assert not unparseable
    assert "sneaky_list" in calls, "a bare @app.get(...) route was not caught by the decorator matcher"
    assert "dependencies" not in _keywords(calls["sneaky_list"])


def test_a_gated_app_get_route_is_still_found_but_not_flagged_ungated():
    """A route added this way with an explicit `dependencies=` is a legitimate
    use of the idiom and must not be forced into the registry text — only the
    ungated case should demand a declaration."""
    tree = ast.parse("@app.get('/api/services/reports', dependencies=_SM)\n" "async def reports():\n" "    return {}\n")
    calls, unparseable = _decorator_calls(tree, frozenset())
    assert not unparseable
    assert "reports" in calls
    assert "dependencies" in _keywords(calls["reports"])


def test_an_add_api_route_call_is_caught_as_an_ungated_bypass():
    """`app.add_api_route(...)` is the third idiom named in #14363 — a call
    rather than a decorator, but reaching the app exactly as directly."""
    tree = ast.parse("def sneaky():\n" "    return {}\n" "\n" "app.add_api_route('/api/services/sneaky2', sneaky)\n")
    calls, unparseable = _add_api_route_calls(tree, frozenset())
    assert not unparseable
    assert "sneaky" in calls, "app.add_api_route(...) was not caught"
    assert "dependencies" not in _keywords(calls["sneaky"])


def test_an_alias_of_app_is_resolved_before_receiver_matching():
    """The concrete exploit demonstrated in #14366.

    ``application = app`` followed by ``application.include_router(...)``
    used to read as a receiver that is not literally named ``app`` and was
    skipped exactly like a genuinely different router object — leaving a
    mounted, ungated, undeclared router unreachable by this check.
    """
    tree = ast.parse("application = app\napplication.include_router(some_router, prefix='/x')\n")
    aliases = _app_aliases(tree)
    assert "application" in aliases, "a direct alias of app was not resolved"

    calls, unparseable = _app_mounts(tree)
    assert not unparseable
    assert "some_router" in calls, "a router mounted through an alias of app was not caught"


def test_an_alias_extends_transitively_within_the_module():
    """`y = x` after `x = app` is still a module-level alias of `app`.

    Bounded to a single forward pass over `tree.body`, matching what
    `_app_aliases` documents: only names that resolve back to `app` through
    other module-level assignments are treated as aliases.
    """
    tree = ast.parse("x = app\ny = x\ny.include_router(some_router)\n")
    aliases = _app_aliases(tree)
    assert {"x", "y"} <= aliases

    calls, unparseable = _app_mounts(tree)
    assert not unparseable
    assert "some_router" in calls


def test_a_name_that_is_never_assigned_from_app_is_not_treated_as_an_alias():
    """The alias resolution must not swallow ordinary router-on-router includes.

    `sub_router` is never assigned from `app` anywhere in this snippet, so it
    must still read as a legitimately different object, not a bypass.
    """
    tree = ast.parse("sub_router.include_router(x)\n")
    aliases = _app_aliases(tree)
    assert "sub_router" not in aliases

    calls, unparseable = _app_mounts(tree)
    assert not calls
    assert not unparseable


def test_a_decorator_reached_through_an_ambiguous_receiver_fails_closed():
    """`@app.router.get(...)` reaches the app just as directly as
    `app.router.include_router(...)` already does. It must be reported as
    unreadable, never silently skipped as "some other object's decorator".
    """
    tree = ast.parse("@app.router.get('/api/sneaky3')\nasync def sneaky3():\n    return {}\n")
    calls, unparseable = _decorator_calls(tree, frozenset())
    assert not calls, "an ambiguous receiver must not be classified as a clean mount"
    assert unparseable, "an ambiguous receiver was silently skipped instead of failing closed"


def test_the_two_declared_app_get_routes_in_main_are_found_by_the_combined_matcher():
    """Guard the guard: `main.py` really does carry `root` and
    `prometheus_registry_metrics` as `@app.get(...)` routes, so the registry
    test above is exercising the real file, not a matcher that has stopped
    matching anything.
    """
    calls = _bypass_calls()
    assert "root" in calls
    assert "prometheus_registry_metrics" in calls


def test_the_registry_check_sees_the_root_and_metrics_routes_as_app_get_calls():
    """Pin the shape: both are decorator-based, not `add_api_route` or
    `include_router` — if the idiom in `main.py` ever changes, this documents
    what changed."""
    tree = _main_tree()
    aliases = _app_aliases(tree)
    decorator_calls, unparseable = _decorator_calls(tree, aliases)
    assert not unparseable
    assert "root" in decorator_calls
    assert "prometheus_registry_metrics" in decorator_calls


def test_a_repeat_registration_cannot_hide_an_ungated_one():
    """Two registrations of one name must fail, not collapse to the last.

    The collectors keyed by name and the merge did `dict.update`, so an ungated
    registration was masked whenever the same name was also registered with the
    gate elsewhere. FastAPI resolves first-match-wins, so the masked one is the
    registration that actually serves — the check reported clean about a route
    it was not looking at.

    Asserted against synthetic source: the real `main.py` registers no name
    twice, so a test built on it could only ever prove the happy path.
    """
    tree = ast.parse(
        "app = FastAPI()\n"
        'app.include_router(widgets_router, prefix="/evil")\n'
        'app.include_router(widgets_router, prefix="/api", dependencies=_SM)\n'
    )
    calls, unparseable = _all_bypass_calls(tree)
    assert unparseable, "a name registered twice was collapsed instead of reported"
    assert any("widgets_router" in item for item in unparseable)


def test_the_repeat_check_does_not_fire_on_distinct_names():
    """Guard the guard: if it flagged every registration, the suite would be
    red for the real file and the assertion above would prove nothing."""
    tree = ast.parse(
        "app = FastAPI()\n"
        'app.include_router(alpha_router, prefix="/a", dependencies=_SM)\n'
        'app.include_router(beta_router, prefix="/b", dependencies=_SM)\n'
    )
    calls, unparseable = _all_bypass_calls(tree)
    assert not unparseable, f"distinct names were reported as repeats: {unparseable}"
    assert set(calls) == {"alpha_router", "beta_router"}
