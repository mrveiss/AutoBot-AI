# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-board lane fails a branch that adds a file without the license header, before it boards (#21535).

A merge train once landed three files with no header: the train content gate catches that, but only when the
train is built, after the member has boarded. The ``added-headers`` job of ``dispatch-preboard-guards.yml`` asks
``preboard_guard_lane.py added-headers`` the same question of the member's own head. This file holds:

* the check on real commits in a temporary repository: an added in-scope file with and without the header, an
  out-of-scope one, a modified one (not this check's business), a renamed one (judged where it lands), and the
  COMMITTED text against a working tree that says otherwise;
* the command: exit status, the files it names, and that it fetches the pinned base first;
* the verdict: a failed, cancelled or missing job is not boardable;
* the workflow wiring, and that the gate and the lane share one definition of "lacks the header".

What it does not cover: no lane run is dispatched here, so the job running on a runner is first shown by the lane
run on the branch that added it.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from repo_tests import _preboard_guard_lane_support as support
from repo_tests._paths import repo_root

from autobot_shared.isolated_git import git, make_repo
from tools.lint import _parse_cache as parse_cache

_ROOT = repo_root()
_WORKFLOW = _ROOT / ".github" / "workflows" / "dispatch-preboard-guards.yml"
_GATE = _ROOT / "pipeline-scripts" / "train_content_gate.py"
_HEADED = "# Copyright 2025-2026 mrveiss\n# SPDX-License-Identifier: Apache-2.0\nvalue = 1\n"
_HEADLESS = "value = 1\n"


@pytest.fixture(scope="module")
def lane():
    yield from support.load_lane()


@pytest.fixture(scope="module")
def jobs() -> dict[str, Any]:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))["jobs"]


class Repo:
    """A temporary repository: ``base`` is main's commit, ``head`` the commit of a branch cut from it."""

    def __init__(self, path: Path) -> None:
        self.path = make_repo(path)
        self.base = ""

    def run(self, *args: str) -> str:
        return git(self.path, *args).stdout.strip()

    def write(self, rel: str, text: str) -> None:
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def commit(self, message: str) -> str:
        self.run("add", "-A")
        self.run("commit", "-q", "-m", message)
        return self.run("rev-parse", "HEAD")

    def branch(self) -> None:
        """Pin the base at the current commit and move to a member branch."""
        self.base = self.run("rev-parse", "HEAD")
        self.run("switch", "-q", "-c", "member")


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Repo:
    made = Repo(tmp_path / "r")
    monkeypatch.chdir(made.path)
    made.write("existing.py", _HEADLESS)  # a header-less file already on the base: legacy, not this head's addition
    made.write("keep.py", _HEADED)
    made.commit("base")
    made.branch()
    return made


def _flagged(lane, repo: Repo, head: str) -> list[str]:
    return lane.headerless_additions(repo.base, head)


def test_an_added_in_scope_file_without_the_header_is_named(lane, repo) -> None:
    repo.write("new/a.py", _HEADLESS)
    repo.write("new/b.py", _HEADED)
    assert _flagged(lane, repo, repo.commit("add")) == ["new/a.py"]


def test_added_files_with_the_header_pass_in_every_scope_extension(lane, repo) -> None:
    repo.write("new/a.py", _HEADED)
    repo.write("new/b.sh", "#!/bin/sh\n# Copyright 2025-2026 mrveiss\n# SPDX-License-Identifier: Apache-2.0\n")
    repo.write("new/c.ts", "// Copyright 2025-2026 mrveiss\n// SPDX-License-Identifier: Apache-2.0\n")
    assert _flagged(lane, repo, repo.commit("add")) == []


def test_each_headerless_file_is_named_not_only_the_first(lane, repo) -> None:
    for name in ("one.py", "two.py", "three.sh"):
        repo.write(f"new/{name}", _HEADLESS)
    assert _flagged(lane, repo, repo.commit("add")) == ["new/one.py", "new/three.sh", "new/two.py"]


def test_an_added_file_outside_the_checks_scope_passes(lane, repo) -> None:
    repo.write("notes.txt", "no header here\n")
    repo.write("docs/a.md", "# a doc\n")
    assert _flagged(lane, repo, repo.commit("add")) == []


def test_a_modified_headerless_file_is_not_flagged(lane, repo) -> None:
    repo.write("existing.py", _HEADLESS + "other = 2\n")
    assert _flagged(lane, repo, repo.commit("modify")) == []


def test_a_renamed_file_is_judged_where_it_lands(lane, repo) -> None:
    repo.run("mv", "existing.py", "moved.py")
    repo.run("mv", "keep.py", "kept.py")
    assert _flagged(lane, repo, repo.commit("rename")) == ["moved.py"]


def test_a_file_deleted_by_the_head_is_not_flagged(lane, repo) -> None:
    repo.run("rm", "-q", "existing.py")
    assert _flagged(lane, repo, repo.commit("delete")) == []


def test_the_committed_text_decides_not_the_working_tree(lane, repo) -> None:
    repo.write("new/a.py", _HEADLESS)
    repo.write("new/b.py", _HEADED)
    head = repo.commit("add")
    repo.write("new/a.py", _HEADED)  # the working tree now has a header the commit does not
    repo.write("new/b.py", _HEADLESS)  # and has lost the one the commit has
    assert _flagged(lane, repo, head) == ["new/a.py"]


