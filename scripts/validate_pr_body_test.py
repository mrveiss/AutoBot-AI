# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the local PR-body validator (#16859).

``validate()`` must call the SAME functions CI calls, not a reimplementation --
that is the whole point of this script, so the tests that matter most assert
the gate functions are actually invoked (patched and checked for a call),
not just that some plausible-looking result comes back. The CLI tests below
that cover ``--pr`` never hit the network: ``subprocess.run`` is patched.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_pr_body import (  # noqa: E402
    _SUBJECT_EXEMPT_PREFIXES,
    _SUBJECT_RE,
    PRLookupError,
    _load_subject_pattern,
    check_title,
    main,
    pr_fields,
    validate,
)

_GOOD_BODY = (
    "## Thinking Path\nreasoning\n\n"
    "## What Changed\nstuff\n\n"
    "## Single-issue rationale\nnarrow fix\n\n"
    "## Verification\ntests pass\n\n"
    "## Model Used\nOpus 5\n\n"
    "Closes #1\n"
)

_MISSING_HEADINGS_BODY = "## Summary\nstuff\n\nCloses #1\n"


def _run(*args: str, capsys: pytest.CaptureFixture) -> tuple[int, str]:
    exit_code = main(list(args))
    return exit_code, capsys.readouterr().out


# ---------------------------------------------------------------------------
# validate(): must call the real gates, not reimplement them
# ---------------------------------------------------------------------------


def test_validate_calls_every_real_gate_function():
    """The point of this script is dispatch, not a third rule set.

    Patched at the point ``validate_pr_body`` imported them, so a body that
    would pass CI's own gates must pass here through the identical code path.
    check_title is local rather than imported, so it is exercised for real.
    """
    with (
        patch("validate_pr_body.check_template_sections", return_value=(True, ["ok"])) as sections,
        patch("validate_pr_body.check_batching", return_value=(True, "ok")) as batching,
    ):
        assert validate("anything", actor="a", branch="b", title="fix(x): y (#1234)") is True

    sections.assert_called_once_with("anything")
    batching.assert_called_once_with("anything", actor="a", branch="b", title="fix(x): y (#1234)")


def test_validate_fails_on_a_title_that_cannot_become_a_commit_subject():
    """#15473: the squash subject comes from the title, and nothing checked it.

    Both other gates are forced green, so only the title can decide the verdict.
    """
    with (
        patch("validate_pr_body.check_template_sections", return_value=(True, ["ok"])),
        patch("validate_pr_body.check_batching", return_value=(True, "ok")),
    ):
        assert validate("anything", actor="a", branch="b", title="fix(deps+security): x (#17304)") is False


def test_validate_fails_when_either_gate_fails():
    with (
        patch("validate_pr_body.check_template_sections", return_value=(False, [])),
        patch("validate_pr_body.check_batching", return_value=(True, "ok")),
    ):
        assert validate("x") is False
    with (
        patch("validate_pr_body.check_template_sections", return_value=(True, [])),
        patch("validate_pr_body.check_batching", return_value=(False, "no")),
    ):
        assert validate("x") is False


def test_a_genuinely_complete_body_passes():
    """End-to-end against the real gates, not mocked -- the body a correct
    author would actually write."""
    assert validate(_GOOD_BODY) is True


def test_wrong_headings_fail():
    assert validate(_MISSING_HEADINGS_BODY) is False


def test_single_closing_keyword_without_rationale_now_passes_with_a_warning():
    """#17128: the batching gate's own rule is advisory now -- a single Closes
    with no stated reason still gets the guidance (as a `::warning::`, printed
    by ``check_batching`` itself), but no longer fails the local validator."""
    body = "## Thinking Path\nx\n\n## What Changed\nx\n\n## Verification\nx\n\n" "## Model Used\nx\n\nCloses #1\n"
    assert validate(body) is True


# ---------------------------------------------------------------------------
# pr_fields(): field mapping must match pr-issue-validation.yml exactly
# ---------------------------------------------------------------------------


def test_pr_fields_maps_gh_json_to_the_ci_field_names():
    payload = {
        "body": "## Thinking Path\n...",
        "author": {"login": "mrveiss"},
        "headRefName": "issue-16859-pr-body-check",
        "title": "fix: wire the body gates into pre-push",
        "baseRefName": "main",
    }
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload), stderr="")
    with patch("validate_pr_body.subprocess.run", return_value=completed) as run:
        fields = pr_fields("16859")

    assert fields == {
        "body": payload["body"],
        "actor": "mrveiss",
        "branch": "issue-16859-pr-body-check",
        "title": payload["title"],
        "base": "main",
    }
    args = run.call_args.args[0]
    assert args[:3] == ["gh", "pr", "view"]
    assert "16859" in args


