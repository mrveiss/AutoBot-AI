# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The reusable `changes` job is a zero-behaviour-change refactor (#15360).

Sixteen workflows each carried  their own `changes` job (checkout + dorny/paths-filter).
They now call `.github/workflows/_changes.yml`. "Zero change" is a claim about sixteen
things at once, so it is frozen as data: `fixtures/pre_15360_changes_jobs.json` was
generated from `origin/main` BEFORE the conversion (`python -m
repo_tests.changes_job_equivalence_15360_test` regenerates it from a git ref, for
provenance only). Each caller is resolved through `_changes.yml` (its inputs and their
defaults) into the same record and compared, field by field:

* the filter source -- its path or inline form; its ENTRIES are judged by rules, not frozen digests
  (#21205): the snapshot is kept in order, every addition cites its issue where it is written, and
  no entry the merge base had goes without a `# retired #NNNN: '<entry>'` tombstone;
* whether `base` is the merge group's base_sha, and whether the step is PR-only;
* checkout, timeout, runner, step ids and the pinned action refs;
* the parsed `on:` block, where a filter entry the migration gate gained must be in its `on.push.paths`;
* the outputs every other job reads from `needs.changes.*`.

An event matrix then evaluates the resolved record per event, so the answer is "same
base, same run or skip" rather than "same fields".

What this cannot prove: how GitHub evaluates the reusable call at run time. That is
only proven by CI running it.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

import pytest
import yaml
from repo_tests._filter_entries import (
    agreed_entries,
    doc_entries,
    removed_without_tombstone,
    split_against_snapshot,
    uncited,
)
from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_text

REPO = repo_root()
WORKFLOWS = ".github/workflows"
FIXTURE = Path(__file__).parent / "fixtures" / "pre_15360_changes_jobs.json"
REUSABLE_USES = f"./{WORKFLOWS}/_changes.yml"
CALLERS = (
    "api-wiring security startup-import-smoke backend-required-context code-quality "
    "code-quality-required-context frontend-test frontend-required-context python-required-context "
    "docker-smoke-required-context docker-smoke-test npm-package-tests slm-frontend-check "
    "verify-generated-types migration-gate ai-security-review"
).split()
#: The ONLY `on:` delta allowed: callers whose `paths:` list their own workflow file gained
#: `_changes.yml` beside it, because that is where their change-detection logic now lives.
#: workflow -> the events whose `paths:` carry the new entry. Pinned, not derived.
ON_ADDED_EVENTS = {
    "api-wiring": ("push",),
    "security": ("pull_request",),
    "startup-import-smoke": ("push",),
    "code-quality": ("push",),
    "frontend-test": ("push",),
    "npm-package-tests": ("push", "pull_request"),
    "slm-frontend-check": ("push", "pull_request"),
    "verify-generated-types": ("push",),
    "migration-gate": ("push",),
    "ai-security-review": ("pull_request",),
}

#: The workflow whose inline `migrations` filter is mirrored by its own `on.push.paths`: every entry
#: the filter gained must be in that list too (#17822), and nothing else may be.
MIRRORED_FILTER_WORKFLOW = "migration-gate"
MIRRORED_FILTER_KEY = "migrations"

EVENTS = ("push", "pull_request", "merge_group", "schedule", "workflow_dispatch")
MG_SHA = "merge-group-base-sha"  # a stand-in value; only its presence or absence is compared
PRE_BASE = "${{ github.event.merge_group.base_sha || '' }}"
POST_BASE = "${{ inputs.merge_group_base && github.event.merge_group.base_sha || '' }}"
POST_DORNY_IF = "${{ !inputs.pr_only || github.event_name == 'pull_request' }}"
PRE_PR_ONLY_IF = "github.event_name == 'pull_request'"
DORNY = "dorny/paths-filter@ceb8a2b8f2d89434be7ff52d3de7ec3738c5cc9d"
CHECKOUT = "actions/checkout@v7"
GITHUB_DEFAULT_TIMEOUT = 360

ReadFile = Callable[[str], bytes]


def _worktree_reader(rel: str) -> bytes:
    return (REPO / rel).read_bytes()


def _git_reader(ref: str) -> ReadFile:
    def read(rel: str) -> bytes:
        return subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=REPO, capture_output=True, check=True).stdout

    return read


def filter_source(raw: str, read: ReadFile) -> dict:
    """dorny's own rule: no newline and no colon means a path, else inline YAML."""
    if "\n" in raw or ":" in raw:
        return {"inline": yaml.safe_load(raw)}
    return {"file": raw.strip(), "content": yaml.safe_load(read(raw.strip()))}


