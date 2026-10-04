# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Whether a phase's checks may be reported as a completion figure (#17089).

A separate module, and not for tidiness. This is the policy that decides when a
number is allowed to be called "completion", and it has to be testable without
importing ``phase_validation_system``, which pulls ``aiohttp``, ``psutil``,
``requests`` and ``autobot_shared`` at module scope. A policy that nothing can
exercise is how the previous one survived unnoticed.

THE DEFECT THIS REPLACES. #7496 skipped the endpoint, service and feature checks
under ``--ci-mode`` on sound grounds -- the workflow never brings a stack up, so
they would all have failed. But skipping removed them from the DENOMINATOR as
well as the numerator, and the phase percentage is ``passed / total``. With the
live checks gone, "Phase 6: Enhanced UI/UX" scored ``2 / 2`` and reported
**100% complete**, where the two were "``autobot-frontend/src/App.vue`` exists"
and "``autobot-frontend/package.json`` exists". A skipped check had become a
passed check, and the more the run could not measure, the higher it scored.

That is the inversion this module exists to prevent: *not looked at* must never
be reportable as *nothing missing* (see ``MEASUREMENT_DISCIPLINE.md``).

THE RULE. A phase with even one skipped check group cannot be called complete at
any ratio, and its number is not called completion. It is called structural
presence, which is what a file-existence sweep actually measures. The ratio is
still reported, because "8 of 9 present" is useful -- it just may not wear a
name it has not earned.

WHY THE CEILING IS A SEPARATE RULE from the naming. Capping the number would be
the obvious fix and the wrong one: a cap makes 99% mean two different things and
invites someone to raise it later. The number stays truthful about what it
measured and the *claim* is what gets withheld, so ``complete`` is a field with
its own reason rather than a threshold comparison anyone can re-derive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Sequence, Tuple

#: What a skipped group is reported as. One string so the report and the tests
#: cannot drift, and phrased as an admission rather than a status.
NOT_CHECKED = "not checked (needs live stack)"

#: The criteria groups that need a running stack, so ``--ci-mode`` cannot check
#: them. Named here rather than inline so a guard can assert this list still
#: matches the feature types ``_validate_phase_features`` iterates -- the stale
#: list was half of #17089, and a skip list that silently stopped covering a
#: group would under-report what went unchecked.
LIVE_STACK_GROUPS = (
    "endpoints",
    "services",
    "security_features",
    "performance_metrics",
    "monitoring_features",
    "ui_features",
    "orchestration_features",
    "ai_features",
    "production_features",
    "testing_features",
)

#: A phase is only ever called complete at or above this share of its checks --
#: and only when nothing was skipped. Unchanged from the previous behaviour so
#: this module changes what a number is CALLED, not where the bar sits.
COMPLETE_AT = 95.0


@dataclass(frozen=True)
class PhaseScore:
    """The checks a phase ran, and what may therefore be claimed about it.

    ``skipped`` holds the names of check GROUPS that did not run (``endpoints``,
    ``services``, ``features``), not individual checks: when a stack is absent
    the whole group is unavailable and the count of what it would have contained
    is not knowable. Reporting the group by name is honest about that; inventing
    a denominator for it would not be.
    """

    ran: int
    passed: int
    skipped: Tuple[str, ...] = field(default_factory=tuple)
    #: Workflows that authoritatively test this phase. When set, the phase
    #: reports NO figure of its own -- see :meth:`as_report`.
    defers_to: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def percentage(self) -> float:
        """Share of the checks that RAN which passed. 0.0 when none ran.

        Named neutrally on purpose -- what this figure may be called depends on
        ``skipped``, and that decision lives in :meth:`as_report`.
        """
        if self.ran <= 0:
            return 0.0
        return round((self.passed / self.ran) * 100, 2)

    @property
    def measures_completion(self) -> bool:
        """True only when every check group ran, so the figure means completion."""
        return not self.skipped

    @property
    def complete(self) -> bool:
        """Whether this phase may be called complete.

        False whenever anything was skipped, at any percentage. This is the
        inversion guard: it is the reason a 2-of-2 structural sweep can no longer
        report the phase finished.
        """
        return self.measures_completion and self.percentage >= COMPLETE_AT

    @property
    def status(self) -> str:
        if self.skipped:
            return "structural-presence-only"
        if self.percentage >= COMPLETE_AT:
            return "complete"
        if self.percentage >= 75:
            return "nearly_complete"
        if self.percentage >= 50:
            return "in_progress"
        return "incomplete"

    def as_report(self) -> Dict[str, Any]:
        """The fields a report may carry for this phase.

        A phase with ``defers_to`` reports NEITHER percentage. "Phase 6:
        Enhanced UI/UX" is the case that prompted #17089: whether a UI is
        consistent, responsive and internationalised is not a question a
        file-existence sweep can answer at any percentage, and publishing a
        number beside a phase whose real verdict lives in four other workflows
        invites exactly the reading the owner objected to. So it names those
        workflows and stays silent on the score.

        ``completion_percentage`` is ABSENT, not zero and not null, when checks
        were skipped. A consumer that reaches for it gets a ``KeyError`` instead
        of a number it would have believed -- the same reason a floor guard
        raises rather than returning an empty set.
        """
        if self.defers_to:
            return {
                "checks_ran": self.ran,
                "checks_passed": self.passed,
                "complete": False,
                "status": "deferred-to-dedicated-gates",
                "authoritative_gates": list(self.defers_to),
                "why_no_score": (
                    "this phase is verified by dedicated workflows, not by file presence; "
                    "see " + ", ".join(self.defers_to)
                ),
            }

        report: Dict[str, Any] = {
            "structural_presence_percentage": self.percentage,
            "checks_ran": self.ran,
            "checks_passed": self.passed,
            "complete": self.complete,
            "status": self.status,
        }
        if self.measures_completion:
            report["completion_percentage"] = self.percentage
        else:
            report["not_checked"] = {group: NOT_CHECKED for group in self.skipped}
            report["why_not_complete"] = (
                f"{len(self.skipped)} check group(s) were not run, so completion was not measured: "
                + ", ".join(self.skipped)
            )
        return report


