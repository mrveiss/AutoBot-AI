# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The audit gate's recorded-exception mechanism, and what it discloses (#13400).

Split from ``npm_audit_gate_test.py`` because that file reached the 600-line hard limit:
the gate's own message says "split it -- do not add a KNOWN_LARGE entry", and recording an
entry to fit a test file would be grandfathering to avoid a split. Shared helpers are
imported from it rather than copied, so there is one ``_FakeNpm`` and one ``BULK_LOG``.

The division of labour matters for reading these: the tests here cover the DECISION (which
advisories are excused and why) and the DISCLOSURE (what a human sees when one is). Review
on #17889 found the second missing entirely -- nine tests asserted on ``verdict.reason``
while the headline printed "no high or critical advisories" over six excused ones -- so the
``main()``-level tests at the bottom read stdout and the job summary, not the verdict object.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import npm_audit_gate as gate
import pytest
from npm_audit_gate_test import BULK_LOG, _FakeNpm, _report

# --- recorded unfixable advisories (#13400) --------------------------------
#
# Owner decision 2026-10-03: GHSA-vfj7-8cjw-p6xm (braces <= 3.0.3, published 2026-09-18)
# has `first_patched_version: null`, every lockfile here is already at 3.0.3, and the chain
# is devDependencies only. The gate yields to it until the recorded expiry.
#
# Every fixture below is a literal in this file, so none of them can degrade through a
# loader, and each failure mode the record can have gets one that trips it.

_EXCUSED = "GHSA-vfj7-8cjw-p6xm"
_UNKNOWN = "GHSA-aaaa-bbbb-cccc"


def _detailed(*advisories: tuple[str, str, bool], **counts: int) -> str:
    """A report with per-package detail: ``(package, advisory id, fix available)`` each."""
    vulnerabilities = {key: counts.get(key, 0) for key in ("info", "low", "moderate", "high", "critical")}
    vulnerabilities["total"] = sum(vulnerabilities.values())
    detail = {
        package: {
            "name": package,
            "severity": "high",
            "fixAvailable": fix,
            "via": [{"source": 1, "name": package, "url": f"https://github.com/advisories/{advisory}"}],
        }
        for package, advisory, fix in advisories
    }
    return json.dumps(
        {"auditReportVersion": 2, "vulnerabilities": detail, "metadata": {"vulnerabilities": vulnerabilities}}
    )


@pytest.fixture
def recorded_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """A record with a far-future expiry, for tests about the MECHANISM.

    Review on #17889: a test that drives `classify()` or `main()` against the production
    record silently depends on today's date, so it goes red by itself the day the real entry
    expires -- while its docstring claims the boundary is pinned elsewhere. The boundary is
    pinned by injecting `today` into `exception_problems`; these tests supply their own
    policy instead, so the mechanism's tests and the record's expiry are independent.
    """
    monkeypatch.setattr(
        gate,
        "ADVISORY_EXCEPTIONS",
        {
            _EXCUSED: gate.AdvisoryException(
                expires="2099-01-01",
                reason="test policy: unfixable, devDependencies only, recorded on #13400",
            )
        },
    )


def test_a_recorded_unfixable_advisory_passes_and_names_itself(recorded_exception) -> None:
    """The yield is visible in the verdict, not silent -- the whole difference from silencing."""
    verdict = gate.classify(_detailed(("braces", _EXCUSED, False), high=6), BULK_LOG)

    assert verdict.result == gate.PASSED
    assert _EXCUSED in verdict.reason and "#13400" in verdict.reason
    assert verdict.counts["high"] == 6, "the count is still reported; the advisory is excused, not hidden"


def test_an_unrecorded_advisory_still_fails_beside_an_excused_one(recorded_exception) -> None:
    """The record is a floor on scrutiny, not a lid: one unknown id fails the whole gate."""
    verdict = gate.classify(_detailed(("braces", _EXCUSED, False), ("other", _UNKNOWN, False), high=2), BULK_LOG)

    assert verdict.result == gate.FOUND
    assert _UNKNOWN in verdict.reason


def test_a_fix_being_available_withdraws_the_exception(recorded_exception) -> None:
    """The condition that keeps this from being a silence: a bump exists, so bump it."""
    verdict = gate.classify(_detailed(("braces", _EXCUSED, True), high=1), BULK_LOG)

    assert verdict.result == gate.FOUND
    assert "fix available" in verdict.reason