def filter_text(raw: str, read: ReadFile) -> tuple[str | None, str]:
    """`(path or None, the raw text)` of the filter source, for the line-level reading."""
    if "\n" in raw or ":" in raw:
        return None, raw
    return raw.strip(), read(raw.strip()).decode("utf-8")


ADDED_ENTRY = f"{WORKFLOWS}/_changes.yml"


def strip_added_on_entries(doc_on: dict, name: str | None, mirrored: list[str]) -> dict:
    """The parsed `on:` with the `_changes.yml` additions and the mirrored filter entries removed.

    Asserts each removed entry is exactly where it is declared (`ON_ADDED_EVENTS`, or the mirrored
    filter's `on.push.paths`), once; the comparison with the snapshot then fails on anything else.
    """
    parsed = {e: dict(v) if isinstance(v, dict) else v for e, v in doc_on.items()}
    for event in ON_ADDED_EVENTS.get(name, ()) if name else ():
        paths = list(parsed[event]["paths"])
        assert paths.count(ADDED_ENTRY) == 1, f"{name}: on.{event}.paths lacks the pinned entry"
        parsed[event]["paths"] = [p for p in paths if p != ADDED_ENTRY]
    for entry in mirrored:
        paths = list(parsed["push"]["paths"])
        assert paths.count(entry) == 1, f"{name}: on.push.paths lacks the filter entry {entry}"
        parsed["push"]["paths"] = [p for p in paths if p != entry]
    return parsed


def _common(text: str, doc: dict, name: str | None = None, mirrored: list[str] = ()) -> dict:
    return {
        "on": strip_added_on_entries(doc.get(True, doc.get("on")), name, list(mirrored)),
        "consumed_outputs": sorted(set(re.findall(r"needs\.changes\.outputs\.(\w+)", text))),
        "display_name": doc["jobs"]["changes"].get("name"),
        "job_level_extras": sorted(set(doc["jobs"]["changes"]) - _JOB_KEYS),
    }


_JOB_KEYS = {"name", "runs-on", "timeout-minutes", "outputs", "steps", "uses", "with"}


def pre_record(text: str, read: ReadFile) -> dict:
    """The record of a `changes` job in its original, self-contained shape."""
    doc = yaml.safe_load(text)
    job = doc["jobs"]["changes"]
    steps = job["steps"]
    dorny = [s for s in steps if str(s.get("uses", "")).startswith("dorny/paths-filter@")]
    checkout = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert len(dorny) == 1 and len(checkout) <= 1 and len(steps) == len(dorny) + len(checkout)
    with_ = dorny[0]["with"]
    assert set(with_) <= {"base", "filters"}, with_
    rec = _common(text, doc)
    rec.update(
        filters=filter_source(with_["filters"], read),
        base_is_merge_group=with_.get("base") == PRE_BASE,
        pr_only=dorny[0].get("if") == PRE_PR_ONLY_IF,
        checkout=bool(checkout),
        checkout_uses=checkout[0]["uses"] if checkout else None,
        dorny_uses=dorny[0]["uses"],
        step_id=dorny[0].get("id"),
        timeout=job.get("timeout-minutes", GITHUB_DEFAULT_TIMEOUT),
        runs_on=job["runs-on"],
        outputs=sorted(job["outputs"]),
        declared_outputs_read_from_step=all(
            v == "${{ steps.filter.outputs." + k + " }}" for k, v in job["outputs"].items()
        ),
    )
    assert with_.get("base", PRE_BASE) == PRE_BASE and dorny[0].get("if", PRE_PR_ONLY_IF) == PRE_PR_ONLY_IF
    return rec


def _input(reusable: dict, call_with: dict, name: str):
    spec = reusable[True if True in reusable else "on"]["workflow_call"]["inputs"][name]
    return call_with.get(name, spec.get("default"))