def test_pr_fields_tolerates_missing_optional_json_keys():
    """A PR with no author on record (deleted account) must not crash the lookup."""
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps({"body": None}), stderr="")
    with patch("validate_pr_body.subprocess.run", return_value=completed):
        fields = pr_fields("16859")
    assert fields == {"body": "", "actor": "", "branch": "", "title": "", "base": ""}


def test_pr_fields_raises_when_gh_is_missing():
    with patch("validate_pr_body.subprocess.run", side_effect=FileNotFoundError()):
        with pytest.raises(PRLookupError, match="gh CLI not found"):
            pr_fields("16859")


def test_pr_fields_raises_on_gh_failure_with_stderr_in_the_message():
    """The failure has to say WHY, not just that it failed -- otherwise a
    real 'no such PR' and a transient network error read identically."""
    err = subprocess.CalledProcessError(1, ["gh"], stderr="no pull requests found for branch")
    with patch("validate_pr_body.subprocess.run", side_effect=err):
        with pytest.raises(PRLookupError, match="no pull requests found"):
            pr_fields("no-such-branch")


def test_pr_fields_raises_on_timeout():
    with patch(
        "validate_pr_body.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["gh"], timeout=30),
    ):
        with pytest.raises(PRLookupError, match="timed out"):
            pr_fields("16859")


def test_pr_fields_raises_on_unparseable_json():
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="not json", stderr="")
    with patch("validate_pr_body.subprocess.run", return_value=completed):
        with pytest.raises(PRLookupError, match="unparseable"):
            pr_fields("16859")


# ---------------------------------------------------------------------------
# main(): CLI dispatch
# ---------------------------------------------------------------------------


def test_main_file_mode_exits_zero_on_a_good_body(tmp_path, capsys):
    body_file = tmp_path / "body.md"
    body_file.write_text(_GOOD_BODY, encoding="utf-8")
    exit_code, _ = _run("--file", str(body_file), capsys=capsys)
    assert exit_code == 0


def test_main_file_mode_exits_one_on_a_bad_body(tmp_path, capsys):
    body_file = tmp_path / "body.md"
    body_file.write_text(_MISSING_HEADINGS_BODY, encoding="utf-8")
    exit_code, out = _run("--file", str(body_file), capsys=capsys)
    assert exit_code == 1
    assert "Thinking Path" in out


def test_main_file_mode_reports_a_missing_file_without_a_traceback(tmp_path, capsys):
    missing = tmp_path / "does-not-exist.md"
    exit_code, _ = _run("--file", str(missing), capsys=capsys)
    assert exit_code == 1


def test_main_pr_mode_uses_the_fetched_fields(capsys):
    payload = {
        "body": _GOOD_BODY,
        "author": {"login": "mrveiss"},
        "headRefName": "b",
        "title": "fix(scope): a conforming subject (#16859)",
        "baseRefName": "main",
    }
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload), stderr="")
    with patch("validate_pr_body.subprocess.run", return_value=completed):
        exit_code, _ = _run("--pr", "16859", capsys=capsys)
    assert exit_code == 0


def test_main_pr_mode_surfaces_the_lookup_failure_as_an_error_not_a_crash(capsys):
    err = subprocess.CalledProcessError(1, ["gh"], stderr="no pull requests found")
    with patch("validate_pr_body.subprocess.run", side_effect=err):
        exit_code, out = _run("--pr", "999999", capsys=capsys)
    assert exit_code == 1
    assert "no pull requests found" in out


def test_file_and_pr_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        main(["--file", "x", "--pr", "1"])


def test_one_of_file_or_pr_is_required():
    with pytest.raises(SystemExit):
        main([])


# ---------------------------------------------------------------------------
# check_title(): the squash-merge subject (#15473)
# ---------------------------------------------------------------------------

_LINT_CONVENTIONS = Path(__file__).resolve().parent / "lint-conventions.sh"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("fix(deps): bump a pinned floor (#17304)", True),
        ("fix(llc/frontend): slashed scopes are real here (#123)", True),
        ("docs(architecture,design): comma-joined scope (#123)", True),
        ("tech-debt: hyphenated type, no scope (#123)", True),
        ("Merge branch 'main' into release", True),
        ('Revert "fix(x): y (#1)"', True),
        ("chore: claim worktree for #123", True),
        ("", True),
        # The one that landed on main and then failed the range check for
        # every PR after it: `+` is not in the scope class.
        ("fix(deps+security): close alerts (#17304)", False),
        ("fix(/llc): scope may not start with a separator (#123)", False),
        ("Fix(deps): capitalised type (#123)", False),
        ("no type at all (#123)", False),
        ("fix(deps): conforming but no issue reference", False),
        ("fix(deps): issue number too short (#12)", False),
        ("fixup! fix(deps): a local WIP form is not a PR title", False),
    ],
)
def test_check_title_verdicts(title: str, expected: bool) -> None:
    ok, message = check_title(title)
    assert ok is expected, message
    assert message, "every verdict explains itself"


