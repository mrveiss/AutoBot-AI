# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The dispatch contract between the PR coordinator and the workflows (#20825).

The coordinator (dev-skills ``scripts/pr-coordinator``, ``dispatch_workflow``) dispatches six workflows with
three inputs; ``ci.yml``'s ``fan-out`` dispatches every path-filtered advisory workflow ("satellite") with the
same three. A rename on either side makes every dispatch answer HTTP 422, so the names are pinned here:

* the six coordinator-dispatched files declare ``pr_number``, ``head_sha``, ``base_sha`` as REQUIRED strings;
* every satellite declares them (optional: ten of them keep a manual ``workflow_dispatch`` of their own);
* the keys of ``.github/filters/satellite-paths*.yml`` are exactly the satellite workflow files;
* a dispatched run validates its pins (``pr-context``) before any step reads a fact it looked up, and keys its
  concurrency group on the pull request number, cancelling superseded runs in PR mode only.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

import pytest
import yaml
from repo_tests._pr_dispatch import (
    COORDINATOR_DISPATCHED,
    PINS,
    WORKFLOWS,
    dispatch_inputs,
    load,
    satellite_keys,
    workflow_files,
)

#: Dispatched workflows whose concurrency group is deliberately NOT per pull request, with the reason.
GLOBAL_GROUP = {"marker-tests.yml": "one queue for the single self-hosted runner; runs wait their turn and are never cancelled"}

FANOUT_BASE_LISTS = re.compile(r'(main_only|main_or_release|release_only)="([^"]*)"')


def _declaring_pins() -> Set[str]:
    return {p.name for p in workflow_files() if set(PINS) <= set(dispatch_inputs(load(p)))}


def pin_problems(doc: Dict[Any, Any], *, required: bool) -> List[str]:
    inputs = dispatch_inputs(doc)
    found = [f"missing input `{pin}`" for pin in PINS if pin not in inputs]
    for pin in PINS:
        spec = inputs.get(pin) or {}
        if pin in inputs and spec.get("type") != "string":
            found.append(f"`{pin}` is not a string input")
        if pin in inputs and bool(spec.get("required")) != required:
            found.append(f"`{pin}` must be {'required' if required else 'optional'}")
    return found


def unvalidated_reads(job: Dict[str, Any]) -> List[str]:
    """Steps reading ``steps.pr.outputs`` before the ``pr-context`` step that defines ``pr`` ran."""
    steps = job.get("steps") or []
    defined = next((i for i, s in enumerate(steps) if s.get("id") == "pr" and "pr-context" in str(s.get("uses"))), None)
    reads = [i for i, s in enumerate(steps) if "steps.pr." in yaml.safe_dump(s) and s.get("id") != "pr"]
    return [str(i) for i in reads if defined is None or i < defined]


def test_the_coordinator_dispatches_six_workflows_with_required_pins() -> None:
    assert len(COORDINATOR_DISPATCHED) == 6
    problems = {n: pin_problems(load(WORKFLOWS / n), required=True) for n in COORDINATOR_DISPATCHED}
    assert {n: p for n, p in problems.items() if p} == {}


def test_every_satellite_declares_the_pins_and_the_filter_keys_are_the_satellite_files() -> None:
    keys = satellite_keys()
    assert len(keys) >= 25, f"the filter files hold {len(keys)} keys; the parse found almost nothing"
    files = {p.stem: p for p in workflow_files()}
    assert not (keys - set(files)), f"filter keys with no workflow file: {sorted(keys - set(files))}"
    assert {n: pin_problems(load(files[k]), required=False) for k in keys for n in [files[k].name] if pin_problems(load(files[k]), required=False)} == {}
    declaring = {n.removesuffix(".yml") for n in _declaring_pins()} - {c.removesuffix(".yml") for c in COORDINATOR_DISPATCHED}
    assert declaring == keys, f"declares the pins without a filter key: {sorted(declaring - keys)}; key without pins: {sorted(keys - declaring)}"


def test_every_filter_key_is_unique_across_the_filter_directory() -> None:
    seen: Dict[str, str] = {}
    for path in sorted((WORKFLOWS.parent / "filters").glob("*.yml")):
        for key in load(path):
            assert key not in seen, f"{key} is in both {seen[key]} and {path.name}"
            seen[key] = path.name


def test_fan_out_dispatches_only_workflows_that_exist_and_names_their_branches() -> None:
    ci = load(WORKFLOWS / "ci.yml")
    script = "\n".join(s.get("run", "") for s in ci["jobs"]["fan-out"]["steps"])
    lists = {name: set(body.split()) for name, body in FANOUT_BASE_LISTS.findall(script)}
    assert set(lists) == {"main_only", "main_or_release", "release_only"}, lists
    named = set().union(*lists.values())
    assert named <= satellite_keys(), f"branch lists name non-satellites: {sorted(named - satellite_keys())}"
    for pin, source in (("pr_number", "PR_NUMBER"), ("head_sha", "HEAD_SHA"), ("base_sha", "BASE_SHA")):
        assert f'-f {pin}="${{{source}}}"' in script, f"fan-out does not pass {pin}"