def test_the_head_is_judged_against_the_merge_base_not_the_base_tip(lane, repo) -> None:
    repo.write("new/a.py", _HEADLESS)
    head = repo.commit("add")
    repo.run("switch", "-q", "main")
    repo.write("elsewhere.py", _HEADLESS)  # main moves on with its own header-less file after the branch point
    tip = repo.commit("main moves")
    assert tip != repo.base and _flagged(lane, repo, head) == ["new/a.py"]


def _main(lane, repo: Repo, head: str, monkeypatch, fetched: list[str]) -> int:
    monkeypatch.setattr(lane, "pinned_base_commit", lambda sha: fetched.append(sha) or {})
    return lane.main(["added-headers", "--base-sha", repo.base, "--head-sha", head])


def test_the_command_exits_one_and_names_the_file(lane, repo, monkeypatch, capsys) -> None:
    repo.write("new/a.py", _HEADLESS)
    fetched: list[str] = []
    assert _main(lane, repo, repo.commit("add"), monkeypatch, fetched) == 1
    err = capsys.readouterr().err
    assert "new/a.py: added without the SPDX/Apache-2.0 license header" in err and "::error::1 added file(s)" in err
    assert fetched == [repo.base], "the pinned base is fetched by id before the diff reads it"


def test_the_command_exits_zero_when_every_added_file_has_the_header(lane, repo, monkeypatch, capsys) -> None:
    repo.write("new/a.py", _HEADED)
    assert _main(lane, repo, repo.commit("add"), monkeypatch, []) == 0
    assert "all" in capsys.readouterr().out


@pytest.mark.parametrize("sha", ["main", "abc123", "", "g" * 40])
def test_a_commit_that_is_not_a_full_id_is_refused(lane, sha) -> None:
    with pytest.raises(SystemExit):
        lane.headerless_additions(sha, "a" * 40)
    with pytest.raises(SystemExit):
        lane.headerless_additions("a" * 40, sha)


@pytest.mark.parametrize(
    "added,expected",
    [("success", "green"), ("failure", "red"), ("skipped", "red"), ("cancelled", "cancelled")],
)
def test_the_added_headers_job_decides_the_lane(lane, tmp_path, added, expected) -> None:
    needs = json.dumps({**support.env_needs(), "added-headers": {"result": added}})
    shards = [support.shard(1, 1, 0, support.passing("repo_tests/m_test.py", 9))]
    result = support.verdict(lane, tmp_path, shards, NEEDS_JSON=needs)
    assert result["overall"] == expected and result["checks"]["added_headers"]["status"] == added


def test_a_needs_without_the_added_headers_job_is_red(lane, tmp_path) -> None:
    needs = json.dumps({k: v for k, v in support.env_needs().items() if k != "added-headers"})
    shards = [support.shard(1, 1, 0, support.passing("repo_tests/m_test.py", 9))]
    result = support.verdict(lane, tmp_path, shards, NEEDS_JSON=needs)
    assert result["overall"] == "red" and result["checks"]["added_headers"]["status"] == "missing"


def test_the_summary_names_the_check(lane, tmp_path) -> None:
    shards = [support.shard(1, 1, 0, support.passing("repo_tests/m_test.py", 9))]
    summary = lane.report.render_lane_summary(support.verdict(lane, tmp_path, shards))
    assert "| license header on every added file | success |" in summary


def _runs(job: dict[str, Any]) -> str:
    return "\n".join(s["run"] for s in job["steps"] if "run" in s)


def test_the_job_reads_the_pinned_base_and_the_dispatched_head_and_merges_nothing(jobs) -> None:
    job = jobs["added-headers"]
    assert job["needs"] == ["pin"] and "timeout-minutes" in job and "added-headers" in jobs["result"]["needs"]
    step = next(s for s in job["steps"] if "added-headers" in s.get("run", ""))
    assert step["env"] == {"BASE_SHA": "${{ needs.pin.outputs.base_sha }}", "HEAD_SHA": "${{ github.sha }}"}
    assert step["run"].strip() == (
        'python3 pipeline-scripts/preboard_guard_lane.py added-headers --base-sha "$BASE_SHA" --head-sha "$HEAD_SHA"'
    )
    assert job["steps"][0]["with"]["fetch-depth"] == 0, "the three-dot diff needs the history"
    body = _runs(job)
    assert " merge " not in body and "pytest" not in body and "${{" not in body
    assert not any(s.get("uses", "").startswith("./") for s in job["steps"]), "no suite environment is built"


def _called(path: Path) -> set[str]:
    """Names the module at *path* calls or defines (anywhere in it)."""
    tree = parse_cache.parse(path.read_text(encoding="utf-8"))
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    return calls | defined


def test_the_gate_and_the_lane_share_one_definition_of_lacking_the_header() -> None:
    for module in (_GATE, support.LANE_MODULE):
        names = _called(module)
        assert "lacks_header" in names, f"{module.name} no longer asks the shared check"
        assert not names & {"has_header", "in_scope"}, f"{module.name} restates the header test"
