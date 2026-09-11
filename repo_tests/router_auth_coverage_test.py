# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every registered router is gated, or its openness is documented (#15745).

Two prior sweeps reported 30 ungated routers, then 15, then fewer -- each
internally consistent, each wrong, always in the same direction. The cause was
that this codebase gates FOUR ways and each detector modelled fewer than exist.

The controls below are therefore **one per mechanism**, not one per direction.
A gated and an ungated control both passed on a sweep that was wrong, because
both were shapes its regex already matched: a control drawn from the detector's
own model tests the model against itself.
"""

from __future__ import annotations

import ast

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.router_auth_enumerator import (
    MIDDLEWARE_UNKNOWN,
    _defines_routes,
    _included_modules,
    auth_vocabulary,
    enumerate_routers,
    registered_routers,
)

#: Routers with no gate of any detectable kind, frozen so a NEW one fails.
#: May only SHRINK. Each entry is a real finding on #15745, not an exemption --
#: they are recorded here so the guard can be turned on before the fixes land,
#: rather than the fixes waiting on a guard that does not exist yet.
KNOWN_UNGATED: frozenset[str] = frozenset(
    {
        "api.frontend_config",
        "api.knowledge_search",
        "api.knowledge_search_aggregator",
        "api.knowledge_suggestions",
        "api.transcriber",
    }
)

#: TWO ENTRIES WERE REMOVED FROM THIS LIST AS FALSE FINDINGS, and how they got
#: here matters more than that they left.
#:
#: `api.service_messages` gates all three routes with `Depends(_check_admin)`, a
#: check DEFINED IN THAT FILE. `api.user_provider_credentials` gates all three
#: with `Depends(get_current_user_id)`, imported from
#: `api.user_management.dependencies` -- a path containing none of
#: auth/security/permission/rbac.
#:
#: Both were reported UNGATED because the vocabulary was derived from the IMPORT
#: PATH rather than from whether the name performs a check. That is the same
#: defect as the hand-written regex missing `check_admin_permission`, in a new
#: spelling -- and it was published as a finding against a credentials surface
#: before review caught it. One-hop resolution now reaches both.

REACH = declare(
    "router-auth-coverage",
    discover=registered_routers,
    floor=90,
    what="routers registered in core_routers.py",
    growth=20,
)


def test_the_sweep_reaches_every_registered_router() -> None:
    """Non-vacuity, bound to routers EXAMINED rather than routers found wanting."""
    routers = REACH.examined(repo_root())
    REACH.completed(len(routers))
    assert len(routers) >= 90


def test_the_vocabulary_is_derived_and_contains_the_name_that_was_missed() -> None:
    """`check_admin_permission` is the most-used auth dependency in the backend.

    A hand-written regex omitted it, and that single omission produced fifteen
    false findings. This asserts the DERIVED vocabulary contains it -- if the
    derivation ever narrows, the sweep silently starts reporting gated routers
    as holes again.
    """
    vocabulary = auth_vocabulary(repo_root())
    for required in ("check_admin_permission", "get_current_user", "enforce_ws_origin"):
        assert required in vocabulary, f"the derivation lost {required!r} -- the sweep is now narrower than the tree"


@pytest.mark.parametrize(
    ("module", "expected", "mechanism"),
    [
        ("api.agent_org", "GATED", "router-level APIRouter(dependencies=[...])"),
        ("api.system", "GATED", "per-route check_admin_permission"),
        ("api.websockets", "GATED", "inline in the handler body"),
        ("api.knowledge_search", "UNGATED", "genuinely nothing"),
        ("api.chat_embed", "UNGATED-BY-DESIGN", "documented in the module docstring"),
    ],
)
def test_one_control_per_gating_mechanism(module: str, expected: str, mechanism: str) -> None:
    """If a control's verdict changes, the DETECTOR broke -- not the tree.

    Each row is a different mechanism. Two controls of the same shape cannot
    tell you the detector covers a shape it has never seen.
    """
    verdicts = {v.module: v for v in enumerate_routers(repo_root())}
    verdict = verdicts.get(module)
    assert verdict is not None, f"{module} is no longer registered -- update the control, do not delete it"

    actual = "GATED" if verdict.gated else ("UNGATED-BY-DESIGN" if verdict.intentional else "UNGATED")
    assert actual == expected, (
        f"{module} ({mechanism}) is {actual}, expected {expected}. "
        f"Evidence: {'; '.join(verdict.evidence) or 'none'}"
    )


def test_no_new_router_is_ungated_and_undocumented() -> None:
    """The constraint.

    A router that is neither gated nor documented as open is a hole. Reported
    with its module path so a reader can check any single row -- three counts
    that disagree are worth less than one table.
    """
    ungated = {
        v.module for v in enumerate_routers(repo_root()) if not v.gated and not v.intentional and not v.unreadable
    }
    new = sorted(ungated - KNOWN_UNGATED)
    assert not new, (
        "router(s) with no auth gate of any kind and no documented open posture:\n  "
        + "\n  ".join(new)
        + "\n\nGate it, or document the open posture IN THE FILE. Note this sweep does not "
        "model middleware, so 'ungated' means 'not gated by router-level, per-route or "
        "inline' -- confirm reachability by hand before treating it as exploitable."
    )


def test_the_known_ungated_list_has_not_gone_stale() -> None:
    """The other direction, and the one normally forgotten.

    An entry that is now gated means someone fixed it and did not record it, and
    a list carrying dead entries silently permits the next hole to be added.
    """
    ungated = {
        v.module for v in enumerate_routers(repo_root()) if not v.gated and not v.intentional and not v.unreadable
    }
    fixed = sorted(KNOWN_UNGATED - ungated)
    assert (
        not fixed
    ), "KNOWN_UNGATED entries that now have a gate -- remove them, the list only shrinks:\n  " + "\n  ".join(fixed)


def test_the_middleware_gap_is_declared_rather_than_implied() -> None:
    """This sweep cannot see mechanism 4, and must say so.

    `initialization/middleware.py` assumes `request.state.user` is already
    populated upstream, and #15758 found there is no upstream for at least some
    routes. So middleware may cover nothing, something, or everything -- and a
    guard that quietly modelled three of four mechanisms would report a
    confident number about a question it cannot answer.
    """
    assert MIDDLEWARE_UNKNOWN is True, (
        "middleware coverage is now modelled -- update this test and the module docstring, "
        "and re-verify every control, because the meaning of UNGATED has changed"
    )


def test_every_registered_router_resolves_to_a_module_on_disk() -> None:
    """A registry entry pointing at nothing is not a gated router.

    `api.redis_mcp` is imported by the registry and has no module on disk. It
    cannot be classified either way, so it must not sit silently in the
    unreadable bucket looking like it was examined -- an unreadable router is an
    unanswered question, and this file's whole purpose is to stop those from
    reading as answers.
    """
    unreadable = {v.module: v.unreadable for v in enumerate_routers(repo_root()) if v.unreadable}
    known = {"api.redis_mcp"}
    new = sorted(set(unreadable) - known)
    assert not new, "registered router(s) whose module cannot be read:\n  " + "\n  ".join(
        f"{m}: {unreadable[m]}" for m in new
    )


def test_a_gated_file_cannot_hide_behind_an_incidental_public_marker() -> None:
    """`intentional` is FILE-scoped; gating is ROUTE-scoped (#15745 review).

    `api/system.py` carries both properties at once: one genuinely public health
    check documented as such, and the rest of the file gated by
    `check_admin_permission`. Because `intentional` is computed over the whole
    source independently of `gated`, a file like that would flip straight to
    UNGATED-BY-DESIGN if its real gates ever regressed -- never to UNGATED, so
    `test_no_new_router_is_ungated_and_undocumented` would pass silently.

    This pins the pair that makes that reachable, so the structural mismatch is
    recorded against a real file rather than described in a comment. Making the
    marker route-scoped is the fuller fix and is NOT this change.
    """
    verdicts = {v.module: v for v in enumerate_routers(repo_root())}
    system = verdicts.get("api.system")
    assert system is not None, "api.system is no longer registered -- update this test"

    assert system.gated and system.intentional, (
        "api/system.py no longer carries both a public marker and real gates. If its "
        "gates were removed, this guard would report UNGATED-BY-DESIGN rather than "
        "UNGATED and pass silently -- which is the hole this test exists to record."
    )


def test_gated_does_not_claim_identity_verification() -> None:
    """GATED means "a gate runs", NOT "the caller was identified" (#15745 AC3).

    `api/voice_stream` checks WS ORIGIN; `api/websockets` authenticates the USER.
    Both report GATED, because this sweep has no notion of origin-check versus
    identity-check. AC3 is exactly about that inconsistency, so a reader using
    this table to judge AC3 would be misled by its own output.

    Asserted rather than documented, so the day someone teaches the model to tell
    them apart, this test fails and forces the docstring and the PR claim to be
    updated with it.
    """
    verdicts = {v.module: v for v in enumerate_routers(repo_root())}
    for module in ("api.voice_stream", "api.websockets"):
        verdict = verdicts.get(module)
        if verdict is None:
            continue
        assert verdict.gated, f"{module} lost its gate"

    origin_only = verdicts.get("api.voice_stream")
    identity = verdicts.get("api.websockets")
    if origin_only and identity:
        assert "enforce_ws_origin" in "; ".join(origin_only.evidence), (
            "api.voice_stream's evidence no longer names an origin check -- the AC3 "
            "distinction may now be modelled; if so, update this test and the docstring"
        )


def test_an_aggregator_is_judged_by_what_it_mounts() -> None:
    """A router that defines no routes must not be reported UNGATED (#16187).

    `api/user_management/router.py` is 24 lines that mount four sub-routers and
    declare nothing of their own. Reading it alone finds no gates -- correctly,
    since there is nothing there to gate -- and the sweep reported UNGATED for a
    module with zero routes.

    That is the fourth distinct way a gate escaped this sweep, and the only one
    where the verdict was about the wrong FILE rather than the wrong depth.
    """
    verdicts = {v.module: v for v in enumerate_routers(repo_root())}
    aggregator = verdicts.get("api.user_management.router")
    assert aggregator is not None, "api.user_management.router is no longer registered"

    assert aggregator.gated, (
        "the aggregator reports ungated. Its four mounted routers "
        "(users, teams, organizations, password_change) each gate on "
        "Depends(get_user_service) -> get_tenant_context -> get_current_user."
    )
    assert any(
        "aggregator" in e for e in aggregator.evidence
    ), f"evidence should name the mounted routers, got: {aggregator.evidence}"


def test_mounting_and_defining_routes_are_asked_separately() -> None:
    """ "No gate found here" was standing in for "defines no routes" (#16189 review).

    The aggregator branch used to trigger on `not _per_route and not _router_level`.
    That is a question about GATES, used to answer a question about ROUTES, and the
    two come apart in both directions:

    * mounts + its own UNGATED route -> looked like a pure aggregator, got judged by
      what it mounts, and reported GATED with its own route standing open. False
      GATED is the direction that hides a hole.
    * mounts + its own GATED route -> skipped the aggregator branch entirely and the
      mounted set was computed and discarded, so a sub-router reachable ONLY through
      the mount became invisible to the sweep.

    Asserted on parsed source rather than on a live module: the tree happens to
    contain no mixed module today, and a guard that can only fail once one appears
    is a guard that reports clean about a case it never examined.
    """
    mounts_only = ast.parse(
        "from api.user_management.users import router as users_router\n"
        "router = APIRouter()\n"
        "router.include_router(users_router)\n"
    )
    mounts_and_defines = ast.parse(
        "from api.user_management.users import router as users_router\n"
        "router = APIRouter()\n"
        "router.include_router(users_router)\n"
        "@router.get('/health')\n"
        "async def health():\n"
        "    return {}\n"
    )

    assert not _defines_routes(mounts_only), "a pure aggregator must not read as defining routes"
    assert _defines_routes(mounts_and_defines), (
        "a module that mounts AND registers its own route must be distinguishable "
        "from a pure aggregator -- otherwise its own route is never classified"
    )
    assert _included_modules(mounts_and_defines), "the mounted set must survive the mixed case"


def test_a_dict_read_is_not_a_route() -> None:
    """`.get` registers a route as a DECORATOR and reads a dict everywhere else.

    A route detector that scans calls rather than decorator position reports routes
    in every file that reads a dictionary -- which would make `_defines_routes` true
    almost everywhere and silently disable the aggregator branch it gates.
    """
    reads_a_dict = ast.parse("config = {}\nvalue = config.get('key')\nrows = payload.get('items', [])\n")
    assert not _defines_routes(reads_a_dict), "a dict read must not be counted as a route registration"

    adds_explicitly = ast.parse("router.add_api_route('/x', handler)\n")
    assert _defines_routes(adds_explicitly), "an explicit add_api_route call registers a route"


def test_the_resolution_depth_is_declared_not_merely_chosen() -> None:
    """An UNGATED verdict is a claim about the SWEEP's reach, not about the tree.

    Four misses, each because a gate sat further away than the resolver reached:
    locally defined (0 hops), non-auth import path (1), service chain (2),
    aggregator (a different file entirely). Raising the number each time treats
    the symptom; the number being VISIBLE is what stops the next reader mistaking
    "not gated within N hops" for "not gated".
    """
    from repo_tests.router_auth_enumerator import MAX_DEPENDENCY_HOPS

    assert MAX_DEPENDENCY_HOPS >= 3, "the measured chain needs 2 hops; 3 leaves one spare"
    source = (repo_root() / "repo_tests" / "router_auth_enumerator.py").read_text(encoding="utf-8")
    assert "MAX_DEPENDENCY_HOPS" in source.split('"""')[1], (
        "the module docstring must state the depth limit -- a reach nobody can read "
        "is the defect this module exists to detect"
    )
