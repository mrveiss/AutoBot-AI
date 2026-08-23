# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14756: the legacy-session backfill must never guess.

#12685 left pre-existing agent sessions untagged on purpose — the only signal
they carry is a display title, and matching on titles is the fragility that
issue removed. This backfill is the explicit, operator-run alternative, and its
whole safety argument rests on one thing: a title is acted on **only** when the
id inside it names a company that actually exists.

The direction of failure matters and is asserted here. Leaving an agent chat
visible is a cosmetic miss; hiding a user's own conversation is data loss from
their point of view. So every ambiguous case must land in `unclassified`, not
in `taggable`.
"""

from __future__ import annotations

import pytest

from chat_history.session_scope_backfill import (
    SESSION_KIND_AGENT,
    apply_plan,
    build_plan,
    classify,
    is_already_scoped,
    render,
)

REAL_COMPANY = "22d907a9-31fd-4bb4-8b42-89aa1c2d3e4f"
OTHER_UUID = "11111111-2222-3333-4444-555555555555"
KNOWN = {REAL_COMPANY}


def _session(chat_id, name, **extra):
    return {"chatId": chat_id, "name": name, **extra}


LEGACY_AGENT = _session("s-legacy", f"CEO · {REAL_COMPANY}")
ODD_USER_TITLE = _session("s-user", "CEO · notes from standup")
ALREADY_TAGGED = _session("s-tagged", f"CEO · {REAL_COMPANY}", companyId=REAL_COMPANY, sessionKind="agent")


class TestTheFixtureFromTheIssue:
    """A legacy agent session, an odd user title, and an already-tagged one."""

    def test_each_lands_in_exactly_one_bucket(self):
        plan = build_plan([LEGACY_AGENT, ODD_USER_TITLE, ALREADY_TAGGED], KNOWN)

        assert [c.session_id for c in plan.taggable] == ["s-legacy"]
        assert [c.session_id for c in plan.already_tagged] == ["s-tagged"]
        assert [c.session_id for c in plan.unclassified] == ["s-user"]
        assert plan.scanned == 3

    def test_the_legacy_session_is_tagged_with_the_id_from_its_title(self):
        candidate = classify(LEGACY_AGENT, KNOWN)
        assert candidate.company_id == REAL_COMPANY


class TestAnAmbiguousSessionIsReportedNeverGuessed:
    @pytest.mark.parametrize(
        "name,why",
        [
            ("CEO · notes from standup", "the id is not a uuid at all"),
            (f"CEO · {OTHER_UUID}", "a well-formed uuid that names no company"),
            ("Quarterly planning", "no separator, an ordinary chat name"),
            (f"{REAL_COMPANY}", "the bare id with no role half"),
            (f"CEO·{REAL_COMPANY}", "no spaces around the separator"),
        ],
    )
    def test_it_is_never_taggable(self, name, why):
        plan = build_plan([_session("s", name)], KNOWN)

        assert plan.taggable == [], f"would have tagged a session where {why}"
        assert len(plan.unclassified) == 1
        assert plan.unclassified[0].reason, "an unclassified session must say why"

    def test_a_uuid_that_names_no_company_is_the_case_that_matters(self):
        """The check that separates a classification from a guess.

        This title is byte-for-byte the shape the real producer wrote. Only the
        lookup against existing companies tells them apart, so a backfill that
        trusted the title would tag this and hide a user's chat.
        """
        candidate = classify(_session("s", f"CEO · {OTHER_UUID}"), KNOWN)

        assert candidate.company_id == ""
        assert "no company" in candidate.reason


class TestReRunningChangesNothing:
    @pytest.mark.asyncio
    async def test_an_already_tagged_session_is_never_rewritten(self):
        writes = []

        class _Mgr:
            async def update_session_metadata(self, session_id, metadata):
                writes.append((session_id, metadata))
                return True

        plan = build_plan([ALREADY_TAGGED], KNOWN)
        written = await apply_plan(plan, _Mgr())

        assert written == 0
        assert writes == [], "a re-run must not rewrite what the first run tagged"

    @pytest.mark.asyncio
    async def test_the_second_pass_over_applied_output_finds_nothing_to_do(self):
        """Idempotency asserted end to end, not by inspection.

        The session dict is updated the way the read path would see it after a
        write, then re-planned.
        """
        session = dict(LEGACY_AGENT)
        plan = build_plan([session], KNOWN)
        assert len(plan.taggable) == 1

        applied = {**session, "companyId": plan.taggable[0].company_id, "sessionKind": SESSION_KIND_AGENT}
        second = build_plan([applied], KNOWN)

        assert second.taggable == []
        assert len(second.already_tagged) == 1


class TestApplyWritesOnlyTheScopingFields:
    @pytest.mark.asyncio
    async def test_exactly_two_keys_are_written(self):
        writes = []

        class _Mgr:
            async def update_session_metadata(self, session_id, metadata):
                writes.append((session_id, metadata))
                return True

        plan = build_plan([LEGACY_AGENT, ODD_USER_TITLE, ALREADY_TAGGED], KNOWN)
        written = await apply_plan(plan, _Mgr())

        assert written == 1
        assert writes == [("s-legacy", {"company_id": REAL_COMPANY, "session_kind": "agent"})], (
            "the backfill must write the scoping fields and nothing else — anything "
            "more risks clobbering metadata it does not own"
        )

    @pytest.mark.asyncio
    async def test_a_failed_write_is_not_counted_as_applied(self):
        class _Mgr:
            async def update_session_metadata(self, session_id, metadata):
                return False

        plan = build_plan([LEGACY_AGENT], KNOWN)

        assert await apply_plan(plan, _Mgr()) == 0


class TestThePredicateMatchesTheReadPath:
    def test_it_agrees_with_the_filter_it_has_to_satisfy(self):
        """If these drift, a "tagged" session stays visible and the run looks done.

        Mirrors `api/chat_sessions._is_agent_scoped_session`'s cases.
        """
        assert is_already_scoped({"companyId": "co-1"}) is True
        assert is_already_scoped({"sessionKind": "agent"}) is True
        assert is_already_scoped({"companyId": "", "sessionKind": "user"}) is False
        assert is_already_scoped({}) is False


class TestTheDryRunReportSaysItWroteNothing:
    def test_it_names_the_unclassified_and_marks_itself_a_dry_run(self):
        plan = build_plan([LEGACY_AGENT, ODD_USER_TITLE], KNOWN)
        report = render(plan)

        assert "DRY RUN" in report
        assert "nothing was written" in report
        assert "s-user" in report, "an operator must see what was skipped, not just the count"
        assert "applied" not in report.replace("Re-run with --apply", "")
