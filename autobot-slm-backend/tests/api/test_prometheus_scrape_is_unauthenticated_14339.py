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


def _mount_calls() -> dict[str, ast.Call]:
    """Every `app.include_router(<name>, ...)` in main.py, keyed by router name.

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
    """
    calls, unparseable = _app_mounts()
    assert not unparseable, (
        f"mount calls this check cannot read: {unparseable}. A shape it does not "
        "recognise used to be skipped in silence, which let an ungated router be "
        "invisible rather than flagged. Mount with a plain router name, or teach "
        "this parser the new shape (#14339)."
    )
    return calls


def _app_mounts() -> tuple[dict[str, ast.Call], list[str]]:
    """`app.include_router(...)` calls, split into readable and unreadable.

    Two things this deliberately does NOT do, both fail-open holes review
    demonstrated with working exploits:

    * It no longer matches any receiver. Only `app` mounts decide what is
      reachable from outside; a router-on-router include is a different question.
    * It no longer skips a call whose first argument is not a plain name.
      `app.include_router(*routers)` and `app.include_router(module.router)` are
      ordinary FastAPI idioms, and each left a genuinely ungated, undeclared
      router reachable while every test here stayed green. An unreadable mount is
      now returned for the caller to fail on, because "I could not parse this"
      and "there is nothing here" must not look the same.
    """
    tree = ast.parse((Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8"))
    calls: dict[str, ast.Call] = {}
    unparseable: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "include_router":
            continue
        receiver = node.func.value
        if not _is_app_receiver(receiver):
            # Not `app.include_router(...)`. A plain name that is not `app` is a
            # router-on-router include — a different question, correctly skipped.
            # Anything else is a receiver this parser cannot resolve, and
            # `app.router.include_router(...)` proved that reaches the app just
            # as directly, so it is reported rather than skipped.
            if not isinstance(receiver, ast.Name):
                unparseable.append(f"line {node.lineno}: receiver {ast.dump(receiver)[:70]}")
            continue
        if _is_plain_name_arg(node):
            calls[node.args[0].id] = node
        else:
            shape = ast.dump(node.args[0])[:80] if node.args else "no arguments"
            unparseable.append(f"line {node.lineno}: argument {shape}")
    return calls, unparseable


def _is_app_receiver(receiver: ast.expr) -> bool:
    """Whether a call's receiver is the application object itself.

    A named helper, not an inline condition, so the tests below can pin the
    decision rather than restate it. Restating it is how two tests here came to
    pass while the production branch they claimed to guard was deleted.
    """
    return isinstance(receiver, ast.Name) and receiver.id == "app"


def _is_plain_name_arg(call: ast.Call) -> bool:
    """Whether the first argument is a bare router name this parser can read."""
    return bool(call.args) and isinstance(call.args[0], ast.Name)


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
    source = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")
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
    """`main.py` keeps a list of routers deliberately mounted without the gate.

    Nothing enforced it, and it had already gone stale before this change — a
    public surface that is not in the one inventory the file maintains is a
    public surface nobody reviewing auth will see. So the list is checked here
    rather than trusted: mount a router without `dependencies` and this fails
    until it is declared, which makes adding public surface a visible act.

    Deliberately keyed on the mount, not on the comment. A name can be removed
    from the list and the test still fails, because the mount is what decides
    who can reach the route.
    """
    declared = _registry_block()

    ungated = {name for name, call in _mount_calls().items() if "dependencies" not in _keywords(call)}
    undeclared = sorted(name for name in ungated if not _is_declared(name, declared))
    assert not undeclared, (
        f"mounted without the service-management gate but not declared in the registry: "
        f"{undeclared}. Add each with the reason it must be reachable unauthenticated, "
        f"or mount it with `dependencies=_SM` (#14339)."
    )


def test_the_registry_block_is_bounded_at_both_ends():
    """The block must not run past its closing marker.

    Review demonstrated the fail-open: with the closing marker reworded, the
    block became the rest of the file, every router matched its own mount line,
    and an undeclared ungated router passed unnoticed. Sized rather than merely
    non-empty, because "the rest of the file" is also non-empty.
    """
    block = _registry_block()
    source = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")
    assert block.strip(), "the registry block is empty"
    assert len(block) < len(source) / 4, (
        f"the registry block is {len(block)} chars of a {len(source)}-char file — "
        "it has run past its closing marker and would declare everything (#14339)"
    )
    assert "include_router" not in block, (
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
    assert not _is_app_receiver(ast.parse("sub_router.include_router(x)").body[0].value.func.value)
    assert _is_app_receiver(ast.parse("app.include_router(x)").body[0].value.func.value)
    # `app.router.include_router(...)` reaches the app just as directly, and is
    # NOT a plain `app` receiver — so it must be reported, never skipped.
    assert not _is_app_receiver(ast.parse("app.router.include_router(x)").body[0].value.func.value)


def test_the_registry_check_actually_sees_the_ungated_mounts():
    """An empty `ungated` set would make the assertion above vacuous.

    If the mount matcher stopped matching — a rename, a different idiom — every
    router would look gated and the registry check would pass over all of them.
    """
    ungated = {name for name, call in _mount_calls().items() if "dependencies" not in _keywords(call)}
    assert "performance_metrics_router" in ungated
    assert len(ungated) >= 3, f"only {len(ungated)} ungated mounts found — the matcher is broken"
