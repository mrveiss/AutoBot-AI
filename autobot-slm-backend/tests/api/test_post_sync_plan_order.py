# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Post-sync actions come out in an executable order, each unit restarted once.

`get_node_actions` built its list role-major -- walk the node's roles, extend
per role -- so the result could not be executed top to bottom. Two concrete
failures, both observed on a live node's action bar:

- a role's `install` landing after another role's `restart`, so a service came
  back before the dependency it needs was installed;
- the same systemd unit scheduled twice. `ollama` appeared twice with identical
  labels, because it is owned by both `autobot-llm-cpu` and `autobot-llm-gpu`
  (#16025). And `autobot-celery` appeared twice with *different* labels -- once
  alone, once inside `Restart autobot-backend autobot-celery`.

The second pair is why these tests assert on UNITS rather than on labels or
commands: the celery duplication is invisible to any comparison of the strings
a user sees.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SLM_BACKEND = Path(__file__).resolve().parents[2]
if str(_SLM_BACKEND) not in sys.path:
    sys.path.insert(0, str(_SLM_BACKEND))

from api._post_sync_plan import ordered_post_sync_plan  # noqa: E402
from api.roles import PostSyncAction  # noqa: E402


def _action(category: str, role: str, *, units: str | None = None, label: str | None = None) -> PostSyncAction:
    return PostSyncAction(
        role_name=role,
        display_name=role,
        category=category,
        label=label or (f"Restart {units}" if units else f"{category} ({role})"),
        command=None if units else f"do-{category}",
        systemd_service=units,
    )


def _categories(plan) -> list[str]:
    return [a.category for a in plan]


def _all_units(plan) -> list[str]:
    return [u for a in plan for u in (a.systemd_service or "").split()]


class TestTheOrderIsExecutable:
    def test_a_restart_never_precedes_an_install(self):
        """The failure this exists for: role-major output interleaved them."""
        plan = ordered_post_sync_plan(
            [
                _action("restart", "postgresql", units="postgresql"),
                _action("install", "ai-stack"),
                _action("restart", "ai-stack", units="autobot-ai-stack"),
            ]
        )

        assert _categories(plan) == ["install", "restart", "restart"]

    def test_every_category_lands_in_dependency_order(self):
        plan = ordered_post_sync_plan(
            [
                _action("restart", "a", units="svc-a"),
                _action("build", "b"),
                _action("schema", "c"),
                _action("install", "d"),
            ]
        )

        assert _categories(plan) == ["install", "schema", "build", "restart"]

    def test_an_unknown_category_lands_before_the_restarts(self):
        """A category added to `_classify_post_sync` and not to the rank table
        must not silently sort after the restarts it should precede."""
        plan = ordered_post_sync_plan(
            [
                _action("restart", "a", units="svc-a"),
                _action("seed-fixtures", "b"),
                _action("install", "c"),
            ]
        )

        assert _categories(plan) == ["install", "seed-fixtures", "restart"]

    def test_two_roles_in_one_category_keep_their_incoming_order(self):
        """Stable within a category, so the output changes only when roles do."""
        plan = ordered_post_sync_plan([_action("install", "first"), _action("install", "second")])

        assert [a.role_name for a in plan] == ["first", "second"]


class TestNoUnitRestartsTwice:
    def test_two_roles_owning_one_unit_produce_one_restart(self):
        """`ollama` backs autobot-llm-cpu and autobot-llm-gpu (#16025)."""
        plan = ordered_post_sync_plan(
            [
                _action("restart", "autobot-llm-cpu", units="ollama"),
                _action("restart", "autobot-llm-gpu", units="ollama"),
            ]
        )

        assert _all_units(plan) == ["ollama"]

    def test_a_unit_inside_a_group_is_not_restarted_alone_as_well(self):
        """The case a label comparison cannot see.

        `Restart autobot-celery` and `Restart autobot-backend autobot-celery`
        are different strings and overlap on one unit.
        """
        plan = ordered_post_sync_plan(
            [
                _action("restart", "celery", units="autobot-celery"),
                _action("restart", "backend", units="autobot-backend autobot-celery"),
            ]
        )

        assert sorted(_all_units(plan)) == ["autobot-backend", "autobot-celery"]

    def test_the_intended_group_survives_and_the_subset_is_dropped(self):
        """Larger groups win: a role grouping backend with celery means they
        are meant to come back together, so the group stays whole rather than
        being shrunk to leave celery restarting on its own."""
        plan = ordered_post_sync_plan(
            [
                _action("restart", "celery", units="autobot-celery"),
                _action("restart", "backend", units="autobot-backend autobot-celery"),
            ]
        )

        assert [a.systemd_service for a in plan] == ["autobot-backend autobot-celery"]

    def test_a_partial_overlap_keeps_the_units_not_already_scheduled(self):
        """Neither group contains the other, so the second keeps its remainder
        and its label is rewritten to match what it will actually restart."""
        plan = ordered_post_sync_plan(
            [
                _action("restart", "one", units="svc-a svc-b"),
                _action("restart", "two", units="svc-b svc-c"),
            ]
        )

        assert sorted(_all_units(plan)) == ["svc-a", "svc-b", "svc-c"]
        assert [a.label for a in plan] == ["Restart svc-a svc-b", "Restart svc-c"]

    def test_a_restart_with_no_unit_is_kept_rather_than_swallowed(self):
        """Dropping it would hide a misconfigured role behind a tidy list."""
        plan = ordered_post_sync_plan([_action("restart", "broken", units=None, label="Restart")])

        assert len(plan) == 1

    def test_a_plan_with_no_duplicates_is_returned_unchanged(self):
        """Negative control: without this, every assertion above is satisfied
        by a function that drops restarts it does not understand."""
        incoming = [
            _action("install", "shared"),
            _action("restart", "a", units="svc-a"),
            _action("restart", "b", units="svc-b"),
        ]

        plan = ordered_post_sync_plan(incoming)

        assert [a.role_name for a in plan] == ["shared", "a", "b"]
        assert _all_units(plan) == ["svc-a", "svc-b"]


class TestTheLiveBarThatPromptedThis:
    """The 22-button bar a node actually rendered, reduced to its defects."""

    @pytest.fixture
    def observed(self):
        return [
            _action("restart", "postgresql", units="postgresql"),
            _action("restart", "redis", units="redis-stack-server"),
            _action("install", "ai-stack"),
            _action("restart", "ai-stack", units="autobot-ai-stack"),
            _action("restart", "autobot-llm-cpu", units="ollama"),
            _action("restart", "autobot-llm-gpu", units="ollama"),
            _action("restart", "celery", units="autobot-celery"),
            _action("restart", "celery-beat", units="autobot-celery-beat"),
            _action("install", "shared"),
            _action("build", "slm-frontend"),
            _action("schema", "backend"),
            _action("restart", "backend", units="autobot-backend autobot-celery"),
        ]

    def test_the_two_redundant_restarts_are_gone(self, observed):
        units = _all_units(ordered_post_sync_plan(observed))

        assert len(units) == len(set(units)), f"a unit is restarted twice: {units}"
        assert units.count("ollama") == 1
        assert units.count("autobot-celery") == 1

    def test_nothing_restarts_before_the_installs_and_the_migration(self, observed):
        plan = ordered_post_sync_plan(observed)
        first_restart = next(i for i, a in enumerate(plan) if a.category == "restart")

        assert all(a.category != "restart" for a in plan[:first_restart])
        assert {a.category for a in plan[:first_restart]} == {"install", "schema", "build"}

    def test_no_action_is_lost(self, observed):
        """Ordering and deduplication only, never a silent drop of real work.

        The two removals are accounted for by name: one `ollama` restart and
        the standalone `autobot-celery` restart, both of which the surviving
        actions already cover.
        """
        plan = ordered_post_sync_plan(observed)

        assert len(plan) == len(observed) - 2
        assert set(_all_units(plan)) == {u for a in observed for u in (a.systemd_service or "").split()}
