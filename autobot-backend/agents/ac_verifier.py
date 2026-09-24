# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Verifying an issue's acceptance criteria against merged code (#17090).

Part of #16698: AutoBot's first role in its own development loop. Agents spend
much of their effort answering "is this criterion actually met in `origin/main`"
before closing or ticking anything, and that answer is mechanical enough to
produce and far too consequential to guess -- a wrong "met" closes an issue on
work that does not exist.

So every path here is built so that the cheapest outcome is **can't tell**:

* A criterion whose wording needs a running system never reaches a model at
  all; it is reported as *needs host evidence* by rule (`ac_criteria`).
* A verdict of met or not met must carry a `file:line` that EXISTS in merged
  code. Citations are parsed out of the model's own reasoning and checked
  against `git show origin/main:<path>`; a verdict whose citations are all
  rejected is downgraded to can't tell, with the rejections recorded.
* A decision that fails to arrive -- no schema-valid answer inside the retry
  budget -- is can't tell, never an assumed verdict. `decisions.decide` raises
  rather than manufacturing an answer, and that raise is caught here and
  reported as what it is.
* Nothing ticks a box. The result is one comment; the checkbox stays a human's
  (or a reviewing agent's) to tick, which is #17090's fourth criterion and the
  reason this module has no write path into the issue body.

The machine-readable block at the end of the comment exists so the next reader
is a program as easily as a person: `#17092`'s queue page and any later gate
read the verdicts without re-parsing English.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Sequence

from agents.ac_criteria import (
    Citation,
    Criterion,
    code_searcher,
    criteria_after_the_section,
    criterion_terms,
    extract_criteria,
    file_reader,
    parse_citations,
    unparsed_amendment_hint,
    verify_citations,
)
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp
from llm_shared.decisions import ChoiceQuestion, DecisionError, decide

logger = get_logger(__name__)

#: The fenced block's language tag. A stable name so a reader -- #17092's page,
#: a later gate -- can find the machine-readable half without parsing prose.
SUMMARY_BLOCK_TAG = "autobot-ac-verification"


class Verdict(str, Enum):
    """What can be said about one criterion from merged code alone."""

    MET = "met"
    NOT_MET = "not_met"
    CANT_TELL = "cant_tell"
    NEEDS_HOST_EVIDENCE = "needs_host_evidence"


#: The verdicts that require a surviving citation. A claim about merged code
#: with nothing that can be opened is not a finding, it is an assertion.
_EVIDENCE_REQUIRED = (Verdict.MET, Verdict.NOT_MET)

_QUESTION_ID = "criterion_verdict"

_INSTRUCTIONS = (
    "Decide whether the acceptance criterion below is met by the MERGED CODE quoted as evidence. "
    f"Answer {Verdict.MET.value} or {Verdict.NOT_MET.value} ONLY if the evidence shows it, and cite at "
    "least one `path/to/file.ext:LINE` from the evidence in your reasoning -- a citation that is not in "
    f"the evidence will be rejected and your verdict discarded. Answer {Verdict.CANT_TELL.value} whenever "
    "the evidence does not settle it, including when there is no evidence. Answer "
    f"{Verdict.NEEDS_HOST_EVIDENCE.value} if the criterion can only be checked on a running system."
)


@dataclass(frozen=True)
class CriterionResult:
    """One criterion's verdict and everything it rests on."""

    criterion: Criterion
    verdict: Verdict
    citations: tuple[Citation, ...] = ()
    rejected_citations: tuple[str, ...] = ()
    reasoning: str = ""
    probability: Optional[float] = None
    #: Why a verdict was downgraded, when it was. Empty when it was not.
    downgraded_from: str = ""

    def as_payload(self) -> dict:
        """The machine-readable form: what #17092 and any later gate read."""
        return {
            "index": self.criterion.index,
            "source": self.criterion.source,
            "already_ticked": self.criterion.checked,
            "verdict": self.verdict.value,
            "evidence": [str(citation) for citation in self.citations],
            "rejected_evidence": list(self.rejected_citations),
            "confidence": self.probability,
            "downgraded_from": self.downgraded_from,
            "criterion": self.criterion.text,
        }


@dataclass(frozen=True)
class IssueVerification:
    """Every criterion of one issue, verified."""

    issue_number: int
    results: tuple[CriterionResult, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)
    ref: str = "origin/main"
    at: str = ""

    def counts(self) -> dict[str, int]:
        """How many criteria landed on each verdict."""
        tally = {verdict.value: 0 for verdict in Verdict}
        for result in self.results:
            tally[result.verdict.value] += 1
        return tally


def _question(criterion: Criterion) -> ChoiceQuestion:
    return ChoiceQuestion(
        id=_QUESTION_ID,
        prompt=f"Is this acceptance criterion met by the merged code? Criterion: {criterion.text}",
        options=[verdict.value for verdict in Verdict],
    )


def _state(criterion: Criterion, evidence: str) -> str:
    return (
        f"{_INSTRUCTIONS}\n\n## Criterion\n{criterion.text}\n\n"
        f"## Evidence from merged code\n{evidence or '(no matching code was found)'}"
    )


def _validated(
    criterion: Criterion,
    verdict: Verdict,
    reasoning: str,
    probability: float,
    read: Callable[[str], Optional[str]],
    evidence: str = "",
) -> CriterionResult:
    """Downgrade a verdict whose citations do not survive being opened.

    A citation must ALSO appear in the evidence the model was shown (review
    finding on the merged #17090). Opening the line proved only that it exists
    and is not blank -- so a citation to a real, non-blank line anywhere in the
    tree passed, whether or not it had anything to do with the criterion. The
    evidence block is `path:line: content` per hit, so requiring the `path:line`
    prefix to appear in it means a verdict can only rest on something the model
    was actually looking at. `evidence=""` keeps the old behaviour for a caller
    that has no evidence text to check against, and says so by defaulting.
    """
    if verdict not in _EVIDENCE_REQUIRED:
        return CriterionResult(criterion=criterion, verdict=verdict, reasoning=reasoning, probability=probability)

    # Existence first, so a fabricated PATH still reports "no such file" rather
    # than the vaguer "not in the evidence"; the evidence check then filters what
    # survived. Both reasons are useful and they answer different questions.
    opened, rejected = verify_citations(parse_citations(reasoning), read)
    rejected = list(rejected)
    verified = []
    for citation in opened:
        if evidence and str(citation) not in evidence:
            rejected.append(f"{citation}: real, but not in the evidence this verdict was shown")
            continue
        verified.append(citation)
    if verified:
        return CriterionResult(
            criterion=criterion,
            verdict=verdict,
            citations=tuple(verified),
            rejected_citations=tuple(rejected),
            reasoning=reasoning,
            probability=probability,
        )
    return CriterionResult(
        criterion=criterion,
        verdict=Verdict.CANT_TELL,
        rejected_citations=tuple(rejected) or ("no file:line was cited",),
        reasoning=reasoning,
        probability=probability,
        downgraded_from=verdict.value,
    )


async def verify_criterion(
    criterion: Criterion,
    *,
    search: Callable[[Sequence[str]], str],
    read: Callable[[str], Optional[str]],
    label: str = "ac_verifier.criterion",
) -> CriterionResult:
    """One criterion's verdict, with its evidence checked before it is believed."""
    if criterion.needs_host_evidence:
        return CriterionResult(
            criterion=criterion,
            verdict=Verdict.NEEDS_HOST_EVIDENCE,
            reasoning="the criterion's own wording asks about a running system, which merged code cannot answer",
        )

    evidence = search(criterion_terms(criterion))
    try:
        result = await decide(_state(criterion, evidence), [_question(criterion)], label=label)
    except DecisionError as exc:
        logger.warning("ac_verifier: no decision for criterion %s (%s)", criterion.index, exc)
        return CriterionResult(
            criterion=criterion,
            verdict=Verdict.CANT_TELL,
            reasoning=f"the decision did not arrive: {exc}",
        )

    answer = result[_QUESTION_ID]
    return _validated(criterion, Verdict(str(answer.value)), answer.reasoning, answer.probability, read, evidence)


async def verify_issue(
    issue_number: int,
    body: str,
    comments: Sequence[tuple[str, str]] = (),
    *,
    search: Callable[[Sequence[str]], str] | None = None,
    read: Callable[[str], Optional[str]] | None = None,
    ref: str = "origin/main",
) -> IssueVerification:
    """Verify every criterion of one issue against *ref*."""
    searcher = search or code_searcher(ref=ref)
    reader = read or file_reader(ref=ref)
    criteria = extract_criteria(body, comments)

    results = [await verify_criterion(criterion, search=searcher, read=reader) for criterion in criteria]

    notes: list[str] = []
    if not criteria:
        notes.append("no acceptance criteria were found in this issue: nothing was verified")
    unread = criteria_after_the_section(body)
    if unread:
        notes.append(
            f"{unread} checkbox line(s) appear after the acceptance-criteria section and were NOT "
            "verified -- the section ended at a heading. Move them under the criteria heading, or "
            "read them yourself; this result covers only what is above that heading"
        )
    hint = unparsed_amendment_hint(comments)
    if hint:
        notes.append(hint)
    return IssueVerification(
        issue_number=issue_number,
        results=tuple(results),
        notes=tuple(notes),
        ref=ref,
        at=utc_timestamp(),
    )


_VERDICT_LABEL = {
    Verdict.MET: "met",
    Verdict.NOT_MET: "NOT met",
    Verdict.CANT_TELL: "can't tell",
    Verdict.NEEDS_HOST_EVIDENCE: "needs host evidence",
}


def _result_line(result: CriterionResult) -> str:
    evidence = ", ".join(f"`{citation}`" for citation in result.citations) or "—"
    detail = ""
    if result.downgraded_from:
        detail = f" (a {result.downgraded_from} verdict was discarded: {'; '.join(result.rejected_citations)})"
    text = result.criterion.text[:90]
    return f"| {result.criterion.index} | {_VERDICT_LABEL[result.verdict]} | {evidence} | {text}{detail} |"


def render_comment(verification: IssueVerification) -> str:
    """The single comment posted back to the issue (#17090 AC 4).

    It states what was NOT verified as prominently as what was: a reader who
    sees four rows and no note cannot tell whether the fifth criterion passed or
    was never read.
    """
    counts = verification.counts()
    header = (
        f"## Acceptance-criteria verification against `{verification.ref}`\n\n"
        f"{counts['met']} met · {counts['not_met']} not met · {counts['cant_tell']} can't tell · "
        f"{counts['needs_host_evidence']} needs host evidence — checked {verification.at}.\n\n"
        "Nothing here ticks a box: that stays with a human or a reviewing agent. A verdict of met or "
        "not met carries a `file:line` that was opened in merged code; one whose citation could not be "
        "opened was downgraded to can't tell rather than reported.\n"
    )
    table = "\n| # | verdict | evidence | criterion |\n|---|---|---|---|\n" + "\n".join(
        _result_line(result) for result in verification.results
    )
    notes = (
        "\n\n" + "\n".join(f"> **Not verified:** {note}" for note in verification.notes) if verification.notes else ""
    )
    payload = {
        "issue": verification.issue_number,
        "ref": verification.ref,
        "at": verification.at,
        "counts": counts,
        "criteria": [result.as_payload() for result in verification.results],
        "notes": list(verification.notes),
    }
    block = f"\n\n```{SUMMARY_BLOCK_TAG}\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n```\n"
    return header + table + notes + block


__all__ = [
    "SUMMARY_BLOCK_TAG",
    "CriterionResult",
    "IssueVerification",
    "Verdict",
    "render_comment",
    "verify_criterion",
    "verify_issue",
]
