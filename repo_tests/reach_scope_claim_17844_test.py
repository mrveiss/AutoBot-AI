# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A declaration's claimed population must match the one its discovery reaches (#17844).

`floor` is a number the framework verifies. `what=` was free text nobody verified, and both sit
in the same `declare()` call. That leaves a third coverage state nothing could see:

| state | caught by |
|---|---|
| no floor at all | `guard_reach_meta_test.test_no_new_tree_scanning_guard_lacks_a_floor` |
| floored below its reach | the floor assertion itself |
| floored correctly, over the WRONG population | nothing, until this |

Measured on #17844's base: 52 `what=` strings, 14 naming a root or scope, 38 bare population
nouns. Seven guards claimed some form of "production python files" across floors from 2555 to
3247 -- a 692-file spread fully explained by differing scan roots, and invisible because only
two of the seven said which roots.

The real-fixture case below is the one the issue asks for by name. A synthetic declaration
proves the rule can fire; it does not prove the rule fires on the shape that actually occurs,
and the shape that occurs is a guard whose discovery stopped reaching one of its own roots
while its floor went on being cleared by the others.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import repo_tests.kb_read_visibility_guard_test as kb
from repo_tests._paths import repo_root
from repo_tests._reach import Reach, ReachScopeError, declare
from repo_tests._reach_scope import relative_paths, scope_complaint

_ROOT = repo_root()


def test_declare_renders_the_scope_from_the_data() -> None:
    """`what=` is derived, so the string cannot disagree with the tuple the check reads."""
    reach = declare(
        "self-check::rendered-scope",
        discover=lambda _root: ["a/x.py"],
        floor=1,
        what="production python files",
        roots=("a/", "b/"),
    )
    assert reach.what == "production python files under a/, b/"


def test_declare_refuses_a_scope_written_twice() -> None:
    """Longhand beside the data is the drift this replaces, not a belt-and-braces restatement."""
    with pytest.raises(ValueError, match="already spells a scope out longhand"):
        declare(
            "self-check::double-scope",
            discover=lambda _root: ["a/x.py"],
            floor=1,
            what="production python files under a/",
            roots=("a/",),
        )


def test_declare_refuses_an_empty_roots_tuple() -> None:
    with pytest.raises(ValueError, match="non-empty tuple of path prefixes"):
        declare("self-check::empty-roots", discover=lambda _root: [], floor=1, what="things", roots=())


def test_the_real_guard_passes_its_own_scope_check() -> None:
    """The negative control, and it has to come first: a check that fails everything is not a check.

    `kb-read-visibility-production-sweep` is the declaration #17844 names as the instance -- it
    claimed "production python files" unqualified over three scan roots. With the scope carried
    as data it must now PASS, or the mutation below would be meaningless.
    """
    kb.REACH.verify_scope(_ROOT)
    assert kb.REACH.what.endswith(", ".join(kb.SCAN_ROOTS)), "the rendered claim must name the roots it was built from"


def test_a_real_guard_whose_discovery_stops_reaching_a_root_fails() -> None:
    """The mutation, on the REAL fixture rather than a synthetic one (#17844 AC2).

    The guard's own `discover` is kept and its output narrowed to two of its three declared
    roots -- the shape a moved directory or an inverted filter produces. The floor is untouched
    and still cleared: 2,701 files minus the MCP tree is far above 2,555, so every count check
    in the suite stays green. Only the scope check notices.
    """
    narrowed, dropped = kb.SCAN_ROOTS[:-1], kb.SCAN_ROOTS[-1]

    def _narrowed(root: Path) -> list[str]:
        return [rel for rel in kb._production_files(root) if rel.startswith(narrowed)]

    mutant = Reach(
        name="self-check::kb-read-visibility-narrowed",
        discover=_narrowed,
        floor=kb.REACH.floor,
        what=kb.REACH.what,
        growth=kb.REACH.growth,
        roots=kb.SCAN_ROOTS,
    )

    assert len(mutant.population(_ROOT)) >= mutant.floor, "precondition: the mutant must still clear its floor"
    with pytest.raises(ReachScopeError) as caught:
        mutant.verify_scope(_ROOT)
    assert dropped in str(caught.value), "the failure must name the root the sweep stopped reaching"


def test_a_sweep_reaching_outside_its_declared_scope_fails() -> None:
    """The mirror: a scope narrower than the sweep under-reports what the guard covers."""
    reach = Reach(
        name="self-check::under-claimed-scope",
        discover=lambda _root: ["a/x.py", "elsewhere/y.py"],
        floor=1,
        what="things under a/",
        roots=("a/",),
    )
    with pytest.raises(ReachScopeError, match="outside every declared root"):
        reach.verify_scope(_ROOT)


