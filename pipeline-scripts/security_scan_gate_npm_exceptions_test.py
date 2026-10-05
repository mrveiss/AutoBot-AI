# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The npm gate must honour the ONE recorded exception, and nothing more (#17890).

`npm_audit_exceptions.ADVISORY_EXCEPTIONS` is the owner-decision record.
`npm_audit_gate.py` has always read it; `security_scan_gate.py` — the gate
`security.yml` actually calls on the blocking frontend audit — did not. One
advisory was therefore excused in one workflow and fatal in the other, and ten
open PRs were red on a decision that had already been made.

Making a security gate *more* permissive is the kind of change that has to
prove its limits, so most of this file is about what still FAILS.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import security_scan_gate as gate  # noqa: E402

_EXCUSED = "GHSA-vfj7-8cjw-p6xm"

#: The recorded exception expires 2026-11-14. Tests that need it LIVE pin a date
#: before that, or they would start failing on 2026-11-15 for a reason that has
#: nothing to do with the code under test (CodeRabbit). `recorded_npm_allowances`
#: takes `today` precisely so the expiry is testable in both directions.
_BEFORE_EXPIRY = date(2026, 10, 1)


def _report(vulnerabilities: dict) -> str:
    return json.dumps({"vulnerabilities": vulnerabilities})


def _advisory(ghsa: str, severity: str = "high") -> dict:
    return {"severity": severity, "range": "*", "via": [{"url": f"https://github.com/advisories/{ghsa}"}]}


def _via_package(parent: str, severity: str = "high") -> dict:
    return {"severity": severity, "range": "*", "via": [parent]}


def test_the_recorded_exception_is_the_live_record_not_a_copy() -> None:
    """If this drifts, the gate is excusing something the record no longer says."""
    from npm_audit_exceptions import ADVISORY_EXCEPTIONS

    live, _expired = gate.recorded_npm_allowances(today=_BEFORE_EXPIRY)
    assert live == {k for k, v in ADVISORY_EXCEPTIONS.items() if date.fromisoformat(v.expires) >= _BEFORE_EXPIRY}
    assert _EXCUSED in ADVISORY_EXCEPTIONS, "the braces exception is this test's subject"


def test_an_expired_exception_is_not_honoured(monkeypatch) -> None:
    """An exception outliving its decision is the failure mode of every allowance list."""
    far_future = date.today() + timedelta(days=365 * 50)
    live, expired = gate.recorded_npm_allowances(today=far_future)
    assert live == set(), "every recorded exception should have expired by then"
    assert _EXCUSED in expired


def test_the_excused_advisory_passes_including_its_transitive_chain() -> None:
    """The real shape: one advisory on `braces`, five dependents naming only each other."""
    findings = gate.PARSERS["npm-audit"](
        _report(
            {
                "braces": _advisory(_EXCUSED),
                "micromatch": _via_package("braces"),
                "fast-glob": _via_package("micromatch"),
                "globby": _via_package("fast-glob"),
                "stylelint": _via_package("globby"),
            }
        )
    )
    live, _ = gate.recorded_npm_allowances(today=_BEFORE_EXPIRY)
    assert (
        gate.not_allowed(gate.at_or_above(findings, "high"), live) == []
    ), "the dependents inherit the root's advisory id, so one decision excuses the chain"


def test_an_unrecorded_advisory_still_fails() -> None:
    """The limit that matters. A gate that excuses everything is not a gate."""
    findings = gate.PARSERS["npm-audit"](_report({"left-pad": _advisory("GHSA-aaaa-bbbb-cccc")}))
    live, _ = gate.recorded_npm_allowances(today=_BEFORE_EXPIRY)
    judged = gate.not_allowed(gate.at_or_above(findings, "high"), live)
    assert [f.identifier for f in judged] == ["left-pad"]


def test_a_package_with_its_own_unexcused_advisory_is_not_saved_by_an_excused_parent() -> None:
    """Inheritance must add ids, never replace them."""
    entry = _advisory("GHSA-dead-beef-9999")
    entry["via"].append("braces")
    findings = gate.PARSERS["npm-audit"](_report({"braces": _advisory(_EXCUSED), "evil": entry}))
    live, _ = gate.recorded_npm_allowances(today=_BEFORE_EXPIRY)
    judged = gate.not_allowed(gate.at_or_above(findings, "high"), live)
    assert [f.identifier for f in judged] == [
        "evil"
    ], "a package carrying its own unexcused advisory must still be judged on it"


def test_an_unexcused_root_still_fails_even_though_dependents_inherit() -> None:
    """Why inheritance is safe: the root is always its own finding."""
    findings = gate.PARSERS["npm-audit"](
        _report({"rootpkg": _advisory("GHSA-9999-8888-7777"), "child": _via_package("rootpkg")})
    )
    live, _ = gate.recorded_npm_allowances(today=_BEFORE_EXPIRY)
    judged = sorted(f.identifier for f in gate.not_allowed(gate.at_or_above(findings, "high"), live))
    assert judged == ["child", "rootpkg"], "an unexcused chain fails whole"


def test_a_cycle_in_the_via_graph_terminates() -> None:
    """npm output is not guaranteed acyclic; a fixed-point loop must still stop."""
    findings = gate.PARSERS["npm-audit"](_report({"a": _via_package("b"), "b": _via_package("a")}))
    assert sorted(f.identifier for f in findings) == ["a", "b"]


def test_a_pip_audit_report_is_not_excused_by_the_npm_record(tmp_path: Path, capsys) -> None:
    """The record is npm-specific, asserted through `main()` rather than restated.

    The previous version of this test parametrised a format and then asserted
    only `fmt != "npm-audit"` — it restated its own premise and could not have
    caught a regression in `main()` (CodeRabbit).
    """
    report = tmp_path / "python-audit.json"
    report.write_text(
        json.dumps(
            {
                "dependencies": [
                    {"name": "somepkg", "vulns": [{"id": _EXCUSED, "fix_versions": []}]},
                ]
            }
        ),
        encoding="utf-8",
    )
    exit_code = gate.main(["--format", "pip-audit", "--report", str(report), "--title", "python", "--fail-on", "any"])
    assert exit_code == 1, (
        "an npm-record advisory id must not excuse a python finding — the record "
        "is folded in for --format npm-audit only"
    )


def test_two_advisories_on_one_package_stay_independently_judgeable() -> None:
    """The hole CodeRabbit found in the first version of this change.

    A package can name several advisories; npm gives each its own `via` object.
    Emitting ONE finding per package with the union of their ids let a single
    recorded allowance excuse the package while a second, unrecorded
    high-severity advisory on it went unjudged — `not_allowed` accepts a
    finding when ANY alias matches, so the blocking gate would have returned
    success with a real finding unaddressed.
    """
    entry = {
        "severity": "high",
        "range": "*",
        "via": [
            {"url": f"https://github.com/advisories/{_EXCUSED}"},
            {"url": "https://github.com/advisories/GHSA-zzzz-yyyy-xxxx"},
        ],
    }
    findings = gate.PARSERS["npm-audit"](_report({"twofaced": entry}))
    assert len(findings) == 2, "one finding per advisory, not one per package"

    live, _ = gate.recorded_npm_allowances(today=_BEFORE_EXPIRY)
    judged = gate.not_allowed(gate.at_or_above(findings, "high"), live)
    assert [f.aliases for f in judged] == [
        ("GHSA-zzzz-yyyy-xxxx",)
    ], "the unrecorded advisory must still fail while its recorded neighbour is excused"
