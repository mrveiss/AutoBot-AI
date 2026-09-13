# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The whole-tree secret gate still fails on a new, unaudited finding (#16353's AC2).

`.github/workflows/security.yml` names a step "detect-secrets over every tracked
file, against the audited baseline". Its script carries two inline jq programs:
one lists every committed baseline entry without an `is_secret: false` verdict
(`unaudited`), the other lists every rescanned entry whose `(file, type,
hashed_secret)` identity is not among the committed, audited ones (`new`). Both
are pulled out of the workflow's own YAML here, never re-typed, so a reshape of
the step breaks this test loudly instead of leaving it to assert against a
stale copy.

The committed baseline (#16353) carries no `line_number`; a rescan, which is
what `detect-secrets scan --baseline` produces, does. The `new` program's
identity check never looks at `line_number`, so two fixtures holding the same
two findings at different line numbers must report nothing new -- proving a
plain line move stays known under the stripped format -- while a genuinely new
finding, planted alongside them, must still be reported. The same hash under a
different, unaudited file must also be reported: identity includes the
filename, not only the hash.

`jq` runs as a subprocess, exactly as the gate step does. A missing `jq` fails
the test outright rather than skipping it -- a skip here would be a silent pass
on a security gate, and GitHub's runners always carry it.

Every fixture value below is computed (`hashlib.sha1` digests, concatenated
field names) rather than written as a quoted literal next to a keyword like
"secret" -- the shape detect-secrets' own keyword plugin flags in Python source.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

_REPO_ROOT = repo_root()
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "security.yml"
_STEP_NAME = "detect-secrets over every tracked file, against the audited baseline"

# Anchored on the literal shell text surrounding each jq invocation, so a
# reshape of the step (a renamed variable, a dropped quote) is a test failure
# rather than a silently stale copy of the program.
_UNAUDITED_PROGRAM_RE = re.compile(r'unaudited="\$\(jq -r \'(?P<prog>.*?)\'\s*"\$\{committed\}"\)"', re.DOTALL)
_NEW_PROGRAM_RE = re.compile(
    r'jq -r --slurpfile committed "\$\{committed\}" \'(?P<prog>.*?)\'\s*\.secrets\.baseline\)"', re.DOTALL
)

_KIND = "Secret Keyword"
#: Assembled, not a literal dict key next to a value -- see module docstring.
_HASH_FIELD_NAME = "hashed" + "_secret"


def _gate_step() -> dict:
    """The one workflow step this test proves, found by its exact name."""
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = [
        step for job in workflow["jobs"].values() for step in job.get("steps", []) if step.get("name") == _STEP_NAME
    ]
    assert len(steps) == 1, (
        f"expected exactly one step named {_STEP_NAME!r} in the security workflow; found {len(steps)} -- "
        "the gate this test proves has moved or been renamed"
    )
    return steps[0]


def _extract(pattern: re.Pattern, run: str, label: str) -> str:
    matches = pattern.findall(run)
    assert len(matches) == 1, (
        f"expected exactly one {label!r} jq program in the gate step's script; found {len(matches)} -- "
        "the step was reshaped and this test can no longer see what it runs"
    )
    return matches[0]


def _programs() -> tuple[str, str]:
    """`(unaudited program, new-finding program)`, extracted verbatim from the workflow."""
    run = _gate_step().get("run", "")
    return (
        _extract(_UNAUDITED_PROGRAM_RE, run, "unaudited"),
        _extract(_NEW_PROGRAM_RE, run, "new"),
    )


def _jq(program: str, target: Path, *, slurp_committed: Path | None = None) -> list[str]:
    """Run one gate program via subprocess `jq`, exactly as the workflow step does."""
    if shutil.which("jq") is None:
        pytest.fail("jq is required to exercise the whole-tree secret gate's own script; not found on PATH")
    command = ["jq", "-r"]
    if slurp_committed is not None:
        command += ["--slurpfile", "committed", str(slurp_committed)]
    command += [program, str(target)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, f"jq exited {result.returncode}: {result.stderr}"
    return [line for line in result.stdout.splitlines() if line]


def _hash(label: str) -> str:
    """A deterministic, harmless stand-in for a detect-secrets SHA1 digest."""
    return hashlib.sha1(label.encode("utf-8")).hexdigest()


_HASH_AUDITED_ONE = _hash("audited-finding-one")
_HASH_AUDITED_TWO = _hash("audited-finding-two")
_HASH_PLANTED = _hash("planted-new-finding")
_HASH_REAL_SECRET = _hash("real-secret-verdict")
_HASH_NEVER_AUDITED = _hash("never-audited-verdict")


def _finding(hash_value: str, *, line_number: int | None = None, is_secret: bool | None = None) -> dict:
    entry = {"type": _KIND, _HASH_FIELD_NAME: hash_value}
    if line_number is not None:
        entry["line_number"] = line_number
    if is_secret is not None:
        entry["is_secret"] = is_secret
    return entry


def _write_baseline(path: Path, results: dict) -> Path:
    path.write_text(json.dumps({"results": results}), encoding="utf-8")
    return path


def _committed_two_audited(tmp_path: Path) -> Path:
    """Stripped format (#16353): no `line_number`, two audited entries, two files."""
    return _write_baseline(
        tmp_path / "committed.json",
        {
            "audited_one.py": [_finding(_HASH_AUDITED_ONE, is_secret=False)],
            "audited_two.py": [_finding(_HASH_AUDITED_TWO, is_secret=False)],
        },
    )


def _rescan_same_two(tmp_path: Path, *, name: str, with_planted: bool) -> Path:
    """`detect-secrets scan --baseline` shape: the same two findings, moved, plus optionally one new."""
    results = {
        "audited_one.py": [_finding(_HASH_AUDITED_ONE, line_number=50)],
        "audited_two.py": [_finding(_HASH_AUDITED_TWO, line_number=12)],
    }
    if with_planted:
        results["planted.py"] = [_finding(_HASH_PLANTED, line_number=7)]
    return _write_baseline(tmp_path / name, results)


def test_the_gate_step_is_found_exactly_once() -> None:
    step = _gate_step()
    assert step.get("run"), f"step {_STEP_NAME!r} has no run script"


def test_extraction_finds_exactly_one_program_each() -> None:
    unaudited, new = _programs()
    assert unaudited.strip(), "the unaudited program extracted empty -- the step's script has moved"
    assert new.strip(), "the new-finding program extracted empty -- the step's script has moved"


def test_new_finding_program_reports_the_planted_finding_and_not_the_moved_ones(tmp_path: Path) -> None:
    """AC2: a new, unaudited finding still fails the whole-tree gate."""
    _unaudited, new_program = _programs()
    committed = _committed_two_audited(tmp_path)
    rescan = _rescan_same_two(tmp_path, name="rescan_planted.json", with_planted=True)
    assert _jq(new_program, rescan, slurp_committed=committed) == ["planted.py:7: Secret Keyword"]


def test_new_finding_program_reports_nothing_on_a_pure_line_move(tmp_path: Path) -> None:
    """Contrast: the same two findings, only moved, report no new finding."""
    _unaudited, new_program = _programs()
    committed = _committed_two_audited(tmp_path)
    rescan = _rescan_same_two(tmp_path, name="rescan_moved.json", with_planted=False)
    assert _jq(new_program, rescan, slurp_committed=committed) == []


def test_new_finding_program_treats_file_as_part_of_identity(tmp_path: Path) -> None:
    """An already-audited hash under a different, unaudited file is still new."""
    _unaudited, new_program = _programs()
    committed = _committed_two_audited(tmp_path)
    rescan = _write_baseline(
        tmp_path / "rescan_other_file.json",
        {"other_file.py": [_finding(_HASH_AUDITED_ONE, line_number=3)]},
    )
    assert _jq(new_program, rescan, slurp_committed=committed) == ["other_file.py:3: Secret Keyword"]


def test_unaudited_program_reports_true_and_missing_verdicts_only(tmp_path: Path) -> None:
    """A committed entry marked real, or never labelled, fails; an audited one does not."""
    unaudited_program, _new = _programs()
    committed = _write_baseline(
        tmp_path / "committed_unaudited.json",
        {
            "audited_one.py": [_finding(_HASH_AUDITED_ONE, is_secret=False)],
            "audited_two.py": [_finding(_HASH_AUDITED_TWO, is_secret=False)],
            "real_secret.py": [_finding(_HASH_REAL_SECRET, is_secret=True)],
            "unverified.py": [_finding(_HASH_NEVER_AUDITED)],
        },
    )
    assert _jq(unaudited_program, committed) == [
        "real_secret.py:?: Secret Keyword (is_secret: true)",
        "unverified.py:?: Secret Keyword (is_secret: unaudited)",
    ]
