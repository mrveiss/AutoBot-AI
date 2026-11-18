# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One filter definition per concept, and ci.yml's `changes` job reads each one (#18208).

Before #18208 `backend`, `python` and `frontend` were each defined twice, differently, in
two filter files (and once inline in ci.yml): `backend` was 5 patterns in
backend-python-paths.yml and 30 in code-quality-paths.yml, `python` 2 and 116, `frontend`
3 and 9. Each consumer ran in its own workflow, so the two never met. ONE `changes` job
that loads every file would merge them silently, so the keys must be unique across the
directory -- and every output the job publishes must be computed from a key that exists in
the file its dorny step loads, or a typo reads as `''` and the gate quietly never runs.
"""

import re

import pytest
import yaml
from repo_tests._paths import repo_root

ROOT = repo_root()
FILTERS = ROOT / ".github" / "filters"
CI = ROOT / ".github" / "workflows" / "ci.yml"
DORNY = "dorny/paths-filter"


def _filters() -> dict:
    return {
        p.name: yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(FILTERS.iterdir()) if p.suffix == ".yml"
    }


def _flat(value) -> set:
    if isinstance(value, str):
        return {value}
    out: set = set()
    for item in value or []:
        out |= _flat(item)
    return out


def _changes_job() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["changes"]


def test_the_directory_is_not_empty():
    assert len(_filters()) >= 7


def test_no_filter_key_is_defined_in_two_files():
    seen: dict = {}
    for fname, doc in _filters().items():
        for key in doc:
            seen.setdefault(key, []).append(fname)
    twice = {k: v for k, v in seen.items() if len(v) > 1}
    assert not twice, f"defined twice (one concept, one definition): {twice}"


def test_the_clashing_names_each_mean_one_set_now():
    """The three names the design note found defined differently in two files."""
    f = _filters()
    assert "backend" in f["code-quality-paths.yml"] and "backend" not in f["backend-python-paths.yml"]
    assert "python" in f["python-paths.yml"] and "python" not in f["backend-python-paths.yml"]
    assert "frontend" in f["frontend-paths.yml"]
    ci_text = CI.read_text(encoding="utf-8")
    assert not re.search(r"^\s+frontend:\s*$", ci_text, re.M), "ci.yml carries an inline `frontend` filter again"


def step_output_problem(steps: list, filters: dict, step_id: str, key: str) -> str | None:
    """Why `steps.<step_id>.outputs.<key>` can never carry a value, or None when its producer exists.

    Two kinds of producer. A paths-filter step yields a key only if the filter file it loads defines
    it. A `run:` step yields one only if its script writes `<key>=` to `$GITHUB_OUTPUT` (#21490).
    """
    step = next((s for s in steps if s.get("id") == step_id), None)
    if step is None:
        return f"output reads steps.{step_id}, which is not a step of the `changes` job"
    if DORNY in str(step.get("uses", "")):
        loaded = step["with"]["filters"].rsplit("/", 1)[-1]
        if key not in filters[loaded]:
            return f"steps.{step_id}.outputs.{key}: {loaded} has no key {key!r}; the output would be '' forever"
        return None
    script = str(step.get("run", ""))
    if not script:
        return f"output reads steps.{step_id}, which is neither a paths-filter step nor a `run:` step"
    if not re.search(r"(?:^|[\s\"'])" + re.escape(key) + r"=[^\n]*>>\s*\"?\$GITHUB_OUTPUT", script):
        return f"steps.{step_id}.outputs.{key}: the script never writes `{key}=` to $GITHUB_OUTPUT; the output would be '' forever"
    return None


def test_every_step_output_ci_reads_exists_in_the_filter_file_that_step_loads():
    job = _changes_job()
    filters = _filters()
    text = yaml.safe_dump(job["outputs"])
    refs = set(re.findall(r"steps\.(\w+)\.outputs\.(\w+)", text))
    assert refs, "the `changes` outputs read no step output at all: the scan is vacuous"
    problems = [step_output_problem(job["steps"], filters, sid, key) for sid, key in sorted(refs)]
    assert not any(problems), [p for p in problems if p]
    assert any(DORNY in str(s.get("uses", "")) for s in job["steps"] if s.get("id") in {r[0] for r in refs})
    assert any("run" in s for s in job["steps"] if s.get("id") in {r[0] for r in refs}), "no run-step output read"


_RUN_STEP = {"id": "hold", "run": 'held=false\necho "held=${held}" >> "$GITHUB_OUTPUT"\n'}
_FILTER_STEP = {"id": "gp", "uses": "dorny/paths-filter@x", "with": {"filters": ".github/filters/a.yml"}}


def test_control_run_step_outputs_and_filter_keys_are_verified():
    steps, filters = [_RUN_STEP, _FILTER_STEP], {"a.yml": {"self": []}}
    assert step_output_problem(steps, filters, "hold", "held") is None
    assert step_output_problem(steps, filters, "gp", "self") is None
    assert "never writes" in step_output_problem(steps, filters, "hold", "nope")
    suffix_only = [{"id": "hold", "run": 'echo "withheld=true" >> "$GITHUB_OUTPUT"'}]
    assert "never writes" in step_output_problem(suffix_only, filters, "hold", "held"), "a suffix is not the key"
    assert step_output_problem(suffix_only, filters, "hold", "withheld") is None
    assert "not a step" in step_output_problem(steps, filters, "ghost", "held")
    assert "no key" in step_output_problem(steps, filters, "gp", "typo")


def test_every_output_a_gate_reads_is_published_by_changes():
    doc = yaml.safe_load(CI.read_text(encoding="utf-8"))
    published = set(doc["jobs"]["changes"]["outputs"])
    read = set(re.findall(r"needs\.changes\.outputs\.(\w+)", CI.read_text(encoding="utf-8")))
    assert read, "no gate reads the changes job: the scan is vacuous"
    assert read <= published, f"read but never published: {sorted(read - published)}"
    unread = published - read
    assert not unread, f"published but never read (dead output, or a gate that forgot its filter): {sorted(unread)}"


def test_security_scope_still_covers_what_the_two_scans_read():
    """It was security.yml's `on.pull_request.paths`: the exact union of both scans' filters plus two extras."""
    f = _filters()
    scope = _flat(f["gate-paths.yml"]["security_scope"])
    needed = _flat(f["backend-python-paths.yml"]["static_analysis"]) | _flat(f["backend-python-paths.yml"]["deps"])
    wild = {p[3:] for p in scope if p.startswith("**/")}
    uncovered = {p for p in needed - scope if not any(p == w or p.endswith("/" + w) for w in wild)}
    assert uncovered == set(), f"a scan would run on a path the PR trigger no longer admits: {sorted(uncovered)}"
    assert {"**/package*.json", ".secrets.baseline"} <= scope


@pytest.mark.parametrize(
    "fname", ["python-paths.yml", "code-quality-paths.yml", "frontend-paths.yml", "docker-paths.yml"]
)
def test_the_gate_filter_files_name_no_removed_workflow(fname):
    """A self-reference to a workflow that is gone matches nothing and reads as coverage."""
    doc = _filters()[fname]
    for key, patterns in doc.items():
        for p in _flat(patterns):
            if p.startswith(".github/workflows/") and "*" not in p:
                assert (ROOT / p).exists(), f"{fname}:{key} names {p}, which does not exist"
