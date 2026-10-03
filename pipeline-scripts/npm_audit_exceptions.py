# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Which advisories the npm audit gate yields to, and why (#13400).

Split from ``npm_audit_gate.py`` when that file reached the 600-line hard limit: the gate's job
is to invoke ``npm audit`` and turn one report into a verdict, and this module's job is the
POLICY -- which advisories are excused, under what conditions, and what counts as a fix. They
were one file because the policy started as a dict; it is now a predicate with four conditions
and the reasoning that justifies each.

Owning the severity vocabulary here rather than in the gate keeps the dependency one-way: the
gate imports from this module and this module imports nothing of the gate's.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

SEVERITY_ORDER = ("critical", "high", "moderate", "low", "info")
FAILING_SEVERITIES = ("critical", "high")

_GHSA = re.compile(r"GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}")


@dataclass(frozen=True)
class AdvisoryException:
    """One advisory the gate yields to, with the reason and the date it stops counting."""

    expires: str
    reason: str


#: Advisories with NO published fix, which the gate yields to until ``expires``.
#:
#: Yielding is deliberate and recorded, which is what the workflow comment above this
#: gate asks for -- "if an advisory ever has no published fix and the gate has to yield,
#: change it deliberately and record why on #13400 -- do not silence it as a flake".
#:
#: Four conditions, each failing LOUDLY rather than quietly widening the gate:
#:   * ``expires`` is in the future. An expired entry fails the gate naming itself, so the
#:     yield cannot outlive the reason for it by inattention.
#:   * npm reports **no fix available** for any failing package. The moment a bump exists
#:     the exception stops being honoured and the gate demands the bump -- which is the
#:     only reason this is not a silence.
#:   * every entry is still reported. A drained entry fails, the same shrink-only pressure
#:     the ratchet baselines use, so the record cannot accumulate dead policy.
#:   * an advisory not listed here still fails. The set is a floor on scrutiny, not a lid.
#:
#: The expiry is enforced by THIS GATE and not by the test suite, deliberately: a test
#: failing on a date would block every Python PR, where the gate blocks only the PRs that
#: trigger the frontend suite. So the suite stays date-independent and #17890 carries the
#: reminder to look again before 2026-11-14.
ADVISORY_EXCEPTIONS: dict[str, AdvisoryException] = {
    "GHSA-vfj7-8cjw-p6xm": AdvisoryException(
        expires="2026-11-14",
        reason=(
            "braces <= 3.0.3 stack-exhaustion DoS, published 2026-09-18, advisory API reports "
            "first_patched_version NULL and npm reports range '*' -- no non-vulnerable version of "
            "braces exists, which is the owner's condition for this record. No bump OF BRACES is "
            "possible; npm does offer a fix path via the parent, and it is stylelint 7.7.0 against "
            "a declared ^17.15.0 -- a rollback across ten majors of a devDependency. The owner "
            "declines that trade: the chain is stylelint and @vue/eslint-config-typescript through "
            "micromatch/fast-glob/globby, all devDependencies, and nothing in a shipped bundle "
            "imports it. An earlier wording said 'no bump exists', which was true of braces and "
            "wrong about the question the gate asks (ae, review of #17889). Owner decision "
            "2026-10-03, recorded on #13400; the dependency-type scoping question is #17890."
        ),
    )
}


_LOWER_BOUND = re.compile(r">=?\s*(\d+(?:\.\d+)*)")


def _version_tuple(text: str) -> tuple[int, ...] | None:
    """``"7.7.0"`` -> ``(7, 7, 0)``; ``None`` when it is not a plain dotted number."""
    try:
        return tuple(int(part) for part in text.split("-", 1)[0].split("."))
    except (AttributeError, ValueError):
        return None


def entry_offers_a_patch(package: str, entry: dict) -> bool:
    """Does npm offer a PATCHED VERSION OF *package*, as opposed to a way round it?

    The owner's condition for an exception (#13400) is that the advisory has **no patched
    version**. The first implementation tested npm's ``fixAvailable`` for truthiness, which
    answers a different question: npm reports a fix whenever it can make the warning go away,
    and for a transitive package that means *bump the parent*. Three distinct situations all
    arrive as "fix available":

    * ``fixAvailable.name`` naming a DIFFERENT package -- a parent bump. ``braces`` reports
      ``{"name": "stylelint", ...}``: nothing about ``braces`` is patched.
    * ``range == "*"`` -- every version of the package is vulnerable. This is npm's own way of
      saying ``first_patched_version: null``, in the gate's own input, and it is the owner's
      condition expressed in the data rather than inferred from it.
    * an offered version BELOW the vulnerable range's lower bound -- a rollback. ``stylelint``
      is vulnerable at ``>=7.7.1`` and npm offers ``7.7.0``: escaping backwards across ten
      majors, which is a trade for a human to weigh and not a patch.

    Anything unparseable counts AS a patch, so the exception is withdrawn rather than excused:
    a range this cannot read must not become permission.
    """
    fix = entry.get("fixAvailable")
    if not isinstance(fix, dict):
        return bool(fix)
    if fix.get("name") != package:
        return False
    vulnerable = str(entry.get("range") or "")
    if vulnerable.strip() == "*":
        return False
    offered = _version_tuple(str(fix.get("version") or ""))
    bound = _LOWER_BOUND.search(vulnerable)
    floor = _version_tuple(bound.group(1)) if bound else None
    if offered is not None and floor is not None and offered < floor:
        return False
    return True