def test_the_pins_are_validated_before_any_looked_up_fact_is_read() -> None:
    checked = 0
    for name in (*COORDINATOR_DISPATCHED, *(f"{k}.yml" for k in satellite_keys())):
        for job_name, job in (load(WORKFLOWS / name).get("jobs") or {}).items():
            assert unvalidated_reads(job) == [], f"{name}:{job_name} reads steps.pr before pr-context"
            checked += 1
    assert checked > 40


def test_a_dispatched_workflow_calls_pr_context_and_keys_its_group_on_the_pull_request() -> None:
    names = [*COORDINATOR_DISPATCHED, *(f"{k}.yml" for k in sorted(satellite_keys()))]
    for name in names:
        doc = load(WORKFLOWS / name)
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "./.github/actions/pr-context" in text, f"{name} never validates its pins (pr-context)"
        group = (doc.get("concurrency") or {}).get("group", "") if isinstance(doc.get("concurrency"), dict) else ""
        if name in GLOBAL_GROUP:
            assert doc["concurrency"].get("cancel-in-progress") is False, f"{name}: a global group must never cancel"
            continue
        assert "inputs.pr_number" in group, f"{name}: concurrency group {group!r} is not keyed on the pull request"
        cancel = doc["concurrency"].get("cancel-in-progress")
        assert cancel in ("${{ inputs.pr_number != '' }}", False), f"{name}: cancel-in-progress {cancel!r} must cancel in PR mode only or never"


def test_ci_is_dispatched_and_the_other_events_keep_their_groups() -> None:
    ci = load(WORKFLOWS / "ci.yml")
    group = ci["concurrency"]["group"]
    assert "github.event_name == 'push' && github.sha" in group, "a push run keys on its own commit (#19283)"
    assert ci["concurrency"]["cancel-in-progress"] == "${{ inputs.pr_number != '' }}"
    assert "run-name" in ci and "inputs.head_sha" in ci["run-name"]


def test_the_gates_are_always_and_read_the_looked_up_facts() -> None:
    ci = load(WORKFLOWS / "ci.yml")
    gates = [j for j in ci["jobs"].values() if any("gate-verdict" in str(s.get("uses")) for s in j.get("steps", []))]
    assert len(gates) == 9, f"{len(gates)} gate jobs"
    for job in gates:
        verdict = next(s for s in job["steps"] if "gate-verdict" in str(s.get("uses")))["with"]
        assert job["if"] == "${{ always() }}"
        assert verdict["admitted"] == "${{ needs.changes.outputs.admitted == 'true' }}"
        assert verdict["draft"] == "${{ needs.changes.outputs.draft == 'true' }}"


# --- known-bad controls: each way the contract breaks must be seen ---------------------------------------


def _doc(inputs: Dict[str, Any]) -> Dict[Any, Any]:
    return {True: {"workflow_dispatch": {"inputs": inputs}}}


def _spec(required: bool) -> Dict[str, Any]:
    return {"type": "string", "required": required}


def test_control_a_missing_a_renamed_and_a_mistyped_pin_are_caught() -> None:
    good = {pin: _spec(True) for pin in PINS}
    assert pin_problems(_doc(good), required=True) == []
    assert any("head_sha" in p for p in pin_problems(_doc({k: v for k, v in good.items() if k != "head_sha"}), required=True))
    renamed = {("base" if k == "base_sha" else k): v for k, v in good.items()}
    assert any("base_sha" in p for p in pin_problems(_doc(renamed), required=True))
    assert any("not a string" in p for p in pin_problems(_doc({**good, "pr_number": {"type": "number", "required": True}}), required=True))
    assert any("must be optional" in p for p in pin_problems(_doc(good), required=False))
    assert any("must be required" in p for p in pin_problems(_doc({pin: _spec(False) for pin in PINS}), required=True))


def test_control_a_step_reading_the_context_before_pr_context_is_caught() -> None:
    ctx = {"id": "pr", "uses": "./.github/actions/pr-context"}
    read = {"run": "echo ${{ steps.pr.outputs.number }}"}
    assert unvalidated_reads({"steps": [ctx, read]}) == []
    assert unvalidated_reads({"steps": [read, ctx]}) == ["0"]
    assert unvalidated_reads({"steps": [read]}) == ["0"]


def test_control_a_filter_key_without_a_file_and_a_file_without_a_key_are_both_visible() -> None:
    keys = satellite_keys()
    files = {p.stem for p in workflow_files()}
    assert "no-such-workflow" not in files and ("no-such-workflow" in (keys | {"no-such-workflow"}) - files)
    assert files - keys, "control: most workflow files are not satellites, so a file with pins and no key would be a difference"


@pytest.mark.parametrize("name", ["ci.yml", "no-commit-trailers.yml", "pr-blocking-findings.yml"])
def test_control_the_required_context_workflows_are_in_the_dispatched_set(name: str) -> None:
    assert name in COORDINATOR_DISPATCHED
