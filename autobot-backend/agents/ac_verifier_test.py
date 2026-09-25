# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#17090's fifth criterion, as tests: the four verdicts and the fake citation.

Every case drives the real `verify_criterion` with a substituted decision
backend, so what is under test is the module's own handling of an answer --
which is where a wrong verdict would come from. The decision itself is not
under test here; `llm_shared/decisions.py` owns that.
"""

from __future__ import annotations

import pytest

from agents import ac_verifier
from agents.ac_criteria import Criterion
from agents.ac_verifier import Verdict, render_comment, verify_criterion, verify_issue
from llm_shared.decisions import Calibration, DecisionAnswer, DecisionError, DecisionResult

#: A file the citation checker can open, with a known line 2.
_FILE = "autobot-backend/agents/ac_verifier.py"
_CONTENT = "line one\nline two has content\n\nline four\n"


def _read(path: str):
    return _CONTENT if path == _FILE else None


def _search(_terms):
    return f"{_FILE}:2: line two has content"


#: Twenty numbered lines, so a citation to line 1 and one to line 12 are both
#: real -- the substring collision is only reachable when the low line exists.
_LONG_CONTENT = "".join(f"line {n}\n" for n in range(1, 21))


def _read_long(path: str):
    return _LONG_CONTENT if path == _FILE else None


def _search_showing_line_12(_terms):
    # Two-space indent and a trailing colon, exactly as `code_searcher` joins
    # its hits -- the indent is why the check has to strip before matching.
    return f"  {_FILE}:12: line 12"


def _answer(value: str, reasoning: str, probability: float = 0.9) -> DecisionResult:
    return DecisionResult(
        answers={
            "criterion_verdict": DecisionAnswer(
                question_id="criterion_verdict",
                value=value,
                probability=probability,
                reasoning=reasoning,
                calibration=Calibration.SELF_REPORTED,
            )
        },
        backend="stub",
    )


@pytest.fixture
def decided(monkeypatch):
    """Substitute the decision seam and record that it was called."""
    calls: list[str] = []
    box: dict = {"result": _answer(Verdict.CANT_TELL.value, "")}

    async def _decide(state, questions, **kwargs):
        calls.append(state)
        if isinstance(box["result"], Exception):
            raise box["result"]
        return box["result"]

    monkeypatch.setattr(ac_verifier, "decide", _decide)
    return {"calls": calls, "box": box}


def _criterion(text: str, index: int = 1) -> Criterion:
    return Criterion(index=index, text=text, checked=False, source="body")


class TestTheFourVerdicts:
    @pytest.mark.asyncio
    async def test_a_met_criterion_keeps_its_verdict_and_its_evidence(self, decided):
        decided["box"]["result"] = _answer(Verdict.MET.value, f"implemented at {_FILE}:2")

        result = await verify_criterion(_criterion("`decide` is wired"), search=_search, read=_read)

        assert result.verdict is Verdict.MET
        assert [str(c) for c in result.citations] == [f"{_FILE}:2"]
        assert result.downgraded_from == ""

    @pytest.mark.asyncio
    async def test_a_not_met_criterion_keeps_its_verdict_and_its_evidence(self, decided):
        decided["box"]["result"] = _answer(Verdict.NOT_MET.value, f"only a stub at {_FILE}:2")

        result = await verify_criterion(_criterion("`decide` retries twice"), search=_search, read=_read)

        assert result.verdict is Verdict.NOT_MET
        assert [str(c) for c in result.citations] == [f"{_FILE}:2"]

    @pytest.mark.asyncio
    async def test_an_unverifiable_criterion_is_cant_tell(self, decided):
        decided["box"]["result"] = _answer(Verdict.CANT_TELL.value, "the evidence does not settle it")

        result = await verify_criterion(_criterion("the design is tasteful"), search=_search, read=_read)

        assert result.verdict is Verdict.CANT_TELL
        assert result.citations == ()

    @pytest.mark.asyncio
    async def test_a_host_evidence_criterion_never_reaches_the_model(self, decided):
        """AC3: reported as needs-host-evidence, and by rule rather than by asking.

        Asserting the backend was not called is the point -- a verdict produced
        by a model that happened to agree would pass a weaker test while leaving
        the criterion answerable as "met from code alone" on the next model.
        """
        result = await verify_criterion(
            _criterion("the service restarts cleanly on the live install"), search=_search, read=_read
        )

        assert result.verdict is Verdict.NEEDS_HOST_EVIDENCE
        assert decided["calls"] == []


class TestAFabricatedCitationIsRejected:
    @pytest.mark.asyncio
    async def test_a_line_past_the_end_of_the_file_downgrades_the_verdict(self, decided):
        decided["box"]["result"] = _answer(Verdict.MET.value, f"see {_FILE}:9999")

        result = await verify_criterion(_criterion("`decide` is wired"), search=_search, read=_read)

        assert result.verdict is Verdict.CANT_TELL
        assert result.downgraded_from == Verdict.MET.value
        assert any("9999" in reason and "line(s)" in reason for reason in result.rejected_citations)

    @pytest.mark.asyncio
    async def test_a_file_that_does_not_exist_downgrades_the_verdict(self, decided):
        decided["box"]["result"] = _answer(Verdict.MET.value, "see services/invented_module.py:12")

        result = await verify_criterion(_criterion("`decide` is wired"), search=_search, read=_read)

        assert result.verdict is Verdict.CANT_TELL
        assert any("no such file" in reason for reason in result.rejected_citations)

    @pytest.mark.asyncio
    async def test_a_blank_line_is_not_evidence(self, decided):
        """Line 3 of the fixture is empty: a number guessed near the right area."""
        decided["box"]["result"] = _answer(Verdict.MET.value, f"see {_FILE}:3")

        result = await verify_criterion(_criterion("`decide` is wired"), search=_search, read=_read)

        assert result.verdict is Verdict.CANT_TELL
        assert any("blank" in reason for reason in result.rejected_citations)

    @pytest.mark.asyncio
    async def test_a_verdict_with_no_citation_at_all_is_not_believed(self, decided):
        decided["box"]["result"] = _answer(Verdict.MET.value, "it is obviously done")

        result = await verify_criterion(_criterion("`decide` is wired"), search=_search, read=_read)

        assert result.verdict is Verdict.CANT_TELL
        assert result.rejected_citations == ("no file:line was cited",)

    @pytest.mark.asyncio
    async def test_one_real_citation_survives_alongside_a_fabricated_one(self, decided):
        """A partly-fabricated answer keeps only what can be opened."""
        decided["box"]["result"] = _answer(Verdict.MET.value, f"see {_FILE}:2 and services/invented.py:5")

        result = await verify_criterion(_criterion("`decide` is wired"), search=_search, read=_read)

        assert result.verdict is Verdict.MET
        assert [str(c) for c in result.citations] == [f"{_FILE}:2"]
        assert any("invented.py" in reason for reason in result.rejected_citations)


class TestADecisionThatNeverArrives:
    @pytest.mark.asyncio
    async def test_a_decision_error_is_cant_tell_not_a_guess(self, decided):
        decided["box"]["result"] = DecisionError("no schema-valid answer in 3 attempts")

        result = await verify_criterion(_criterion("`decide` is wired"), search=_search, read=_read)

        assert result.verdict is Verdict.CANT_TELL
        assert "did not arrive" in result.reasoning


class TestTheWholeIssue:
    @pytest.mark.asyncio
    async def test_every_criterion_is_verified_and_counted(self, decided):
        decided["box"]["result"] = _answer(Verdict.MET.value, f"see {_FILE}:2")
        body = "## Acceptance criteria\n- [ ] `decide` is wired\n- [ ] it works on the live install\n"

        verification = await verify_issue(17090, body, search=_search, read=_read)

        assert [r.verdict for r in verification.results] == [Verdict.MET, Verdict.NEEDS_HOST_EVIDENCE]
        assert verification.counts() == {"met": 1, "not_met": 0, "cant_tell": 0, "needs_host_evidence": 1}

    @pytest.mark.asyncio
    async def test_an_issue_with_no_criteria_says_so_rather_than_reporting_clean(self, decided):
        verification = await verify_issue(17090, "## Problem\nno criteria here\n", search=_search, read=_read)

        assert verification.results == ()
        assert any("nothing was verified" in note for note in verification.notes)

    @pytest.mark.asyncio
    async def test_a_prose_amendment_is_reported_as_unread(self, decided):
        decided["box"]["result"] = _answer(Verdict.MET.value, f"see {_FILE}:2")
        body = "## Acceptance criteria\n- [ ] `decide` is wired\n"
        comments = [("c1", "criterion 2 no longer applies, we do it the other way now")]

        verification = await verify_issue(17090, body, comments, search=_search, read=_read)

        assert any("does not parse" in note for note in verification.notes)


class TestTheComment:
    @pytest.mark.asyncio
    async def test_it_carries_the_machine_readable_block_and_never_a_checkbox(self, decided):
        decided["box"]["result"] = _answer(Verdict.MET.value, f"see {_FILE}:2")
        body = "## Acceptance criteria\n- [ ] `decide` is wired\n"

        comment = render_comment(await verify_issue(17090, body, search=_search, read=_read))

        assert "```autobot-ac-verification" in comment
        assert '"verdict": "met"' in comment
        assert "- [x]" not in comment and "- [ ]" not in comment, "the comment must never restate a tickable box"

    @pytest.mark.asyncio
    async def test_a_downgrade_is_visible_to_a_reader_not_only_in_the_json(self, decided):
        decided["box"]["result"] = _answer(Verdict.MET.value, f"see {_FILE}:9999")
        body = "## Acceptance criteria\n- [ ] `decide` is wired\n"

        comment = render_comment(await verify_issue(17090, body, search=_search, read=_read))

        assert "can't tell" in comment
        assert "a met verdict was discarded" in comment


class TestACitationMustHaveBeenShown:
    """A real line that was never in the evidence is not evidence (#17090).

    The citation check used to prove only that a `file:line` exists and is not
    blank, so a citation to any real, non-blank line in the tree survived --
    whether or not it had anything to do with the criterion. A code-reviewer
    pass on the merged code made the point with this file's own fixture: line 2
    of `_FILE` says "line two has content", which supports nothing.
    """

    @pytest.mark.asyncio
    async def test_a_real_line_absent_from_the_evidence_is_rejected(self, decided):
        decided["box"]["result"] = _answer(Verdict.MET.value, f"see {_FILE}:1")

        # `_search` shows line 2 only, so line 1 is real, non-blank, and unshown.
        result = await verify_criterion(_criterion("`decide` is wired"), search=_search, read=_read)

        assert result.verdict is Verdict.CANT_TELL
        assert any("not in the evidence" in reason for reason in result.rejected_citations)

    @pytest.mark.asyncio
    async def test_a_shown_line_is_still_accepted(self, decided):
        """Positive control: the new check must not reject everything."""
        decided["box"]["result"] = _answer(Verdict.MET.value, f"see {_FILE}:2")

        result = await verify_criterion(_criterion("`decide` is wired"), search=_search, read=_read)

        assert result.verdict is Verdict.MET
        assert [str(c) for c in result.citations] == [f"{_FILE}:2"]

    @pytest.mark.asyncio
    async def test_a_nonexistent_path_still_reports_that_reason(self, decided):
        """Existence is checked BEFORE the evidence filter, so the more precise
        reason survives rather than being replaced by the vaguer one."""
        decided["box"]["result"] = _answer(Verdict.MET.value, "see services/invented.py:5")

        result = await verify_criterion(_criterion("`decide` is wired"), search=_search, read=_read)

        assert any("no such file" in reason for reason in result.rejected_citations)


class TestTheEvidenceCheckIsAnchored:
    """A citation to line 1 must not ride in on the evidence quoting line 12.

    The check was `str(citation) not in evidence` over the whole blob, and
    `Citation.__str__` has no terminator -- so `...:1` was a substring of
    `...:12` and the fabricated citation passed. The class of collision, not an
    edge of it: the lower the line number, the likelier it is, which made line 1
    the cheapest citation to invent inside the check that exists to reject
    invented citations (review finding on #17397).

    The test that shipped before this one asserted line 1 against evidence
    showing line 2, where no digit overlap exists -- it passed for a reason
    unrelated to what it was asserting.
    """

    @pytest.mark.asyncio
    async def test_a_low_line_is_not_satisfied_by_a_higher_one_on_the_same_path(self, decided):
        decided["box"]["result"] = _answer(Verdict.MET.value, f"implemented at {_FILE}:1")

        result = await verify_criterion(
            _criterion("`decide` is wired"), search=_search_showing_line_12, read=_read_long
        )

        assert (
            result.verdict is Verdict.CANT_TELL
        ), "line 1 was accepted because the evidence quotes line 12 -- the substring collision"
        assert any("not in the evidence" in reason for reason in result.rejected_citations)

    @pytest.mark.asyncio
    async def test_the_shown_two_digit_line_is_still_accepted(self, decided):
        """Positive control: anchoring must not reject the line actually shown."""
        decided["box"]["result"] = _answer(Verdict.MET.value, f"implemented at {_FILE}:12")

        result = await verify_criterion(
            _criterion("`decide` is wired"), search=_search_showing_line_12, read=_read_long
        )

        assert result.verdict is Verdict.MET
        assert [str(c) for c in result.citations] == [f"{_FILE}:12"]

    @pytest.mark.asyncio
    async def test_a_path_that_is_a_tail_of_the_shown_path_is_not_a_match(self, decided):
        """The other half of the collision: `a.py:1` inside `ba.py:1`.

        Both paths are readable here on purpose. If only the shown one were,
        the citation would be rejected for not existing and this would pass
        without ever reaching the evidence check.
        """
        tail = _FILE.rsplit("/", 1)[-1]  # `ac_verifier.py`, a tail of `_FILE`
        decided["box"]["result"] = _answer(Verdict.MET.value, f"implemented at {tail}:12")

        def _read_both(path: str):
            return _LONG_CONTENT if path in (_FILE, tail) else None

        result = await verify_criterion(
            _criterion("`decide` is wired"), search=_search_showing_line_12, read=_read_both
        )

        assert result.verdict is Verdict.CANT_TELL
        assert any("not in the evidence" in reason for reason in result.rejected_citations)


class TestTruncatedCriteriaReachTheReader:
    """The CRITICAL's repair, asserted end to end rather than in a unit.

    `criteria_after_the_section` is unit-tested in `ac_criteria_test.py` and the
    wiring in `verify_issue` reads correctly -- but a mutation deleting that
    wiring passed every test in this PR, because nothing drove the count
    through to the comment a human reads. Surfacing the truncation IS the fix,
    so this asserts the whole path: body with boxes after the closing heading ->
    `verify_issue` -> `render_comment` (review finding on #17397).
    """

    _BODY = (
        "## Acceptance criteria\n"
        "- [ ] `decide` is wired\n"
        "\n"
        "## Notes for the implementer\n"
        "- [ ] a box below the closing heading\n"
        "- [ ] and a second one\n"
    )

    @pytest.mark.asyncio
    async def test_the_comment_says_how_many_boxes_went_unverified(self, decided):
        decided["box"]["result"] = _answer(Verdict.MET.value, f"see {_FILE}:2")

        comment = render_comment(await verify_issue(17090, self._BODY, search=_search, read=_read))

        assert "> **Not verified:**" in comment, "the count never reached the rendered comment"
        assert "2 checkbox line(s)" in comment
        assert "the section ended at a heading" in comment

    @pytest.mark.asyncio
    async def test_it_verified_only_the_one_criterion_inside_the_section(self, decided):
        """The count is a note, not a silent inclusion: 3 boxes, 1 verified."""
        decided["box"]["result"] = _answer(Verdict.MET.value, f"see {_FILE}:2")

        verification = await verify_issue(17090, self._BODY, search=_search, read=_read)

        assert len(verification.results) == 1

    @pytest.mark.asyncio
    async def test_a_body_with_nothing_after_the_section_says_nothing(self, decided):
        """Negative control: the note must not appear when there is no truncation.

        Without this, the assertions above pass equally well against a
        `render_comment` that emits the note unconditionally.
        """
        decided["box"]["result"] = _answer(Verdict.MET.value, f"see {_FILE}:2")
        body = "## Acceptance criteria\n- [ ] `decide` is wired\n"

        comment = render_comment(await verify_issue(17090, body, search=_search, read=_read))

        assert "checkbox line(s) appear after" not in comment