def post_record(text: str, reusable_text: str, read: ReadFile, name: str) -> dict:
    """The same record, resolved through the caller's `with:` and `_changes.yml`."""
    doc, reusable = yaml.safe_load(text), yaml.safe_load(reusable_text)
    job = doc["jobs"]["changes"]
    assert job.get("uses") == REUSABLE_USES, "the caller does not use the reusable job"
    call = job.get("with") or {}
    inner = reusable["jobs"]["changes"]
    co = [s for s in inner["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")]
    dorny = [s for s in inner["steps"] if str(s.get("uses", "")).startswith("dorny/paths-filter@")]
    assert len(co) == 1 and len(dorny) == 1 and co[0]["if"] == "${{ inputs.checkout }}"
    assert dorny[0]["with"]["base"] == POST_BASE and dorny[0]["if"] == POST_DORNY_IF
    assert dorny[0]["with"]["filters"] == "${{ inputs.filters }}"
    assert inner["timeout-minutes"] == "${{ inputs.timeout_minutes }}"
    path, ftext = filter_text(call["filters"], read)
    pre = _load_pre()[name]["filters"]
    mirrored = _mirrored_entries(name, ftext, pre)
    rec = _common(text, doc, name, mirrored)
    rec.update(
        filters=filter_source(call["filters"], read),
        filters_path=path,
        filters_text=ftext,
        base_is_merge_group=bool(_input(reusable, call, "merge_group_base")),
        pr_only=bool(_input(reusable, call, "pr_only")),
        checkout=bool(_input(reusable, call, "checkout")),
        checkout_uses=co[0]["uses"],
        dorny_uses=dorny[0]["uses"],
        step_id=dorny[0].get("id"),
        timeout=_input(reusable, call, "timeout_minutes"),
        runs_on=inner["runs-on"],
        outputs=sorted(reusable[True if True in reusable else "on"]["workflow_call"]["outputs"]),
        declared_outputs_read_from_step=all(
            v == "${{ steps.filter.outputs." + k + " }}" for k, v in inner["outputs"].items()
        ),
    )
    assert set(call) <= {"filters", "merge_group_base", "pr_only", "checkout", "timeout_minutes"}, call
    return rec


def evaluate(rec: dict, event: str) -> dict:
    """What the dorny step receives and whether it runs, for one event."""
    base = MG_SHA if (rec["base_is_merge_group"] and event == "merge_group") else ""
    runs = (not rec["pr_only"]) or event == "pull_request"
    return {"base": base, "dorny_runs": runs, "checkout_runs": rec["checkout"]}


def _load_pre() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _post(name: str) -> dict:
    text = (REPO / WORKFLOWS / f"{name}.yml").read_text(encoding="utf-8")
    reusable = (REPO / WORKFLOWS / "_changes.yml").read_text(encoding="utf-8")
    return post_record(text, reusable, _worktree_reader, name)


def _generate(ref: str) -> dict:
    read = _git_reader(ref)
    return {n: pre_record(read(f"{WORKFLOWS}/{n}.yml").decode(), read) for n in CALLERS}


_EQUAL_FIELDS = (
    "filters",
    "base_is_merge_group",
    "pr_only",
    "checkout",
    "checkout_uses",
    "dorny_uses",
    "step_id",
    "timeout",
    "runs_on",
    "display_name",
    "on",
    "consumed_outputs",
    "job_level_extras",
    "declared_outputs_read_from_step",
)


def test_the_fixture_covers_every_caller_and_is_not_vacuous():
    pre = _load_pre()
    assert sorted(pre) == sorted(CALLERS)
    assert any(r["base_is_merge_group"] for r in pre.values()), "no merge-group caller frozen"
    assert any(not r["base_is_merge_group"] for r in pre.values())
    assert [n for n, r in pre.items() if r["pr_only"]] == ["docker-smoke-test"]
    assert {r["timeout"] for r in pre.values()} == {10, GITHUB_DEFAULT_TIMEOUT}
    assert any("inline" in r["filters"] for r in pre.values()) and any("file" in r["filters"] for r in pre.values())


def _snapshot(pre: dict) -> list[tuple[str, str]]:
    """The pre-conversion filter's entries, from its stored parse (`content`, or `inline` for an inline one)."""
    return doc_entries(pre.get("content", pre.get("inline")))


def _mirrored_entries(name: str, text: str, pre: dict) -> list[str]:
    """The entries an inline filter gained, which its own `on.push.paths` must mirror (rule 4)."""
    if name != MIRRORED_FILTER_WORKFLOW:
        return []
    _, new = split_against_snapshot(_snapshot(pre), agreed_entries(text))
    return [e.value for e in new if e.key == MIRRORED_FILTER_KEY]


