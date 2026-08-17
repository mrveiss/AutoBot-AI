# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guards for the `python-suite` required-context split (#14353).

`python-suite` can only be a required status check if *exactly one* job publishes
it on every pull request: the real twelve-shard suite in ci.yml when Python paths
changed, and the shim in python-required-context.yml when they did not.

The dangerous direction is silent. If the shim believed nothing Python changed
while ci.yml believed otherwise, the pull request would take the shim's green for
a suite that never ran — a gate bypass, not a flake. These tests pin the two
properties that prevent it: the job names match, and both sides read the same
filter file rather than keeping copies that can drift.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflows")

REPO_ROOT = Path(__file__).resolve().parents[1]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SHIM = REPO_ROOT / ".github" / "workflows" / "python-required-context.yml"
FILTER = REPO_ROOT / ".github" / "filters" / "python-paths.yml"

REQUIRED_CONTEXT = "python-suite"


def _jobs(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]


def test_both_workflows_publish_the_same_context_name():
    """The required context is the job NAME; a rename on one side breaks the split."""
    assert _jobs(CI)[REQUIRED_CONTEXT]["name"] == REQUIRED_CONTEXT
    assert _jobs(SHIM)[REQUIRED_CONTEXT]["name"] == REQUIRED_CONTEXT


def test_the_two_conditions_are_exact_complements():
    """One and only one of them may run for any given pull request."""
    real = _jobs(CI)[REQUIRED_CONTEXT]["if"]
    shim = _jobs(SHIM)[REQUIRED_CONTEXT]["if"]

    assert "needs.changes.outputs.python == 'true'" in real
    assert shim.strip() == "needs.changes.outputs.python != 'true'"


def test_both_sides_read_the_shared_filter_file():
    """A second inline copy of the path set is how the two sides drift apart."""
    assert FILTER.is_file(), f"missing canonical filter: {FILTER}"

    for path in (CI, SHIM):
        text = path.read_text(encoding="utf-8")
        assert ".github/filters/python-paths.yml" in text, f"{path.name} does not read the shared filter"

    # ...and ci.yml resolves the set through that file rather than an inline copy.
    steps = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["changes"]["steps"]
    python_steps = [s for s in steps if s.get("id") == "filter-python"]
    assert len(python_steps) == 1, "ci.yml must resolve `python` through exactly one filter step"
    assert python_steps[0]["with"]["filters"] == ".github/filters/python-paths.yml"


def test_the_filter_covers_its_own_inputs():
    """Editing the filter or the shim must run the real suite, not the shim."""
    patterns = yaml.safe_load(FILTER.read_text(encoding="utf-8"))["python"]

    assert ".github/filters/python-paths.yml" in patterns
    assert ".github/workflows/python-required-context.yml" in patterns
    assert ".github/workflows/ci.yml" in patterns
    assert "**/*.py" in patterns


def test_the_shim_declares_no_concurrency_group():
    """A shared concurrency group is what made the frontend shim useless (#13405).

    Asserted against the parsed document, not the raw text: the file *explains*
    why it has no concurrency block, and a substring check fails on its own
    comment.
    """
    parsed = yaml.safe_load(SHIM.read_text(encoding="utf-8"))
    assert "concurrency" not in parsed
    assert "concurrency" not in parsed["jobs"][REQUIRED_CONTEXT]


def test_the_shim_runs_on_a_github_hosted_runner():
    """The shim must not depend on the singleton self-hosted pool."""
    assert _jobs(SHIM)[REQUIRED_CONTEXT]["runs-on"] == "ubuntu-latest"
    assert _jobs(SHIM)["changes"]["runs-on"] == "ubuntu-latest"


def test_the_shim_fails_closed_on_a_broken_detector():
    """If `changes` errors, the shim must skip rather than report green."""
    shim_job = _jobs(SHIM)[REQUIRED_CONTEXT]
    assert shim_job["needs"] == "changes", "without `needs`, a failed detector would not gate the shim"
