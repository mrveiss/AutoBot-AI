# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The release workflow is told its range, and says so when it sees none (#13835).

A 269-commit promotion to `main` produced no release: the run reported success,
git-cliff returned the current version, and the guard exited 0. The promotion
lands as a merge commit, so the first-parent range from the previous tag is
exactly one commit — the merge — which `cliff.toml` skips via
``{ message = "^Merge ", skip = true }``.

Two properties are pinned here. The range is passed explicitly, so the walk
semantics stop mattering. And a "nothing to release" outcome with commits in
range is an **error**, not a quiet success — that silence is why a release that
never happened looked like one that did.
"""

import pathlib
import subprocess

import yaml

WORKFLOW = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"

# The shell body of the range step, extracted so the logic is executed rather
# than pattern-matched. Kept in sync by test_the_extracted_logic_matches_the_workflow.
RANGE_LOGIC = """
CURRENT_TAG="$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || true)"
if [[ -n "$CURRENT_TAG" ]]; then
  RANGE="${CURRENT_TAG}..HEAD"
  COUNT="$(git rev-list --count "$RANGE")"
else
  RANGE=""
  COUNT="$(git rev-list --count HEAD)"
fi
echo "${RANGE:-<all>}|${COUNT}"
"""


def _steps() -> list:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["release"]["steps"]


def _step(step_id: str) -> dict:
    return next(s for s in _steps() if s.get("id") == step_id)


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _run_range_logic(repo) -> tuple:
    out = subprocess.run(["bash", "-c", RANGE_LOGIC], cwd=str(repo), capture_output=True, text=True, check=True)
    rng, count = out.stdout.strip().split("|")
    return rng, int(count)


# ------------------------------------------------- the range is passed, not inferred


def test_the_version_step_is_given_an_explicit_range():
    """Without this, cliff decides what "unreleased" means and a merge hides it."""
    args = _step("version")["with"]["args"]

    assert "--bumped-version" in args
    assert "steps.range.outputs.range" in args, "the version step still infers its own range"


def test_the_range_step_runs_before_the_version_step():
    ids = [s.get("id") for s in _steps()]

    assert ids.index("range") < ids.index("version")


# ------------------------------------ a no-release outcome with commits is an error


def test_nothing_to_release_with_commits_in_range_fails_the_run():
    """The defect was a green run that minted nothing.

    A range that is genuinely empty is a legitimate no-op; a non-empty one means
    the version decision could not see the commits, and that must not exit 0.
    """
    body = _step("check")["run"]

    assert "commit_count" in body, "the guard does not consult the range size"
    assert "exit 1" in body, "a version decision that misses its range still exits 0"
    assert "::error::" in body


def test_an_empty_range_is_still_a_clean_no_op():
    body = _step("check")["run"]

    assert "release_needed=false" in body
    assert "::notice::" in body, "a legitimate no-op should say so rather than being silent"


# ----------------------------------------------------- the logic itself, executed


def test_a_tagged_repo_yields_the_range_since_its_latest_tag(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "f.txt").write_text("1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "feat: one")
    _git(tmp_path, "tag", "v1.0.0")
    (tmp_path / "f.txt").write_text("2\n", encoding="utf-8")
    _git(tmp_path, "commit", "-qam", "feat: two")

    rng, count = _run_range_logic(tmp_path)

    assert rng == "v1.0.0..HEAD"
    assert count == 1


def test_a_merge_commit_range_reports_every_commit_not_just_the_merge(tmp_path):
    """The exact shape that produced no release.

    First-parent from the tag is one commit — the merge, which cliff skips. The
    range must report the whole set, or the version decision has nothing to work
    from.
    """
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "f.txt").write_text("1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "chore: base")
    _git(tmp_path, "tag", "v1.0.0")
    _git(tmp_path, "checkout", "-qb", "feature")
    for i in range(3):
        (tmp_path / f"n{i}.txt").write_text("x\n", encoding="utf-8")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-qm", f"feat: change {i}")
    _git(tmp_path, "checkout", "-q", "master") if _has_master(tmp_path) else _git(tmp_path, "checkout", "-q", "main")
    _git(tmp_path, "merge", "--no-ff", "-q", "-m", "Merge pull request #1 from feature", "feature")

    first_parent = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-list", "--count", "--first-parent", "v1.0.0..HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    rng, count = _run_range_logic(tmp_path)

    assert first_parent == "1", "fixture no longer reproduces the merge shape"
    assert count == 4, f"the range saw {count} commits, not the 3 changes plus the merge"


def _has_master(repo) -> bool:
    out = subprocess.run(
        ["git", "-C", str(repo), "branch", "--list", "master"], capture_output=True, text=True, check=True
    )
    return bool(out.stdout.strip())


def test_an_untagged_repo_falls_back_to_all_history(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "f.txt").write_text("1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "feat: only")

    rng, count = _run_range_logic(tmp_path)

    assert rng == "<all>"
    assert count == 1


def test_the_extracted_logic_matches_the_workflow():
    """Guard the guard: the logic above is a copy, and a copy can drift."""
    body = _step("range")["run"]

    for line in ("git describe --tags --abbrev=0", "rev-list --count", 'RANGE="${CURRENT_TAG}..HEAD"'):
        assert line in body, f"the workflow no longer contains: {line}"