@pytest.mark.parametrize("name", CALLERS)
@pytest.mark.parametrize("field", _EQUAL_FIELDS)
def test_each_resolved_field_equals_the_pre_conversion_value(name, field):
    post, pre = _post(name)[field], _load_pre()[name][field]
    if field == "filters":  # the entries are judged by the rules below; the shape and source must agree
        assert ("file" in post, post.get("file")) == ("file" in pre, pre.get("file"))
        assert set(post.get("content", post.get("inline"))) == set(pre.get("content", pre.get("inline")))
        return
    assert post == pre


@pytest.mark.parametrize("name", CALLERS)
def test_a_filter_keeps_its_snapshot_and_declares_every_addition_in_place(name):
    """Rules 1 and 2: the snapshot entries survive in order; each new entry cites its issue where it is written."""
    post = _post(name)
    found = uncited(post["filters_text"], _snapshot(_load_pre()[name]["filters"]))
    assert not found, f"{name}: " + "; ".join(found)


def _head_and_base_texts(name: str) -> tuple[str, str | None, str]:
    """`(head filter text, the same at the base, the file whose tombstones count)` for one caller."""
    post = _post(name)
    if post["filters_path"] is not None:
        return post["filters_text"], base_text(REPO, post["filters_path"]), post["filters_text"]
    rel = f"{WORKFLOWS}/{name}.yml"
    base = base_text(REPO, rel)
    inline = None if base is None else (yaml.safe_load(base)["jobs"]["changes"].get("with") or {}).get("filters")
    return post["filters_text"], inline, (REPO / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", CALLERS)
def test_no_entry_the_merge_base_had_is_removed_without_a_tombstone(name):
    """Rule 3. `BaseUnavailable` is never a pass: it propagates and the test errors."""
    head, base, tombstones_in = _head_and_base_texts(name)
    found = removed_without_tombstone(base, head, tombstones_in)
    assert not found, f"{name}: " + "; ".join(found)


def test_the_filters_widened_on_purpose_are_not_a_vacuous_set():
    """Some caller's filter file and some inline filter really did gain entries, so rules 1-4 judge something."""
    gained = {}
    for name in CALLERS:
        _, new = split_against_snapshot(
            _snapshot(_load_pre()[name]["filters"]), agreed_entries(_post(name)["filters_text"])
        )
        gained[name] = len(new)
    assert any(n for k, n in gained.items() if k in ("python-required-context", "frontend-test", "docker-smoke-test"))
    assert gained[MIRRORED_FILTER_WORKFLOW] > 0, "the mirrored inline filter gained nothing; rule 4 judges nothing"


@pytest.mark.parametrize("name", CALLERS)
def test_the_reusable_job_still_provides_every_output_the_job_had(name):
    pre, post = _load_pre()[name], _post(name)
    assert set(pre["outputs"]) <= set(post["outputs"])
    assert set(post["consumed_outputs"]) <= set(pre["outputs"])


@pytest.mark.parametrize("name", CALLERS)
@pytest.mark.parametrize("event", EVENTS)
def test_the_event_matrix_gives_the_same_base_and_the_same_run_or_skip(name, event):
    assert evaluate(_post(name), event) == evaluate(_load_pre()[name], event)


def test_the_event_matrix_is_not_vacuous():
    pre = _load_pre()
    mg = [n for n, r in pre.items() if evaluate(r, "merge_group")["base"] == MG_SHA]
    assert mg and set(mg) < set(CALLERS), "the matrix must see both a base and no base on merge_group"
    assert not evaluate(pre["docker-smoke-test"], "push")["dorny_runs"]
    assert evaluate(pre["docker-smoke-test"], "pull_request")["dorny_runs"]
    assert all(evaluate(r, "push")["base"] == "" for r in pre.values())


def test_every_output_the_reusable_job_declares_reads_the_matching_step_output():
    inner = yaml.safe_load((REPO / WORKFLOWS / "_changes.yml").read_text(encoding="utf-8"))
    wf = inner[True if True in inner else "on"]["workflow_call"]["outputs"]
    for key, spec in wf.items():
        assert spec["value"] == "${{ jobs.changes.outputs." + key + " }}"
        assert inner["jobs"]["changes"]["outputs"][key] == "${{ steps.filter.outputs." + key + " }}"
    assert len(wf) == 15  # the union of every caller's outputs


def test_the_pinned_dorny_ref_carries_its_version_comment():
    text = (REPO / WORKFLOWS / "_changes.yml").read_text(encoding="utf-8")
    assert f"uses: {DORNY}  # v4.0.3" in text


if __name__ == "__main__":
    FIXTURE.write_text(
        json.dumps(_generate(sys.argv[1] if len(sys.argv) > 1 else "origin/main"), indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
