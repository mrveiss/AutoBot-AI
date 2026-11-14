# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-board lane runs the Vitest specs a head adds or changes, and fails when they fail (#21509, #18499).

A member's new frontend specs used to execute for the first time inside the merge train. The ``own-specs`` job of
``dispatch-preboard-guards.yml`` runs them first. This file holds:

* the selection (``changed-specs``) on real commits in a temporary repository: an added and a modified spec are
  selected under their package, a deleted one and a non-spec are not, a spec no package collects is a notice,
  several packages are grouped, and the config's own ``include``/``exclude`` decide (comments and nested objects
  such as ``coverage`` do not);
* the rule reader and the glob it feeds, on small cases, and on the three real configs (non-vacuous);
* the verdict: a failed, cancelled, skipped or missing ``own-specs`` job is not boardable;
* the workflow: the job merges the pinned base, installs nothing for an empty selection, sets Node up as the
  frontend test job does, and hands Vitest exactly the selected files.

What it does not cover: no lane run is dispatched here, and a branch that changes no spec exercises only the
empty path of the job, so the install and run steps are first proved by a lane run on a branch with a changed spec.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any

import pytest
import yaml
from repo_tests import _preboard_guard_lane_support as support
from repo_tests._paths import repo_root

from autobot_shared.isolated_git import git, make_repo
from tools.lint._comment_syntax import code_lines

_ROOT = repo_root()
_WORKFLOW = _ROOT / ".github" / "workflows" / "dispatch-preboard-guards.yml"
_SUITE = _ROOT / ".github" / "workflows" / "ci.yml"
_PACKAGES = ("autobot-frontend", "autobot-slm-frontend", "libs/autobot-ui")
_FILES_ARG = '"${FILES[@]}"'
_CONFIG = """import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    // include: ['commented/**/*.spec.ts'],
    coverage: { include: ['never/**/*.spec.ts'], exclude: ['cov/**'] },
    include: ['src/**/*.{test,spec}.ts'],
    exclude: [...configDefaults.exclude, 'e2e/**', '**/*.playwright.spec.ts'],
  },
})
"""


@pytest.fixture(scope="module")
def lane():
    yield from support.load_lane()


@pytest.fixture(scope="module")
def jobs() -> dict[str, Any]:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))["jobs"]


class Repo:
    """A temporary repository: ``base`` is main's commit, the member's commits are cut from it."""

    def __init__(self, path: Path) -> None:
        self.path = make_repo(path)
        self.base = ""

    def run(self, *args: str) -> str:
        return git(self.path, *args).stdout.strip()

    def write(self, rel: str, text: str = "it('x', () => {})\n") -> None:
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def commit(self, message: str) -> str:
        self.run("add", "-A")
        self.run("commit", "-q", "-m", message)
        return self.run("rev-parse", "HEAD")

    def branch(self) -> None:
        self.base = self.run("rev-parse", "HEAD")
        self.run("switch", "-q", "-c", "member")


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Repo:
    made = Repo(tmp_path / "r")
    monkeypatch.chdir(made.path)
    made.write("web/vitest.config.ts", _CONFIG)
    made.write("kit/inner/vitest.config.ts", _CONFIG.replace("src/**/*.{test,spec}.ts", "tests/**/*.spec.ts"))
    made.write("web/src/kept.spec.ts")
    made.write("web/src/gone.spec.ts")
    made.commit("base")
    made.branch()
    return made


def _select(lane, repo: Repo, head: str, capsys, rc: int = 0) -> dict[str, Any]:
    out = repo.path.parent / "out"
    argv = ["changed-specs", "--base-sha", repo.base, "--head-sha", head, "--out-dir", str(out)]
    assert lane.main(argv) == rc
    captured = capsys.readouterr()
    packages = (out / "packages.txt").read_text(encoding="utf-8").split()
    lists = {p: (out / f"{p.replace('/', '__')}.txt").read_text(encoding="utf-8").split() for p in packages}
    return {"out": captured.out, "err": captured.err, "packages": packages, "lists": lists}


def test_an_added_spec_is_selected_under_its_package_relative_to_it(lane, repo, capsys) -> None:
    repo.write("web/src/deep/new.spec.ts")
    got = _select(lane, repo, repo.commit("add"), capsys)
    assert got["packages"] == ["web"] and got["lists"] == {"web": ["src/deep/new.spec.ts"]}
    assert got["out"] == "total=1\npackages=1\n"