def test_an_expired_exception_fails_and_names_the_date() -> None:
    """Injected date, so the test does not change meaning when the expiry passes."""
    expiry = date.fromisoformat(gate.ADVISORY_EXCEPTIONS[_EXCUSED].expires)
    honoured, problems = gate.exception_problems({_EXCUSED}, False, expiry + timedelta(days=1))

    assert honoured == set()
    assert any(gate.ADVISORY_EXCEPTIONS[_EXCUSED].expires in problem for problem in problems)


def test_the_exception_is_honoured_on_its_last_day() -> None:
    """Contrast for the boundary: expiry is inclusive, so the off-by-one is pinned."""
    expiry = date.fromisoformat(gate.ADVISORY_EXCEPTIONS[_EXCUSED].expires)
    honoured, problems = gate.exception_problems({_EXCUSED}, False, expiry)

    assert honoured == {_EXCUSED}
    assert problems == []


def test_a_drained_exception_fails_rather_than_lingering() -> None:
    """Shrink-only, as the ratchet baselines are: a record cannot outlive its advisory."""
    honoured, problems = gate.exception_problems({_UNKNOWN}, False, date(2026, 10, 3))

    assert honoured == set()
    assert any("no longer reported" in problem for problem in problems)


def test_a_count_without_any_advisory_id_is_never_excused_into_a_pass() -> None:
    """The existing `_report` shape: counts present, detail empty. FOUND, and says why."""
    verdict = gate.classify(_report(high=1), BULK_LOG)

    assert verdict.result == gate.FOUND
    assert "named no advisory id" in verdict.reason


def test_unreadable_detail_is_never_excused_into_a_pass() -> None:
    """Detail that is not a mapping at all is a different failure from an empty one.

    Both must be FOUND, and separating them is the point: "I could not read the detail" and
    "the detail named nothing" send a reader to different places, and a shared message would
    have sent them to the wrong one.
    """
    broken = json.dumps(
        {
            "auditReportVersion": 2,
            "vulnerabilities": "not a mapping",
            "metadata": {"vulnerabilities": {"info": 0, "low": 0, "moderate": 0, "high": 1, "critical": 0}},
        }
    )
    verdict = gate.classify(broken, BULK_LOG)

    assert verdict.result == gate.FOUND
    assert "unreadable" in verdict.reason


def test_every_recorded_exception_carries_a_reason_and_an_issue() -> None:
    """A record whose entries need no justification is a silence with a dict around it."""
    for advisory, exception in gate.ADVISORY_EXCEPTIONS.items():
        assert date.fromisoformat(exception.expires), advisory
        assert len(exception.reason) > 80, f"{advisory} needs a reason, not a label"
        assert "#" in exception.reason, f"{advisory} must cite the issue recording the decision"


def test_an_empty_record_excuses_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no exceptions recorded the gate is exactly what it was before this mechanism.

    The question a reviewer should ask of any allowlist is whether the empty case is the
    old behaviour or a new hole. Here it is the old behaviour: nothing is honoured, every
    failing advisory is unexcused, and the verdict is FOUND.
    """
    monkeypatch.setattr(gate, "ADVISORY_EXCEPTIONS", {})
    verdict = gate.classify(_detailed(("braces", _EXCUSED, False), high=6), BULK_LOG)

    assert verdict.result == gate.FOUND
    assert _EXCUSED in verdict.reason


def test_the_failing_verdict_maps_to_a_non_zero_exit() -> None:
    """A yield that warned and continued would be the silence this gate forbids."""
    assert gate.EXIT_CODES[gate.FOUND] != 0
    assert gate.EXIT_CODES[gate.UNAVAILABLE] != 0
    assert gate.EXIT_CODES[gate.PASSED] == 0


# --- disclosure: the mechanism's accountability IS its output ----------------
#
# Review on #17889 found an excused pass printing "no high or critical advisories" while six
# were excused. Every one of the nine tests above asserted on `verdict.reason` -- they pinned
# the DECISION and not the DISCLOSURE, so the false headline was invisible to all of them.
# These drive `main()` and read what a human actually sees.


def test_an_excused_pass_names_the_advisory_in_stdout_and_the_summary(
    tmp_path, monkeypatch, capsys, recorded_exception
) -> None:
    """Exit 0, and the id, the expiry and #13400 in both places a reader looks."""
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("NPM_AUDIT_MAX_ATTEMPTS", "1")
    monkeypatch.setattr(gate, "_run_npm_audit", _FakeNpm((_detailed(("braces", _EXCUSED, False), high=6), BULK_LOG)))

    assert gate.main(["--report", str(tmp_path / "audit-results.json")]) == 0

    printed = capsys.readouterr().out
    written = summary.read_text(encoding="utf-8")
    for place, text in (("stdout", printed), ("the job summary", written)):
        assert _EXCUSED in text, f"the advisory id never reached {place}"
        assert "#13400" in text, f"the issue recording the decision never reached {place}"
        assert gate.ADVISORY_EXCEPTIONS[_EXCUSED].expires in text, f"the expiry never reached {place}"
    assert "no high or critical advisories" not in printed, (
        "an excused pass must not claim there were none -- six were excused, and that sentence "
        "is the false statement #13400 exists to forbid"
    )
    assert "::warning" in printed, "an excused pass belongs in the checks UI, not only the log"
    assert "| high | 6 |" in written, "the counts are still reported; the advisory is excused, not hidden"


