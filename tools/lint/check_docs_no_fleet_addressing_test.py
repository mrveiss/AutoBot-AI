#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Discrimination tests for the #15208 documentation fleet-addressing guard.

No fixture here quotes a fleet address. Each one is *derived* from the canonical
``HV_VM_IP`` pattern the guard itself loads, so this file cannot drift from the rule
it tests and adds no second copy of the range to the repository — the same reason the
guard parses the pattern instead of restating it.

The reach-floor tests are the contrast mutation for the sweep: narrowing discovery back
to a single directory, the way #3315's sweep was scoped, must fail on the floor rather
than report a comfortable "no offenders" over a handful of files.
"""

from __future__ import annotations

import pathlib
import re
import textwrap

import pytest

from tools.lint import check_docs_no_fleet_addressing as guard

RULES_BODY = "HV_VM_IP='{pattern}'\n"


def _canonical_pattern() -> str:
    """The fleet-address regex as the repository defines it, read once."""
    return guard.fleet_address_pattern().pattern


def _sample_address() -> str:
    """A literal that the canonical pattern matches, built from the pattern itself."""
    literal = re.sub(r"\[0-9\]\+$", "17", _canonical_pattern().replace("\\", ""))
    assert guard.fleet_address_pattern().search(literal), literal
    return literal


def _base(tmp_path: pathlib.Path, docs: dict[str, str]) -> pathlib.Path:
    """A miniature repository: the canonical rule set plus the given documents."""
    rules = tmp_path / guard.RULES_REL
    rules.parent.mkdir(parents=True, exist_ok=True)
    rules.write_text(RULES_BODY.format(pattern=_canonical_pattern()), encoding="utf-8")
    for rel, body in docs.items():
        path = tmp_path / guard.DOCS_DIR / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body), encoding="utf-8")
    return tmp_path


def _padding(count: int, prefix: str = "pad") -> dict[str, str]:
    """Enough clean documents to clear the discovery floor."""
    return {f"{prefix}/doc_{i}.md": "# Clean\n\nNothing to see.\n" for i in range(count)}


def _scan(text: str):
    return guard.scan_document("docs/x.md", text, guard.fleet_address_pattern())


# ── detection ────────────────────────────────────────────────────────────────


def test_flags_a_literal_address_in_prose():
    findings, problems = _scan(f"# Doc\n\nRedis runs on {_sample_address()} in the fleet.\n")
    assert [f.lineno for f in findings] == [3]
    assert problems == []


def test_flags_a_literal_address_inside_a_fenced_code_block():
    body = f"# Doc\n\n```bash\nssh autobot@{_sample_address()}\n```\n"
    findings, _ = _scan(body)
    assert [f.lineno for f in findings] == [4]


def test_a_role_placeholder_is_not_a_finding():
    findings, problems = _scan("# Doc\n\nRedis runs on `<database-ip>` in the fleet.\n")
    assert findings == []
    assert problems == []


def test_findings_never_echo_the_matched_address():
    findings, _ = _scan(f"# Doc\n\nRedis runs on {_sample_address()}.\n")
    rendered = guard._format_findings(findings)
    assert _sample_address() not in rendered
    assert "docs/x.md:3" in rendered


# ── structural exemptions ────────────────────────────────────────────────────


def test_block_marker_exempts_the_block_it_introduces():
    body = (
        "# Doc\n\n"
        f"<!-- {guard.EXEMPT_BLOCK}: documents the pattern the hook matches -->\n\n"
        f"- Hardcoded VM IPs (`{_sample_address()}`)\n"
    )
    findings, problems = _scan(body)
    assert findings == []
    assert problems == []


def test_block_marker_does_not_cover_a_later_block():
    body = (
        "# Doc\n\n"
        f"<!-- {guard.EXEMPT_BLOCK}: counter-example -->\n\n"
        f"- Hardcoded VM IPs (`{_sample_address()}`)\n\n"
        f"The database endpoint is {_sample_address()}:5432.\n"
    )
    findings, _ = _scan(body)
    assert [f.lineno for f in findings] == [7]


def test_stranded_block_marker_is_a_finding():
    body = f"# Doc\n\n<!-- {guard.EXEMPT_BLOCK}: nothing here -->\n\nOrdinary prose.\n"
    _, problems = _scan(body)
    assert any("stranded" in p for p in problems)


def test_file_marker_exempts_the_whole_file():
    body = (
        f"<!-- {guard.EXEMPT_FILE}: this document is the rule's own reference -->\n\n"
        f"# Doc\n\nOne {_sample_address()} here and another {_sample_address()} there.\n"
    )
    findings, problems = _scan(body)
    assert findings == []
    assert problems == []


def test_stranded_file_marker_is_a_finding():
    body = f"<!-- {guard.EXEMPT_FILE}: stale claim -->\n\n# Doc\n\nNo address at all.\n"
    _, problems = _scan(body)
    assert any("stranded" in p for p in problems)


# ── pattern provenance ───────────────────────────────────────────────────────


def test_pattern_comes_from_the_canonical_rule_set(tmp_path):
    base = _base(tmp_path, {})
    assert guard.fleet_address_pattern(base).pattern == _canonical_pattern()


def test_missing_rule_set_aborts_rather_than_reporting_clean(tmp_path):
    (tmp_path / guard.DOCS_DIR).mkdir(parents=True)
    with pytest.raises(RuntimeError, match="cannot read the canonical rule set"):
        guard.fleet_address_pattern(tmp_path)


def test_rule_set_without_the_assignment_aborts(tmp_path):
    rules = tmp_path / guard.RULES_REL
    rules.parent.mkdir(parents=True, exist_ok=True)
    rules.write_text("# no assignment here\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="no HV_VM_IP assignment"):
        guard.fleet_address_pattern(tmp_path)


# ── reach floor (the contrast mutation) ──────────────────────────────────────


def test_audit_is_clean_when_the_floor_is_met_and_nothing_offends(tmp_path):
    base = _base(tmp_path, _padding(guard.DISCOVERY_FLOOR))
    reached, problems = guard.audit(base)
    assert reached == guard.DISCOVERY_FLOOR
    assert problems == []


def test_audit_fails_on_the_floor_when_discovery_is_narrowed(tmp_path, monkeypatch):
    """#3315's scope, applied to this guard: a sweep that stops finding files must fail.

    Discovery is narrowed to one subdirectory — the shape of the original sweep — over a
    tree that contains no offender at all. Without the floor the run reports success
    having checked almost nothing, which is the failure #15208 was filed for.
    """
    base = _base(tmp_path, {**_padding(guard.DISCOVERY_FLOOR), **_padding(3, prefix="architecture")})
    monkeypatch.setattr(
        guard,
        "discover_markdown_files",
        lambda b=None: sorted((base / guard.DOCS_DIR / "architecture").rglob("*.md")),
    )
    reached, problems = guard.audit(base)
    assert reached == 3
    assert any("floor" in p for p in problems)


def test_audit_fails_on_the_floor_when_docs_is_absent(tmp_path):
    base = _base(tmp_path, {})
    reached, problems = guard.audit(base)
    assert reached == 0
    assert any("floor" in p for p in problems)


# ── the repository itself ────────────────────────────────────────────────────


def test_repository_documentation_carries_no_unexempted_fleet_address():
    reached, problems = guard.audit()
    assert reached >= guard.DISCOVERY_FLOOR
    assert problems == [], "\n\n".join(problems)


def test_main_reports_a_nonzero_exit_for_a_leaking_file(tmp_path, monkeypatch):
    base = _base(tmp_path, {"leak.md": f"# Doc\n\nEndpoint {_sample_address()}:5432.\n"})
    monkeypatch.setattr(guard, "repo_root", lambda: base)
    assert guard.main([str(base / guard.DOCS_DIR / "leak.md")]) == 1