def test_a_declaration_whose_items_are_not_paths_is_refused_rather_than_passed() -> None:
    """`roots=` on a sweep returning parsed objects would be a claim nothing can check."""
    assert relative_paths([("a.yml", "job"), 3], _ROOT) is None
    complaint = scope_complaint("synthetic", "things", ("a/",), None)
    assert "not paths" in complaint


def test_the_scope_check_is_satisfiable() -> None:
    """Positive control for the primitive itself, independent of any live guard."""
    assert scope_complaint("synthetic", "things under a/, b/", ("a/", "b/"), ["a/x.py", "b/y.py"]) == ""


def test_a_declared_scope_that_the_sweep_does_not_reach_is_refused() -> None:
    """The synthetic control for `verify_scope`: it must be able to fail.

    The real-fixture mutation above is the one #17844 asks for; this is the cheap half that
    keeps `reach_declarations_test`'s parametrised sweep from passing vacuously if
    `verify_scope` ever became a no-op.
    """
    overclaiming = Reach(
        name="self-check::overclaiming-scope",
        discover=lambda _root: ["autobot-backend/api/x.py"],
        floor=1,
        what="production python files under autobot-backend/, autobot-slm-backend/",
        roots=("autobot-backend/", "autobot-slm-backend/"),
    )
    with pytest.raises(ReachScopeError, match="found NOTHING under"):
        overclaiming.verify_scope(_ROOT)


#: What each scoped declaration claims, written out BY HAND rather than read from the constant
#: the guard walks (#17844, review). Every call site passes `roots=SCAN_ROOTS` or the local
#: equivalent, so narrowing that constant narrows the claim with it and `verify_scope` stays
#: green over the smaller population -- which is the very mutation #17844's AC2 describes.
#: This is the independent second derivation that closes it: narrow a guard's roots constant
#: and this goes red, because the expectation does not move with it.
#:
#: Compared as a SET in both directions. Adding a scoped declaration means adding a line here,
#: and that is the point -- the scope is a decision, so it is written twice on purpose.
_DECLARED_SCOPES = {
    "direct-secrets-service-callers": ("autobot-backend", "autobot_shared"),
    "jekyll-processed-docs": ("docs",),
    "kb-admin-read-bypass": ("autobot-backend/", "autobot_shared/"),
    "kb-read-visibility-production-sweep": (
        "autobot-backend/",
        "autobot_shared/",
        "autobot-infrastructure/shared/mcp/",
    ),
    "model-revision-pinning-sweep": ("autobot-backend", "autobot_shared", "autobot-slm-backend"),
    "one-claim-registry": (
        "autobot-backend",
        "autobot_shared",
        "autobot-slm-backend",
        "scripts",
        "pipeline-scripts",
    ),
    "store-fact-chokepoint": ("autobot-backend/", "autobot_shared/"),
}


def test_every_scoped_declaration_claims_the_roots_recorded_here() -> None:
    """A guard's roots constant cannot be narrowed without this failing.

    `verify_scope` holds the sweep to `roots`; it cannot hold `roots` to anything, because the
    call sites alias the same constant the discovery walks. Without this pin, deleting a tree
    from `SCAN_ROOTS` shrinks the sweep AND the claim together and every check in the suite
    stays green over two thirds of the population -- the exact state #17844 was filed about.
    """
    import repo_tests.direct_secrets_service_callers_17773_test  # noqa: F401, PLC0415
    import repo_tests.docs_liquid_tags_are_defined_17930_test  # noqa: F401, PLC0415
    import repo_tests.kb_admin_read_bypass_guard_test  # noqa: F401, PLC0415
    import repo_tests.model_revision_pinning_enforced_17804_test  # noqa: F401, PLC0415
    import repo_tests.one_claim_registry_16653_test  # noqa: F401, PLC0415
    import repo_tests.store_fact_chokepoint_guard_test  # noqa: F401, PLC0415
    from repo_tests._reach import REGISTRY

    live = {
        name: reach.roots for name, reach in REGISTRY.items() if reach.roots and not name.startswith("self-check::")
    }
    assert live == _DECLARED_SCOPES, (
        "declared scopes disagree with the hand-written record. Narrowed or widened: "
        + repr(
            {
                n: (live.get(n), _DECLARED_SCOPES.get(n))
                for n in set(live) ^ set(_DECLARED_SCOPES) | {n for n in live if live[n] != _DECLARED_SCOPES.get(n)}
            }
        )
        + "\nA root removed from a guard's own constant shrinks the sweep and the claim "
        "together, which nothing else here can see. Change both, in one diff, on purpose."
    )
