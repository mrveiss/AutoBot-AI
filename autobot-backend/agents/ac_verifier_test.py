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
