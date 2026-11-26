# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The issue-link gate's decisions, exercised by running the workflow's own script.

The script block is extracted from the YAML and executed with bash rather than
reimplemented here. A second copy of the rule would drift from the first, and
then the test would be asserting the copy (#14241).

Lives in ``repo_tests/`` rather than beside the workflow: ci.yml's shard command
passes an explicit path list (``autobot-backend autobot_shared autobot-tts-worker
repo_tests tools scripts pipeline-scripts``) and ``.github/`` is not on it, so a
test placed there is collected by a bare local ``pytest`` and by nothing in CI --
present, passing locally, and never run where it matters.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

_WORKFLOW = repo_root() / ".github" / "workflows" / "pr-issue-validation.yml"


_STEP_NAME = "Validate PR issue linkage"


def _script() -> str:
    """The linkage step's shell body, selected BY NAME.

    #15492: this used to assert the job had exactly one ``run:`` step and take
    it. That held only while the job did one thing -- adding a second step
    (the same-scope batching gate) failed eight tests at once, none of them for
    a reason connected to what they assert. Selecting by name keeps the
    extraction unambiguous without pinning the job to a single step.
    """
    document = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["validate"]["steps"]
    named = [step["run"] for step in steps if step.get("name") == _STEP_NAME and "run" in step]
    assert len(named) == 1, (
        f"expected exactly one step named {_STEP_NAME!r} carrying a `run:` body, "
        f"found {len(named)}. If the step was renamed, update _STEP_NAME here too."
    )
    return named[0]


def _decide(tmp_path: Path, *, branch: str, body: str, is_fork: str = "false") -> tuple[int, str]:
    output = tmp_path / "github_output"
    output.touch()
    result = subprocess.run(
        ["bash", "-c", _script()],
        env={
            "PATH": "/usr/bin:/bin",
            "PR_BODY": body,
            "PR_BRANCH": branch,
            "PR_NUMBER": "1",
            "PR_TITLE": "test",
            "PR_IS_FORK": is_fork,
            "GITHUB_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, output.read_text(encoding="utf-8") + result.stdout


def test_the_script_block_was_actually_extracted():
    """An empty script would make bash exit 0 and every test below pass."""
    script = _script()

    assert "EXPECTED_ISSUE" in script
    assert len(script.splitlines()) > 30


# ---------------------------------------------------------------------------
# The behaviour that already worked, and must keep working
# ---------------------------------------------------------------------------


def test_a_branch_matching_its_body_passes(tmp_path):
    code, out = _decide(tmp_path, branch="issue-14241", body="Closes #14241")

    assert code == 0 and "status=success" in out


def test_a_branch_with_no_issue_token_is_skipped(tmp_path):
    """Promotion, manual and dependabot branches must never be blocked."""
    code, out = _decide(tmp_path, branch="dependabot/pip/urllib3-2.0.0", body="")

    assert code == 0 and "status=skipped" in out


def test_a_body_with_no_keyword_still_fails(tmp_path):
    code, out = _decide(tmp_path, branch="issue-14241", body="This mentions 14241 in prose.")

    assert code == 1 and "status=failure" in out


def test_a_same_repo_branch_naming_the_wrong_issue_still_fails(tmp_path):
    """The relaxation is fork-only. Renaming an in-repo branch costs nothing, so
    a mismatch there stays a real signal rather than an unfixable accident."""
    code, out = _decide(tmp_path, branch="issue-14241", body="Closes #99999")

    assert code == 1 and "status=failure" in out


# ---------------------------------------------------------------------------
# #14241 — the fork case
# ---------------------------------------------------------------------------


def test_a_fork_branch_naming_the_wrong_issue_passes_on_an_explicit_close(tmp_path):
    """The reproduction: #14146's branch was `fix/issue-13162-...` while the PR
    actually fixed #14235. A maintainer cannot rename a fork branch, so the only
    green path was linking an issue the PR did not address."""
    code, out = _decide(tmp_path, branch="fix/issue-13162-1786528649", body="Closes #14235", is_fork="true")

    assert code == 0 and "status=success" in out


def test_a_fork_with_only_refs_does_not_qualify(tmp_path):
    """`Refs` alone must not open the gate — requirement (a) already accepts it,
    so any `Refs #1` would otherwise satisfy any branch. Overriding the branch
    takes an explicit claim of closure."""
    code, out = _decide(tmp_path, branch="fix/issue-13162-1786528649", body="Refs #14235", is_fork="true")

    assert code == 1 and "status=failure" in out


def test_a_fork_with_a_bare_closing_verb_does_not_qualify(tmp_path):
    """The body must name a NUMBER, not merely use the word.

    `Refs #14235` satisfies requirement (a), so this body reaches the fork check
    with prose that says "closes" about nothing in particular. A keyword-only
    match would let that override the branch. The first version of this test used
    a body with no keyword at all, so it failed at requirement (a) and proved
    nothing about the fork path.
    """
    code, out = _decide(
        tmp_path,
        branch="fix/issue-13162-1786528649",
        body="Refs #14235. This closes the gap in the parser.",
        is_fork="true",
    )

    assert code == 1 and "status=failure" in out


def test_a_fork_naming_its_own_branch_issue_still_takes_the_normal_path(tmp_path):
    """The relaxation is a fallback, not a replacement — a correct fork PR must
    not start depending on it."""
    code, out = _decide(tmp_path, branch="fix/issue-14235-1", body="Closes #14235", is_fork="true")

    assert code == 0 and "status=success" in out and "#14241" not in out


def test_the_mva_form_is_unaffected(tmp_path):
    code, out = _decide(tmp_path, branch="issue-MVA-3244", body="Closes MVA-3244")

    assert code == 0 and "status=success" in out


def test_a_superstring_does_not_count_as_the_issue(tmp_path):
    """#19464 must not satisfy a branch implying 9464."""
    code, out = _decide(tmp_path, branch="issue-9464", body="Closes #19464")

    assert code == 1 and "status=failure" in out


# ---------------------------------------------------------------------------
# What the relaxation must NOT accept (found in review of #14251).
#
# The first version checked only that *some* closing keyword and *some* number
# appeared. It could not tell a claim from a coincidence, while the PR body
# described it as "an explicit claim naming a concrete issue".
#
# What this gate can and cannot do, stated plainly: it verifies a claim was
# MADE. It cannot verify the claim is the RIGHT one — no gate can, and the
# strict path never could either (name a branch `issue-1`, write `Closes #1`,
# and it passes today). Relevance is review's job. These tests hold the line at
# "a human wrote a deliberate reference", which is the part a machine can check.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "This encloses #14235 for context.",
        "Change discloses #14235 in the log.",
        "The handler self-closes #14235 on timeout.",
    ],
)
def test_a_word_merely_containing_a_keyword_does_not_qualify(tmp_path, body):
    """No left word boundary meant `encloses` matched `closes` as a substring."""
    code, out = _decide(tmp_path, branch="fix/issue-13162-1786528649", body=body + " Refs #14235", is_fork="true")

    assert code == 1 and "status=failure" in out


def test_a_keyword_inside_fenced_code_does_not_qualify(tmp_path):
    """A body pasting the PR template as an example is illustrating, not claiming."""
    body = "Refs #14235\n\nTemplate for future PRs:\n```\nCloses #14235\n```\n"
    code, out = _decide(tmp_path, branch="fix/issue-13162-1786528649", body=body, is_fork="true")

    assert code == 1 and "status=failure" in out


def test_a_real_claim_outside_the_fence_still_qualifies(tmp_path):
    """Stripping fenced code must not swallow a genuine claim elsewhere."""
    body = "Closes #14235\n\nExample of the old form:\n```\nRefs #1\n```\n"
    code, out = _decide(tmp_path, branch="fix/issue-13162-1786528649", body=body, is_fork="true")

    assert code == 0 and "status=success" in out


@pytest.mark.parametrize("body", ["Closes #0", "Fixes #0.", "Resolves MVA-0"])
def test_issue_zero_does_not_qualify(tmp_path, body):
    """No issue can be number zero, so this is never an author naming something."""
    code, out = _decide(tmp_path, branch="fix/issue-13162-1786528649", body=body, is_fork="true")

    assert code == 1 and "status=failure" in out


def test_the_tightening_did_not_break_the_ordinary_case(tmp_path):
    """A keyword at the very start of the body has no character to its left."""
    code, out = _decide(tmp_path, branch="fix/issue-13162-1786528649", body="Closes #14235", is_fork="true")

    assert code == 0 and "status=success" in out


def test_a_keyword_after_punctuation_still_qualifies(tmp_path):
    code, out = _decide(
        tmp_path,
        branch="fix/issue-13162-1786528649",
        body="Summary of the change.\n\n(Closes #14235)",
        is_fork="true",
    )

    assert code == 0 and "status=success" in out


# ---------------------------------------------------------------------------
# A large body must not race the pipe (printf | grep -q under pipefail: SIGPIPE)
# ---------------------------------------------------------------------------

# One env var is capped at MAX_ARG_STRLEN (128 KiB) by the kernel, so this is the
# largest body the gate can ever be handed; it is ~2x the 64 KiB pipe buffer.
_LARGE_BODY_FILLER = "x" * 120_000


def test_a_large_body_whose_link_is_on_the_first_line_passes_every_time(tmp_path):
    """`grep -q` exits on the first match; a producer still writing gets SIGPIPE and
    pipefail then reports no match. It was a race, so one run proves nothing."""
    body = "Closes #14241\n" + _LARGE_BODY_FILLER
    for attempt in range(25):
        code, out = _decide(tmp_path, branch="issue-14241", body=body)
        assert code == 0 and "status=success" in out, f"attempt {attempt}: {out[-200:]}"


# A producer piped into an early-exiting grep: `grep -q` / `--quiet`, any producer.
_PIPE_INTO_QUIET_GREP = re.compile(
    r"(?<!\|)\|(?!\|)\s*(?:e|f)?grep\s+(?:[^|;&\n]*?\s)?(?:-[A-Za-z]*q[A-Za-z]*|--quiet)\b"
)


def _pipefail_active(document: dict, job: dict, step: dict) -> bool:
    """GitHub's default `bash -e {0}` has no pipefail; `shell: bash` (or an
    explicit `set -o pipefail` in the body) does."""
    shell = step.get("shell") or job.get("defaults", {}).get("run", {}).get("shell")
    shell = shell or document.get("defaults", {}).get("run", {}).get("shell") or ""
    body = step["run"]
    return "pipefail" in body or shell.strip() == "bash" or "pipefail" in shell


def test_no_workflow_step_under_pipefail_pipes_a_producer_into_quiet_grep():
    """The class, not the instance: any `producer | grep -q` in a run block whose
    shell has pipefail. A step with no pipefail (the default shell) is exempt: there
    the pipeline status is grep's alone, so an early exit cannot fail it."""
    offenders = []
    for path in sorted((repo_root() / ".github" / "workflows").glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_id, job in (document.get("jobs") or {}).items():
            for step in job.get("steps", []) if isinstance(job, dict) else []:
                if "run" not in step or not _pipefail_active(document, job, step):
                    continue
                joined = step["run"].replace("\\\n", " ")
                for line in joined.splitlines():
                    if not line.lstrip().startswith("#") and _PIPE_INTO_QUIET_GREP.search(line):
                        offenders.append(f"{path.name}:{job_id}:{step.get('name')}: {line.strip()[:80]}")

    assert not offenders, f"producer piped into grep -q under pipefail: {offenders}"


_SET_PIPEFAIL = re.compile(r"\bset\s+(?:-\w+\s+)*-\w*o\s+pipefail")


# Piped input is a few bytes of fixed text, far below the pipe buffer, so the producer
# cannot be mid-write when grep exits; the `$?` of the pipeline is what each case asserts.
_FIXED_INPUT_SCRIPTS = {"fleet-ip-rule_test.sh"}


def _logical_lines(text: str) -> list[str]:
    """Join `\\` continuations and lines ending in a pipe, so `cmd \\ \\n | grep -q` is one line."""
    joined = re.sub(r"\\\n\s*", " ", text)
    joined = re.sub(r"(?<!\|)\|\s*\n\s*", "| ", joined)
    return joined.splitlines()


def test_no_shell_script_under_pipefail_pipes_a_producer_into_quiet_grep():
    """The script half of the class: a file with `set -o pipefail` (any flag mix) must
    not pipe a producer into `grep -q`, including across a continued line."""
    offenders = []
    for path in sorted((repo_root() / "scripts").rglob("*.sh")):
        if path.name in _FIXED_INPUT_SCRIPTS:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not _SET_PIPEFAIL.search(text):
            continue
        for line in _logical_lines(text):
            if not line.lstrip().startswith("#") and _PIPE_INTO_QUIET_GREP.search(line):
                offenders.append(f"{path.relative_to(repo_root())}: {line.strip()[:90]}")

    assert not offenders, f"producer piped into grep -q under pipefail: {offenders}"
