# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The early ``frontend-related-specs`` job of ci.yml (#22114).

It runs ``vitest related`` on the files a pull request changes, so a spec that cannot load goes red in minutes and not
after the whole frontend suite. This file pins what that early signal depends on:

* the job runs only on a ready, un-held pull request, and starts after ``changes`` alone;
* it sets up the toolchain through the one shared action, with the same package the suite installs;
* it runs ``vitest related --run --passWithNoTests`` and passes no ``--`` before the files (Vitest 4's ``related`` command
  reads its files from the arguments before ``--``; the ones after it never reach it);
* no ``run:`` block interpolates an expression, so a file name cannot become shell;
* a shared-kit change selects consumer specs, which needs both apps to pin the kit by file path.

What it does not cover: that the job goes red on a broken spec; the first pull request that breaks one proves that.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from repo_tests._paths import repo_root

_ROOT = repo_root()
_CI = _ROOT / ".github" / "workflows" / "ci.yml"
_ACTION = "./.github/actions/setup-frontend"
_IF = (
    "${{ github.event_name == 'pull_request' && needs.changes.outputs.ready == 'true' "
    "&& needs.changes.outputs.held != 'true' }}"
)


@pytest.fixture(scope="module")
def jobs() -> dict[str, Any]:
    return yaml.safe_load(_CI.read_text(encoding="utf-8"))["jobs"]


def _runs(job: dict[str, Any]) -> list[str]:
    return [s["run"] for s in job["steps"] if "run" in s]


def test_the_job_runs_on_a_ready_unheld_pull_request_after_changes_only(jobs) -> None:
    job = jobs["frontend-related-specs"]
    assert job["name"] == "frontend-related-specs"
    assert job["if"] == _IF
    assert job["needs"] == "changes", "no short-check wait: the point is an early signal"


def test_the_job_uses_the_shared_setup_action_with_the_suites_package(jobs) -> None:
    setup = next(s for s in jobs["frontend-related-specs"]["steps"] if s.get("uses") == _ACTION)
    assert setup["with"]["package-dirs"] == "${{ steps.files.outputs.apps }}"
    assert "autobot-frontend/package-lock.json" in setup["with"]["cache-dependency-path"]
    suite = next(s for s in jobs["frontend-tests"]["steps"] if s.get("uses") == _ACTION)
    assert suite["with"]["package-dirs"] == "autobot-frontend"


def test_the_job_runs_vitest_related_on_the_files_without_a_double_dash(jobs) -> None:
    run = "\n".join(_runs(jobs["frontend-related-specs"]))
    assert 'npx --no-install vitest related --run --passWithNoTests "${FILES[@]}"' in run
    assert "vitest related --run --passWithNoTests --" not in run


def test_no_run_block_of_the_job_interpolates_an_expression(jobs) -> None:
    for run in _runs(jobs["frontend-related-specs"]):
        assert "${{" not in run, run


def test_the_job_installs_nothing_itself(jobs) -> None:
    assert not [r for r in _runs(jobs["frontend-related-specs"]) if "npm ci" in r or "npm install" in r]


def test_a_kit_change_selects_consumer_specs_in_both_apps(jobs) -> None:
    run = next(s["run"] for s in jobs["frontend-related-specs"]["steps"] if s.get("id") == "files")
    assert "libs/autobot-ui/" in run and "GITHUB_WORKSPACE" in run, "the kit files are given as absolute paths"
    assert "autobot-frontend autobot-slm-frontend" in run
    configs = ("autobot-frontend/vite.config.js", "autobot-slm-frontend/vitest.config.ts")
    for config in configs:
        assert "autobotUiResolve" in (_ROOT / config).read_text(
            encoding="utf-8"
        ), f"{config} no longer pins the kit by path"


def test_the_frontend_filter_runs_the_suite_for_an_action_only_change() -> None:
    filters = yaml.safe_load((_ROOT / ".github/filters/frontend-paths.yml").read_text(encoding="utf-8"))["frontend"]
    assert ".github/actions/setup-frontend/**" in filters