def test_a_modified_spec_is_selected_too(lane, repo, capsys) -> None:
    repo.write("web/src/kept.spec.ts", "it('changed', () => {})\n")
    got = _select(lane, repo, repo.commit("modify"), capsys)
    assert got["lists"] == {"web": ["src/kept.spec.ts"]}


def test_a_deleted_spec_is_not_selected_and_an_empty_selection_says_so(lane, repo, capsys) -> None:
    repo.run("rm", "-q", "web/src/gone.spec.ts")
    got = _select(lane, repo, repo.commit("delete"), capsys)
    assert got["packages"] == [] and got["out"] == "total=0\npackages=0\n"
    assert "no changed frontend specs" in got["err"]


def test_a_changed_file_that_is_not_a_spec_is_not_selected(lane, repo, capsys) -> None:
    repo.write("web/src/util.ts", "export const x = 1\n")
    repo.write("web/src/spec-helpers.ts", "export const y = 2\n")
    repo.write("web/src/a.spec.ts.md", "notes\n")
    got = _select(lane, repo, repo.commit("add"), capsys)
    assert got["packages"] == [] and got["out"] == "total=0\npackages=0\n"
    assert "::notice::" not in got["err"], "a file that does not look like a spec is not worth a notice"


def test_a_spec_outside_every_package_is_a_notice_and_not_a_failure(lane, repo, capsys) -> None:
    repo.write("elsewhere/x.test.ts")
    got = _select(lane, repo, repo.commit("add"), capsys)
    assert got["packages"] == []
    assert "::notice::elsewhere/x.test.ts looks like a spec" in got["err"] and "::error::" not in got["err"]


def test_specs_are_grouped_by_package_and_the_nearest_config_owns_a_file(lane, repo, capsys) -> None:
    repo.write("web/src/a.spec.ts")
    repo.write("kit/inner/tests/b.spec.ts")
    repo.write("kit/inner/tests/c.spec.ts")
    repo.write("web/sub/vitest.config.ts", _CONFIG.replace("src/**/*.{test,spec}.ts", "tests/**/*.spec.ts"))
    repo.write(
        "web/sub/tests/n.spec.ts"
    )  # under web too, but web/sub holds the nearer config (and web would not collect it)
    got = _select(lane, repo, repo.commit("add"), capsys)
    assert got["packages"] == ["kit/inner", "web", "web/sub"]
    assert got["lists"] == {
        "kit/inner": ["tests/b.spec.ts", "tests/c.spec.ts"],
        "web": ["src/a.spec.ts"],
        "web/sub": ["tests/n.spec.ts"],
    }
    assert got["out"] == "total=4\npackages=3\n"


def test_a_spec_an_explicit_exclude_skips_is_a_notice_and_the_job_stays_green(lane, repo, capsys) -> None:
    for rel in ("web/e2e/a.spec.ts", "web/src/b.playwright.spec.ts", "web/src/node_modules/e.spec.ts"):
        repo.write(rel)
    repo.write("web/src/ok.spec.ts")
    got = _select(lane, repo, repo.commit("add"), capsys)
    assert got["lists"] == {"web": ["src/ok.spec.ts"]}
    for path in ("web/e2e/a.spec.ts", "web/src/b.playwright.spec.ts", "web/src/node_modules/e.spec.ts"):
        assert f"::notice::{path} looks like a spec" in got["err"], path
    assert "::error::" not in got["err"]


def test_a_spec_in_a_package_that_its_include_does_not_match_is_an_error_and_red(lane, repo, capsys) -> None:
    repo.write("web/src/c.spec.tsx")
    repo.write("web/never/d.spec.ts")
    got = _select(lane, repo, repo.commit("add"), capsys, rc=1)
    assert "::error::web/src/c.spec.tsx looks like a spec but package web does not collect it" in got["err"]
    assert "::error::web/never/d.spec.ts looks like a spec but package web does not collect it" in got["err"]
    assert "::notice::web/never" not in got["err"]


def test_an_unrun_spec_is_red_even_beside_a_collected_one_which_is_still_selected(lane, repo, capsys) -> None:
    repo.write("web/src/ok.spec.ts")
    repo.write("web/never/d.spec.ts")
    got = _select(lane, repo, repo.commit("add"), capsys, rc=1)
    assert got["lists"] == {"web": ["src/ok.spec.ts"]} and got["out"] == "total=1\npackages=1\n"