def _attribute_entry(package: str, entry: dict, detail: dict) -> tuple[set[str], list[str]]:
    """``(advisory ids this entry names, reasons it is not fully attributed)`` -- per via
    entry, for the three reasons in the module docstring."""
    ids: set[str] = set()
    problems: list[str] = []
    vias = entry.get("via") or []
    if not vias:
        return ids, [f"{package} is a failing advisory with no `via` entries to attribute"]
    for via in vias:
        if isinstance(via, dict):
            match = _GHSA.search(str(via.get("url") or ""))
            if match:
                ids.add(match.group(0))
            else:
                problems.append(f"{package} names an advisory with no GHSA id: {via.get('url') or via!r}")
        elif isinstance(via, str):
            if via not in detail:
                problems.append(f"{package} is attributed to `{via}`, which the report does not describe")
        else:
            problems.append(f"{package} has a `via` entry that is neither an advisory nor a package: {via!r}")
    return ids, problems


def failing_advisories(report: dict) -> tuple[dict[str, bool], list[str]] | None:
    """``{advisory id: a patch for an affected package exists}``, and attribution problems.

    Public because the gate consumes it: a helper that crosses a module boundary is that
    module's interface, whatever its name was while it lived inside one file.

    Per advisory, not per run. The previous version returned ONE boolean meaning "any failing
    package anywhere in this report is fixable", and `_entry_problem` withdrew an exception on
    it -- so an unrelated fixable advisory revoked a valid owner ruling. The flag was named
    `fixable`, which reads at the call site as a property of the advisory being judged; it
    held a property of the whole report, and the gate's message ("a failing package") was the
    accurate one.

    ``None`` when the per-package detail is unreadable: the caller keeps a failing verdict.
    """
    detail = report.get("vulnerabilities")
    if not isinstance(detail, dict):
        return None
    patchable: dict[str, bool] = {}
    problems: list[str] = []
    for package, entry in sorted(detail.items()):
        if not isinstance(entry, dict):
            problems.append(f"{package}'s entry is not a mapping, so its severity is unknown")
            continue
        severity = entry.get("severity")
        if severity is None:
            problems.append(f"{package} has no severity recorded, so it cannot be ruled out")
            continue
        if severity not in FAILING_SEVERITIES:
            continue
        entry_ids, entry_problems = _attribute_entry(str(package), entry, detail)
        problems += entry_problems
        patched_here = entry_offers_a_patch(str(package), entry)
        for advisory in entry_ids:
            patchable[advisory] = patchable.get(advisory, False) or patched_here
    return patchable, problems


def _entry_problem(
    advisory: str, exception: AdvisoryException, patchable_by_advisory: dict[str, bool], today: date
) -> str | None:
    """Why this entry is not honoured, or ``None`` when it is. Never raises."""
    if advisory not in patchable_by_advisory:
        return (
            f"{advisory} is recorded as unfixable but is no longer reported -- remove it from "
            "ADVISORY_EXCEPTIONS; a record that outlives its advisory is dead policy"
        )
    try:
        expires = date.fromisoformat(exception.expires)
    except ValueError:
        return f"{advisory}'s expiry {exception.expires!r} is not a date -- the record is unusable"
    if expires < today:
        return (
            f"{advisory}'s exception expired on {exception.expires} -- re-check for a published "
            "fix and either bump or renew it deliberately"
        )
    if patchable_by_advisory[advisory]:
        return (
            f"{advisory} is recorded as unfixable, but npm offers a patched version of a package "
            "affected BY THIS ADVISORY -- bump it; the exception is not honoured once a patch exists"
        )
    return None


def excused_phrase(honoured: Iterable[str]) -> str:
    """``GHSA-a (expires D), GHSA-b (expires D)`` for the advisories an exception covered.

    Lives here rather than in the gate because ``ADVISORY_EXCEPTIONS`` must have exactly ONE
    reader (#13400). When the gate formatted this itself it needed the record re-exported, and a
    re-exported mutable record has two names for one object: the gate's tests patched the gate's
    name while ``exception_problems`` went on reading the original, so four of them silently
    stopped testing what they said they tested. The record is only reachable through the module
    that defines it, so patching it and reading it are the same act.
    """
    return ", ".join(f"{a} (expires {ADVISORY_EXCEPTIONS[a].expires})" for a in sorted(honoured))


def exception_problems(patchable_by_advisory: dict[str, bool], today: date) -> tuple[set[str], list[str]]:
    """``(ids honoured, reasons the record itself is wrong)``.

    The second half is the point: a record that can only ever widen the gate is a silence
    with extra steps, so every way it can be stale is a failure that names itself.
    """
    honoured: set[str] = set()
    problems: list[str] = []
    for advisory, exception in sorted(ADVISORY_EXCEPTIONS.items()):
        problem = _entry_problem(advisory, exception, patchable_by_advisory, today)
        if problem:
            problems.append(problem)
        else:
            honoured.add(advisory)
    return honoured, problems
