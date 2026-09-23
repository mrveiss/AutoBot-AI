# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The split durations must actually land, and their age must be visible (#17313).

`test-durations.yml` measured the suite every week for months and uploaded the
result as an artifact. Nothing committed it. The workflow was named "Measure and
store", the files it was supposed to store aged 37 and 51 days, and both were
last written by ordinary feature PRs rather than by the workflow that owns them.

Nothing reported that, which is the actual defect: pytest-split gives every
unknown test the mean duration, so the split decays quietly and the only symptom
is CI slowly getting slower.

Two things are pinned here. The age, because that is the state that matters --
and the automation, because an age check alone would take three months to notice
that the landing job had been deleted.
"""

from __future__ import annotations

import datetime
import subprocess

import pytest
import yaml
from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

WORKFLOW = repo_root() / ".github" / "workflows" / "test-durations.yml"
DURATIONS = (".test_durations", ".test_durations_slm")

#: A rot floor, not a target. The weekly cron should keep these under ~10 days;
#: 90 is the point past which the timings describe a suite that no longer
#: exists. Set wide on purpose -- a threshold that fires on ordinary lateness
#: gets muted, and a muted guard is worse than none.
MAX_AGE_DAYS = 90


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _land_script() -> str:
    """The landing step's shell body, read as written.

    Not ``yaml.dump`` of the job: re-encoding escapes ``$`` and rewraps lines,
    so assertions against the dump passed or failed on the serialiser's choices
    rather than on the script.
    """
    for step in _workflow()["jobs"]["land"]["steps"]:
        if "run" in step:
            return step["run"]
    raise AssertionError("the landing job has no run step")


def _last_committed(path: str) -> datetime.date:
    out = subprocess.run(
        ["git", "-C", str(repo_root()), "log", "-1", "--format=%ad", "--date=short", "--", path],
        capture_output=True,
        text=True,
        env=scrubbed_git_env(),
    )
    stamp = out.stdout.strip()
    # A check that cannot look must not report clean: no commit date means the
    # file is untracked or the log failed, and neither is "the file is fresh".
    assert stamp, f"could not read a commit date for {path} -- the freshness of this file is UNKNOWN, not fine"
    return datetime.date.fromisoformat(stamp)


@pytest.mark.parametrize("path", DURATIONS)
def test_the_durations_are_not_older_than_the_rot_floor(path: str) -> None:
    age = (datetime.date.today() - _last_committed(path)).days
    print(f"{path}: last committed {_last_committed(path)} ({age} days ago)")
    assert age <= MAX_AGE_DAYS, (
        f"{path} was last committed {age} days ago, past the {MAX_AGE_DAYS}-day floor. "
        "The weekly run should be landing these; check that test-durations.yml's `land` job is succeeding."
    )


def test_a_job_lands_the_durations_without_a_human_step() -> None:
    """The gap this issue was filed for: measuring is not storing."""
    jobs = _workflow()["jobs"]
    assert "land" in jobs, "test-durations.yml has no landing job -- a refresh would go nowhere again"
    land = jobs["land"]
    assert land.get("needs") == "store-durations", "the landing job must consume the measuring job's result"
    assert "gh pr create" in _land_script(), "the landing job must open a PR rather than leave an artifact"


def test_the_landing_job_runs_on_the_scheduled_refresh() -> None:
    """A landing job wired only to pull_request would never fire on the cron."""
    condition = " ".join(_workflow()["jobs"]["land"]["if"].split())
    for event in ("schedule", "workflow_dispatch"):
        assert event in condition, f"the landing job does not run on {event}"


def test_the_suite_job_never_holds_a_write_token() -> None:
    """Split for this reason, so a later merge must not quietly recombine them.

    The measuring job runs the entire test suite. Giving it `contents: write`
    would put a repository-write token within reach of any test, fixture or
    transitive import in that run.
    """
    jobs = _workflow()["jobs"]
    measure_perms = jobs["store-durations"].get("permissions")
    assert measure_perms in (
        None,
        {"contents": "read"},
    ), f"the suite-running job declares {measure_perms!r}; it must not hold write scope"
    assert jobs["land"]["permissions"]["contents"] == "write", "the landing job needs write scope to land anything"


def test_an_empty_or_truncated_durations_file_is_refused() -> None:
    """Committing an empty file over a good one is worse than staleness.

    pytest-split would then give every test the mean, so the split would be
    worse than the stale data it replaced.
    """
    script = _land_script()
    assert '[ -s "$f" ]' in script, "no emptiness check before committing"
    assert "fewer than 100 timings" in script, "no check that the run actually measured the suite"


def test_the_landing_script_is_valid_shell() -> None:
    """The check whose absence let a broken heredoc reach CI.

    Everything else here inspects the workflow as data -- YAML parses, the job
    is wired, the body renders. None of that runs the shell, so a heredoc whose
    terminator is indented one level too deep, and a duplicate `fi`, both passed
    every assertion in this file while `bash -n` reported "here-document
    delimited by end-of-file". The step would have died at runtime on the
    schedule path, which is the one path that matters: the durations PR would
    never have opened, and the failure would have looked like the silence this
    whole issue is about.

    Found by a peer session reviewing the branch, not by these tests.
    """
    script = _land_script()
    proc = subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True)
    assert proc.returncode == 0, f"the landing script is not valid shell:\n{proc.stderr}"