def test_a_deleted_unrun_spec_is_not_an_error(lane, repo, capsys) -> None:
    repo.write("web/never/d.spec.ts")
    repo.commit("add the odd one")
    repo.base = repo.run("rev-parse", "HEAD")
    (repo.path / "web" / "never" / "d.spec.ts").unlink()
    got = _select(lane, repo, repo.commit("remove"), capsys)
    assert got["packages"] == [] and "::error::" not in got["err"]


def test_the_rules_are_read_from_the_test_object_without_comments_or_nested_objects(lane, tmp_path) -> None:
    config = tmp_path / "vitest.config.ts"
    config.write_text(_CONFIG, encoding="utf-8")
    include, exclude = lane.specs.package_rules(config)
    assert include == ["src/**/*.{test,spec}.ts"]
    assert exclude == ["e2e/**", "**/*.playwright.spec.ts", *lane.specs.DEFAULT_EXCLUDE]


def test_a_glob_survives_comments_that_hold_an_apostrophe_a_block_marker_or_trail_a_rule(lane, tmp_path) -> None:
    config = tmp_path / "vitest.config.ts"
    config.write_text(
        "export default { test: {\n"
        "  // the worker's stdout -- and a stray /* opener, which is prose here\n"
        "  include: ['src/**/*.spec.ts'], /* a real block comment */\n"
        "  exclude: ['e2e/**'], // trailing, with a don't\n"
        "} }\n",
        encoding="utf-8",
    )
    text = lane.specs.code_text(config.read_text(encoding="utf-8"), name=config.name, strip_trailing=True)
    assert "'src/**/*.spec.ts'" in text and "'e2e/**'" in text, text
    for gone in ("worker", "real block comment", "trailing", "don't"):
        assert gone not in text, f"{gone!r} survived comment removal: {text}"
    assert lane.specs.package_rules(config) == (["src/**/*.spec.ts"], ["e2e/**"])


def test_a_config_without_include_or_exclude_gets_vitests_defaults(lane, tmp_path) -> None:
    config = tmp_path / "vitest.config.ts"
    config.write_text("export default defineConfig({ test: { globals: true } })\n", encoding="utf-8")
    assert lane.specs.package_rules(config) == (list(lane.specs.DEFAULT_INCLUDE), list(lane.specs.DEFAULT_EXCLUDE))


def test_a_declared_exclude_without_the_default_spread_is_exactly_what_it_says(lane, tmp_path) -> None:
    config = tmp_path / "vitest.config.ts"
    config.write_text("export default { test: { include: ['a/**'], exclude: ['b/**'] } }\n", encoding="utf-8")
    assert lane.specs.package_rules(config) == (["a/**"], ["b/**"])


@pytest.mark.parametrize(
    "path,pattern,expected",
    [
        ("src/a.spec.ts", "src/**/*.{test,spec}.ts", True),
        ("src/x/y/a.test.ts", "src/**/*.{test,spec}.ts", True),
        ("src/a.spec.tsx", "src/**/*.{test,spec}.ts", False),
        ("lib/a.spec.ts", "src/**/*.{test,spec}.ts", False),
        ("e2e/a.spec.ts", "e2e/**", True),
        ("src/e2e/a.spec.ts", "e2e/**", False),
        ("src/a.e2e.test.ts", "**/*.e2e.test.ts", True),
        ("a.e2e.test.ts", "**/*.e2e.test.ts", True),
        ("src/node_modules/x/a.spec.ts", "**/node_modules/**", True),
        ("src/a.spec.ts", "src/?.spec.ts", True),
        ("src/ab.spec.ts", "src/?.spec.ts", False),
        ("src/ab.spec.ts", "src/*.spec.ts", True),
        ("src/deep/a.spec.ts", "src/*.spec.ts", False),
    ],
)
def test_the_glob_reads_double_star_star_question_and_braces_as_vitest_does(lane, path, pattern, expected) -> None:
    assert lane.specs.glob_matches(path, [pattern]) is expected


def test_braces_expand_in_groups_and_nested(lane) -> None:
    assert lane.specs.expand_braces("a.{b,c}.d") == ["a.b.d", "a.c.d"]
    assert lane.specs.expand_braces("x{a,{b,c}}") == ["xa", "xb", "xc"]
    assert lane.specs.expand_braces("{a,b}.{c,d}") == ["a.c", "a.d", "b.c", "b.d"]
    assert lane.specs.expand_braces("plain") == ["plain"]