def test_a_stale_record_on_a_clean_audit_says_so_rather_than_claiming_advisories(tmp_path, monkeypatch, capsys) -> None:
    """The drain case: counts are zero, the entry is dead, and the headline must not hunt a ghost."""
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.setenv("NPM_AUDIT_MAX_ATTEMPTS", "1")
    monkeypatch.setattr(gate, "_run_npm_audit", _FakeNpm((_report(), BULK_LOG)))

    assert gate.main(["--report", str(tmp_path / "audit-results.json")]) == 1

    printed = capsys.readouterr().out
    assert "exception record is stale" in printed
    assert _EXCUSED in printed and "no longer reported" in printed
    assert "advisories found" not in printed, "zero advisories were found; saying so sends the reader hunting"


def test_a_failing_run_names_which_advisory_was_not_excused(tmp_path, monkeypatch, capsys, recorded_exception) -> None:
    """A FOUND reason was computed and dropped too: "Bump the dependency" named nothing."""
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.setenv("NPM_AUDIT_MAX_ATTEMPTS", "1")
    report = _detailed(("braces", _EXCUSED, False), ("other", _UNKNOWN, False), high=2)
    monkeypatch.setattr(gate, "_run_npm_audit", _FakeNpm((report, BULK_LOG)))

    assert gate.main(["--report", str(tmp_path / "audit-results.json")]) == 1

    printed = capsys.readouterr().out
    assert _UNKNOWN in printed, "a failing run must name the advisory that failed it"
    assert "Bump the dependency" in printed


def test_a_failing_package_naming_no_advisory_id_is_not_excused_by_another(recorded_exception) -> None:
    """The fail-OPEN parse, and the test I had not written for my own fix.

    Mutating the fix away left all 57 tests green, which is how I know this assertion was
    missing rather than redundant.
    """
    report = json.dumps(
        {
            "auditReportVersion": 2,
            "vulnerabilities": {
                "braces": {
                    "severity": "high",
                    "fixAvailable": False,
                    "via": [{"url": f"https://github.com/advisories/{_EXCUSED}"}],
                },
                "mystery": {
                    "severity": "high",
                    "fixAvailable": False,
                    "via": [{"title": "something", "url": "https://example.invalid/not-an-advisory"}],
                },
            },
            "metadata": {"vulnerabilities": {"info": 0, "low": 0, "moderate": 0, "high": 2, "critical": 0}},
        }
    )

    verdict = gate.classify(report, BULK_LOG)

    assert verdict.result == gate.FOUND
    assert "mystery" in verdict.reason, f"the unidentifiable package must be named: {verdict.reason}"