def test_check_title_never_echoes_a_bare_failure() -> None:
    """A rejection has to say what to do; a bare 'invalid' gets worked around."""
    _, message = check_title("fix(deps+security): close alerts (#17304)")
    assert "squash merge" in message.lower()
    assert "'+' is not a separator" in message


def test_the_subject_pattern_has_one_source_and_both_gates_read_it() -> None:
    """#15473 AC: the regex is SHARED, not restated.

    A drift test would only report a second copy after someone wrote one. This
    asserts there is no second copy to drift: the shell reads the file by name,
    this module compiles that same file, and neither carries the pattern inline.
    """
    shell = _LINT_CONVENTIONS.read_text(encoding="utf-8")
    assert "lib/commit-subject.ere" in shell, "lint-conventions.sh no longer reads the shared rule"
    assert (
        shell.count('grep -qE "$SUBJECT_ERE"') == 2
    ), "both the commit-msg and the range subject check must use the shared pattern"
    inlined = re.findall(r"grep -qE '\^\[a-z\][^']*'", shell)
    assert not inlined, f"lint-conventions.sh has re-inlined the subject pattern: {inlined}"

    ere_file = Path(__file__).resolve().parent / "lib" / "commit-subject.ere"
    raw = ere_file.read_text(encoding="utf-8")
    lines = [ln for ln in (x.strip() for x in raw.splitlines()) if ln and not ln.startswith("#")]
    assert lines == [_SUBJECT_RE.pattern]


@pytest.mark.parametrize(
    ("content", "why"),
    [
        ("", "an empty rule file"),
        ("# only comments\n", "a rule file with no pattern"),
        ("^a: .+\n^b: .+\n", "two patterns, so which one governs is unknowable"),
    ],
)
def test_an_unusable_rule_file_raises_rather_than_falling_back(tmp_path, content: str, why: str) -> None:
    """A subject rule that cannot be loaded must never read as a subject that passes."""
    bad = tmp_path / "commit-subject.ere"
    bad.write_text(content, encoding="utf-8")
    with pytest.raises(RuntimeError):
        _load_subject_pattern(bad)


def test_a_missing_rule_file_raises_rather_than_falling_back(tmp_path) -> None:
    with pytest.raises(RuntimeError):
        _load_subject_pattern(tmp_path / "does-not-exist.ere")


def test_the_exempt_prefixes_have_not_drifted_from_range_mode() -> None:
    shell = _LINT_CONVENTIONS.read_text(encoding="utf-8")
    cases = re.findall(r'^\s*("Merge "\*\|[^)]*)\)\s*continue\s*;;\s*$', shell, re.MULTILINE)
    assert len(cases) == 1, f"expected exactly one range-mode subject exemption, found {len(cases)}"
    shell_prefixes = tuple(pat.rstrip("*").strip('"').replace("\\ ", " ") for pat in cases[0].split("|"))
    assert shell_prefixes == _SUBJECT_EXEMPT_PREFIXES


def test_a_promotion_pr_skips_the_title_gate_and_says_why() -> None:
    """#15473: a main -> release promotion is merged, not squashed.

    Its title never becomes a commit subject, so judging it as one is wrong --
    and it red-flagged the real promotion PR, whose title correctly carries no
    issue reference because a promotion is not an issue fix.
    """
    with (
        patch("validate_pr_body.check_template_sections", return_value=(True, ["ok"])),
        patch("validate_pr_body.check_batching", return_value=(True, "ok")),
    ):
        assert validate("anything", title="chore(release): promote main to release", base="release") is True


def test_the_promotion_skip_is_not_the_default() -> None:
    """A default that skipped would leave every ordinary PR unguarded.

    --file mode has no PR to read a base from, so the default must be the
    squash-merged case, which is all but the promotion PRs.
    """
    with (
        patch("validate_pr_body.check_template_sections", return_value=(True, ["ok"])),
        patch("validate_pr_body.check_batching", return_value=(True, "ok")),
    ):
        assert validate("anything", title="chore(release): promote main to release") is False


def test_the_workflow_job_skips_promotions_the_same_way() -> None:
    """Two enforcers again: the hook reads `base`, the workflow reads base.ref.

    If only one of them skips, a promotion PR is either red in CI or red at
    push -- and the one that is wrong is the one nobody is looking at.
    """
    workflow = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "pr-template-check.yml"
    condition = " ".join(yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"]["check-title"]["if"].split())
    assert "github.event.pull_request.base.ref == 'main'" in condition
    # #15473 review: check-template's fork skip must NOT be copied here. A
    # squash subject is permanent; a template convention is not.
    assert (
        "head.repo.full_name" not in condition
    ), "check-title must not skip fork PRs -- their titles become permanent subjects too"