@pytest.mark.parametrize("package", _PACKAGES)
def test_each_real_package_config_yields_rules_that_collect_a_spec_and_skip_the_rest(lane, package) -> None:
    rules = lane.specs.package_rules(_ROOT / package / "vitest.config.ts")
    assert rules[0], f"{package}: the config's include list was not read"
    assert lane.specs.collected(rules, "src/deep/x/a.spec.ts"), f"{package}: an ordinary spec is not collected"
    assert not lane.specs.collected(rules, "src/deep/node_modules/a.spec.ts")
    assert not lane.specs.collected(rules, "docs/a.spec.ts")


def test_the_frontend_config_excludes_what_the_suite_excludes(lane) -> None:
    rules = lane.specs.package_rules(_ROOT / "autobot-frontend" / "vitest.config.ts")
    assert not lane.specs.collected(rules, "e2e/a.spec.ts")
    assert not lane.specs.collected(rules, "src/test/e2e/a.spec.ts")
    assert not lane.specs.collected(rules, "src/a.playwright.spec.ts")
    assert lane.specs.collected(rules, "src/components/__tests__/a.spec.ts")
    assert lane.specs.collected(rules, "scripts/canonical/__tests__/runner.test.mjs")


def test_only_the_changed_specs_that_still_exist_in_the_tested_tree_are_selected(lane, tmp_path) -> None:
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "vitest.config.ts").write_text(_CONFIG, encoding="utf-8")
    (tmp_path / "web" / "src").mkdir()
    (tmp_path / "web" / "src" / "here.spec.ts").write_text("", encoding="utf-8")
    paths = ["web/src/here.spec.ts", "web/src/here.spec.ts", "web/src/absent.spec.ts"]
    assert lane.specs.select_specs(tmp_path, paths) == ({"web": ["src/here.spec.ts"]}, [], [])


def _green_shards() -> list[dict[str, Any]]:
    return [support.shard(1, 1, 0, support.passing("repo_tests/m_test.py", 9))]


@pytest.mark.parametrize(
    "own,expected", [("success", "green"), ("failure", "red"), ("skipped", "red"), ("cancelled", "cancelled")]
)
def test_the_own_specs_job_decides_the_lane(lane, tmp_path, own, expected) -> None:
    needs = json.dumps({**support.env_needs(), "own-specs": {"result": own}})
    result = support.verdict(lane, tmp_path, _green_shards(), NEEDS_JSON=needs)
    assert result["overall"] == expected and result["checks"]["own_specs"]["status"] == own


def test_a_needs_without_the_own_specs_job_is_red(lane, tmp_path) -> None:
    needs = json.dumps({k: v for k, v in support.env_needs().items() if k != "own-specs"})
    result = support.verdict(lane, tmp_path, _green_shards(), NEEDS_JSON=needs)
    assert result["overall"] == "red" and result["checks"]["own_specs"]["status"] == "missing"


def test_the_summary_names_the_check(lane, tmp_path) -> None:
    summary = lane.report.render_lane_summary(support.verdict(lane, tmp_path, _green_shards()))
    assert "| own specs (the frontend spec files this head adds or changes) | success |" in summary


def test_the_workflow_header_documents_the_job_and_its_result_field() -> None:
    header = _WORKFLOW.read_text(encoding="utf-8").split("\nname: ", 1)[0]
    assert "checks.own_specs" in header and "own-specs" in header and "changed-specs" in header
    assert "Not covered: frontend specs" not in header


def _steps(jobs: dict[str, Any]) -> list[dict[str, Any]]:
    return jobs["own-specs"]["steps"]


def _step(jobs: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in _steps(jobs) if s.get("name", "").startswith(name))


def test_the_job_merges_the_pinned_base_before_node_and_the_result_job_needs_it(jobs) -> None:
    job = jobs["own-specs"]
    assert job["needs"] == ["pin"] and job["timeout-minutes"] <= 45 and "own-specs" in jobs["result"]["needs"]
    assert _steps(jobs)[0]["with"]["fetch-depth"] == 0, "the three-dot diff and the merge need the history"
    names = [s.get("name", "") for s in _steps(jobs)]
    merge = next(i for i, s in enumerate(_steps(jobs)) if "preboard_guard_lane.py merge" in s.get("run", ""))
    node = next(i for i, s in enumerate(_steps(jobs)) if s.get("uses", "").startswith("actions/setup-node@"))
    assert merge < node and "Stop on a head that conflicts with the base" in names
    assert _step(jobs, "Stop on a head")["if"] == "steps.base.outputs.merged != 'true'"