def overall(scores: Sequence[Tuple[PhaseScore, float]]) -> Dict[str, Any]:
    """Aggregate weighted phase scores into the run's top-level figures.

    Emits ``structural_presence`` always and ``overall_maturity`` only when no
    phase skipped anything. The CI gate reads the former and says so; before
    #17089 it read a completion figure that no live check had contributed to.
    """
    # A phase that reports no figure of its own must not contribute one here
    # either -- otherwise its number still reaches the gate through the average,
    # and "reports no score" would be true of the phase and false of the run.
    counted = [(score, weight) for score, weight in scores if not score.defers_to]
    deferred = sorted({gate for score, _ in scores if score.defers_to for gate in score.defers_to})

    # #17674: ``None``, not 0.0. No weight means every phase deferred (or the
    # run scored nothing at all), so there was no figure to average -- and a
    # 0.0 here is a measurement-shaped value the CI gate would accept and fail
    # on. The gate's reader rejects a non-number loudly and names what it
    # found, which is the honest outcome for "nothing could be weighed".
    total_weight = sum(weight for _, weight in counted)
    weighted = (
        sum(score.percentage * weight for score, weight in counted) / total_weight if total_weight > 0 else None
    )

    skipped_groups = sorted({group for score, _ in counted for group in score.skipped})
    result: Dict[str, Any] = {
        "structural_presence": round(weighted, 2) if weighted is not None else None,
        "measures": (
            "nothing could be weighed -- every phase defers to a dedicated gate"
            if weighted is None
            else ("completion" if not skipped_groups else "structural presence only")
        ),
        "checks_skipped": len(skipped_groups),
        "skipped_detail": {group: NOT_CHECKED for group in skipped_groups},
        "phases_complete": sum(1 for score, _ in scores if score.complete),
        # Stated rather than left to inference: the aggregate is over fewer
        # phases than the run evaluated, and this says which and why.
        "phases_excluded_from_score": sum(1 for score, _ in scores if score.defers_to),
        "verified_by_dedicated_gates": deferred,
    }
    if not skipped_groups and weighted is not None:
        result["overall_maturity"] = round(weighted, 2)
        result["ready_for_production"] = weighted >= 85
    else:
        result["overall_maturity"] = None
        # Not False: production readiness was not assessed, and False would read
        # as "assessed and failed" to anything rendering this.
        result["ready_for_production"] = None
    return result


#: Top-level keys :func:`project_report` REBUILDS into a different shape.
#: Everything else at the top level is carried through verbatim.
#:
#: A deny-list, deliberately, and not the allow-list it replaces (#17674). The
#: old projection enumerated four keys by hand, so ``structural_presence`` --
#: added to the aggregate by #17505, read by the CI gate from the same change --
#: never reached the artifact, the gate read ``None``, a defensive default
#: rendered it as ``0``, and ``0 < 60`` failed the gate. An allow-list drops
#: silently when the producer grows a key; a deny-list carries the new key and
#: only needs editing when a key's SHAPE changes, which is a change you cannot
#: make without touching this module.
REBUILT_KEYS = frozenset({"phases", "recommendations"})

#: Top-level keys deliberately NOT carried into the artifact, each with its
#: reason. Separate from :data:`REBUILT_KEYS` because "rebuilt in another shape"
#: and "dropped on purpose" are different facts, and a single set called
#: "restructured" told the second one as if it were the first -- the same
#: conflation, in the fix for it.
DROPPED_KEYS = {
    # A nested restatement of the aggregate keys that are already top-level
    # here (``structural_presence``, ``measures``, ``skipped_detail``,
    # ``phases_complete``, ``ready_for_production``). Two copies of one figure
    # in one artifact is how a consumer ends up reading the stale one. The
    # full object is still written by ``save_validation_report``.
    "overall_assessment": "a nested duplicate of the top-level aggregate keys",
}


def project_report(results: Dict[str, Any], timestamp: str) -> Dict[str, Any]:
    """The JSON artifact CI consumes, derived from the in-memory results.

    ``timestamp`` is passed in rather than taken here so this module stays a
    pure policy with no clock: the same results object projects to the same
    report, which is what makes the contract testable.

    Per-phase, ``structural_presence_percentage`` stays ``None`` rather than 0
    for a phase that defers to dedicated gates -- 0 would read as "measured and
    found empty" (#17089), which is the same confusion one level down.
    """
    report: Dict[str, Any] = {
        key: value for key, value in results.items() if key not in REBUILT_KEYS and key not in DROPPED_KEYS
    }
    report["timestamp"] = timestamp
    report["phases"] = [
        {
            "name": phase_name,
            "status": phase_data.get("status", "unknown"),
            "structural_presence_percentage": phase_data.get("structural_presence_percentage"),
            "complete": phase_data.get("complete", False),
            "not_checked": phase_data.get("not_checked", {}),
            "authoritative_gates": phase_data.get("authoritative_gates", []),
            # #7496: ``_validate_phase`` stores per-check details under
            # ``validations`` (plural). The old key ``validation_details``
            # silently defaulted to ``{}`` in every report.
            "validation_details": phase_data.get("validations", {}),
        }
        for phase_name, phase_data in results.get("phases", {}).items()
    ]
    report["recommendations"] = [
        {"title": rec, "action": "Review and implement"} for rec in results.get("recommendations", [])
    ]
    return report
