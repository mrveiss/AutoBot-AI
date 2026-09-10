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

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.router_auth_enumerator import (
    MIDDLEWARE_UNKNOWN,
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
        # The five confirmed by hand on #15745, with file:line evidence there.
        "api.developer",
        "api.knowledge_suggestions",
        "api.redis",
        "api.wake_word",
        "services.knowledge_sync_service",
        # Seven MORE the enumerator found that hand-inspection had not reached.
        # Two of them are the subjects of open issues, which is independent
        # corroboration rather than new information:
        #   api.transcriber          -- #15758 ("routes authenticate no one")
        #   api.user_management      -- #15738 ("no admin or ownership gate")
        # api.frontend_config is the #15737 legibility case: it documents nothing,
        # where api/chat_embed.py documents its open posture and is classified
        # UNGATED-BY-DESIGN on that basis.
        # api.user_provider_credentials handles provider credentials and wants
        # looking at first.
        "api.frontend_config",
        "api.knowledge_search",
        "api.knowledge_search_aggregator",
        "api.service_messages",
        "api.transcriber",
        "api.user_management.router",
        "api.user_provider_credentials",
    }
)

REACH = declare(
    "router-auth-coverage",
    discover=registered_routers,
    floor=80,
    what="routers registered in core_routers.py",
    growth=20,
)


def test_the_sweep_reaches_every_registered_router() -> None:
    """Non-vacuity, bound to routers EXAMINED rather than routers found wanting."""
    routers = REACH.examined(repo_root())
    REACH.completed(len(routers))
    assert len(routers) >= 80


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
        ("api.redis", "UNGATED", "genuinely nothing"),
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