def test_the_selection_step_reads_the_dispatched_head_against_the_pinned_base(jobs) -> None:
    step = _step(jobs, "Select the frontend specs")
    assert step["id"] == "select"
    assert step["env"] == {"BASE_SHA": "${{ steps.base.outputs.base_sha }}", "HEAD_SHA": "${{ github.sha }}"}
    assert "preboard_guard_lane.py changed-specs" in step["run"] and '>> "$GITHUB_OUTPUT"' in step["run"]
    assert '--base-sha "$BASE_SHA" --head-sha "$HEAD_SHA"' in step["run"]


def test_an_empty_selection_sets_up_and_installs_nothing(jobs) -> None:
    gated = [
        s for s in _steps(jobs) if s.get("uses", "").startswith("actions/setup-node@") or "npm " in s.get("run", "")
    ]
    assert len(gated) == 2, "expected the Node setup step and the install-and-run step"
    for step in gated:
        assert step["if"] == "steps.select.outputs.total != '0'", step["name"]


def test_node_is_set_up_as_the_frontend_test_job_does_it(jobs) -> None:
    suite = yaml.safe_load(_SUITE.read_text(encoding="utf-8"))["jobs"]["frontend-tests"]["steps"]
    theirs = next(s for s in suite if s.get("name") == "Setup Node.js")
    mine = _step(jobs, "Setup Node.js")
    assert mine["uses"] == theirs["uses"], "a different setup-node pin"
    for key in ("node-version-file", "cache"):
        assert mine["with"][key] == theirs["with"][key]
    locks = mine["with"]["cache-dependency-path"].split()
    assert theirs["with"]["cache-dependency-path"] in locks and all((_ROOT / lock).is_file() for lock in locks)
    install = next(s for s in suite if s.get("name") == "Install frontend dependencies")
    for key, value in install["env"].items():
        assert jobs["own-specs"]["env"][key] == value, f"{key} differs from the frontend test job"
    assert "npm ci" in install["run"] and "npm ci" in _step(jobs, "Run the changed specs")["run"]


def _lines(script: str) -> list[list[str]]:
    lines = [c.text for c in code_lines(script, name="step.sh", join_continuations=True) if c.text.strip()]
    return [shlex.split(line, posix=False) for line in lines]


def _vitest_arguments(script: str) -> list[list[str]]:
    """The tokens after ``vitest run`` on every line of *script* that runs it."""
    found = []
    for tokens in _lines(script):
        for i in range(len(tokens) - 1):
            if tokens[i : i + 2] == ["vitest", "run"]:
                found.append(tokens[i + 2 :])
    return found


def test_vitest_runs_once_in_run_mode_on_exactly_the_selection_array(jobs) -> None:
    run = _step(jobs, "Run the changed specs")["run"]
    assert _vitest_arguments(run) == [[_FILES_ARG]], "vitest must be given only the selected files, from the array"
    assert re.search(r"vitest run(?! --watch)", run) and "--coverage" not in run and "--passWithNoTests" not in run
    assert "packages.txt" in run and 'mapfile -t FILES < "$SPECS_DIR/' in run


def test_every_package_runs_and_one_failure_fails_the_job(jobs) -> None:
    run = _step(jobs, "Run the changed specs")["run"]
    assert "rc=0" in run and "rc=1" in run and 'exit "$rc"' in run
    assert "< /dev/null" in run, "an installer must not read the package list"
    assert "set +e" not in run and "|| true" not in run


def test_the_job_installs_with_npm_ci_where_a_lock_exists_and_npm_install_where_none_is_committed(jobs) -> None:
    run = _step(jobs, "Run the changed specs")["run"]
    assert "if [ -f package-lock.json ]; then npm ci; else npm install; fi" in run


def test_the_job_runs_no_pytest_pushes_nothing_and_inlines_no_expression(jobs) -> None:
    body = "\n".join(s["run"] for s in _steps(jobs) if "run" in s)
    assert "${{" not in body and "pytest" not in body
    assert not [t for line in _lines(body) for t in line if t == "push"]