def test_a_malformed_expiry_fails_closed_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_entry_problem` says "never raises", and a bad date in the record must honour that.

    Fail-closed was already the behaviour -- the exception raised, `main` caught it and exited
    1 -- but a crash is a different thing from a verdict, and the docstring claimed the latter.
    """
    monkeypatch.setattr(
        gate,
        "ADVISORY_EXCEPTIONS",
        {_EXCUSED: gate.AdvisoryException(expires="not-a-date", reason="x" * 90 + " #13400")},
    )

    verdict = gate.classify(_detailed(("braces", _EXCUSED, False), high=1), BULK_LOG)

    assert verdict.result == gate.FOUND
    assert "not a date" in verdict.reason and _EXCUSED in verdict.reason


# --- attribution: every via entry, not every package ------------------------
#
# The second #17889 review found three defects in one line, and the test that existed
# covered only the single-dict case -- the one that was already working. Each fixture below
# reached PASS with "excused by recorded exception" while an unnamed advisory sat in the
# same report.


def _entry(severity: str = "high", *via: object, fix: bool = False) -> dict:
    return {"severity": severity, "fixAvailable": fix, "via": list(via)}


def _with(detail: dict, **counts: int) -> str:
    vulnerabilities = {key: counts.get(key, 0) for key in ("info", "low", "moderate", "high", "critical")}
    vulnerabilities["total"] = sum(vulnerabilities.values())
    return json.dumps(
        {"auditReportVersion": 2, "vulnerabilities": detail, "metadata": {"vulnerabilities": vulnerabilities}}
    )


_GHSA_VIA = {"url": f"https://github.com/advisories/{_EXCUSED}"}
_LEGACY_VIA = {"title": "legacy advisory", "url": "https://npmjs.com/advisories/1234"}


def test_a_second_via_dict_without_an_id_is_not_covered_by_the_first(recorded_exception) -> None:
    """Ids were collected across the whole list before asking whether any were missing."""
    report = _with({"braces": _entry("high", _GHSA_VIA, _LEGACY_VIA)}, high=1)

    verdict = gate.classify(report, BULK_LOG)

    assert verdict.result == gate.FOUND
    assert "no GHSA id" in verdict.reason and "braces" in verdict.reason


def test_a_string_via_does_not_suppress_an_unidentified_dict(recorded_exception) -> None:
    """`["braces", {no GHSA}]` set a `transitive` flag that skipped the check entirely."""
    report = _with({"braces": _entry("high", _GHSA_VIA), "other": _entry("high", "braces", _LEGACY_VIA)}, high=2)

    verdict = gate.classify(report, BULK_LOG)

    assert verdict.result == gate.FOUND
    assert "other" in verdict.reason


def test_a_failing_entry_with_no_severity_is_not_skipped(recorded_exception) -> None:
    """`severity not in FAILING_SEVERITIES` dropped a missing key while counts reported it."""
    report = _with(
        {"braces": _entry("high", _GHSA_VIA), "mystery": {"fixAvailable": False, "via": [_GHSA_VIA]}}, high=2
    )

    verdict = gate.classify(report, BULK_LOG)

    assert verdict.result == gate.FOUND
    assert "no severity recorded" in verdict.reason


def test_a_dangling_string_via_is_reported(recorded_exception) -> None:
    """A string `via` naming a package the report does not describe resolves to nothing."""
    report = _with({"braces": _entry("high", _GHSA_VIA), "other": _entry("high", "not-in-this-report")}, high=2)

    verdict = gate.classify(report, BULK_LOG)

    assert verdict.result == gate.FOUND
    assert "does not describe" in verdict.reason


def test_a_failing_entry_with_no_via_entries_is_reported(recorded_exception) -> None:
    """Nothing to attribute is not nothing to worry about."""
    verdict = gate.classify(_with({"orphan": _entry("high")}, high=1), BULK_LOG)

    assert verdict.result == gate.FOUND
    assert "no `via` entries" in verdict.reason


def test_counts_and_detail_disagreeing_is_unavailable_not_a_pass(recorded_exception) -> None:
    """A report contradicting itself is an unreadable report, not a clean one (N2)."""
    verdict = gate.classify(_with({"braces": _entry("high", _GHSA_VIA)}, high=0), BULK_LOG)

    assert verdict.result == gate.UNAVAILABLE
    assert "disagree" in verdict.reason or "while the per-package detail" in verdict.reason


def test_the_real_transitive_chain_still_passes(recorded_exception) -> None:
    """The contrast that matters: failing CLOSED must not break the actual braces report.

    npm reports one root advisory and five dependents whose `via` names its parent by
    string. Every string resolves inside the report, so the chain is fully attributed and
    the exception applies -- if this went red, the gate would stop being an unblock.
    """
    detail = {"braces": _entry("high", _GHSA_VIA)}
    for package, parent in (
        ("micromatch", "braces"),
        ("fast-glob", "micromatch"),
        ("globby", "fast-glob"),
        ("stylelint", "globby"),
        ("@vue/eslint-config-typescript", "globby"),
    ):
        detail[package] = _entry("high", parent)

    verdict = gate.classify(_with(detail, high=6), BULK_LOG)

    assert verdict.result == gate.PASSED, verdict.reason
    assert _EXCUSED in verdict.reason and "6 excused" in verdict.reason
