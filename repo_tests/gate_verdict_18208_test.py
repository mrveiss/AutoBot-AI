# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The verdict script behind every required-context gate in ci.yml (#18208).

`.github/actions/gate-verdict/verdict.sh` is the one place the order of the checks is
decided. Its contract, in order: failed detection fails; a draft pull request fails
("draft: mark ready for review", D4); a gate that does not apply passes "not affected";
verified work passes; anything else fails. These tests drive the real script over every
branch, so a reorder that lets a draft pass, or lets a skipped suite read as verified
(#18106), reddens by name.
"""

import re

import pytest
import yaml
from repo_tests._gate_verdict_driver import BASE, SCRIPT
from repo_tests._gate_verdict_driver import run_verdict as _run
from repo_tests._gate_verdict_driver import run_verdict_env
from repo_tests._paths import repo_root


def test_the_script_exists_and_is_executable_shaped():
    assert SCRIPT.is_file()
    assert SCRIPT.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")


def test_verified_work_passes():
    rc, out = _run()
    assert rc == 0 and "verified" in out


def test_a_gate_that_does_not_apply_passes_and_says_so():
    rc, out = _run(GATE_APPLIES="false", GATE_WORK_OK="false", GATE_WORK_DETAIL="run-x=skipped")
    assert rc == 0 and "not affected" in out


def test_an_empty_detection_result_is_an_error_not_a_pass():
    """`needs.changes.result` is never empty in a real run; if it ever were, the gate must not pass."""
    rc, _ = _run(GATE_CHANGES_RESULT="", GATE_APPLIES="false")
    assert rc != 0


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
def test_failed_detection_fails_closed_even_when_nothing_applies(result):
    rc, out = _run(GATE_CHANGES_RESULT=result, GATE_APPLIES="false")
    assert rc == 1 and "path detection" in out


def test_a_draft_pull_request_fails_with_the_reason_never_skips():
    rc, out = _run(GATE_DRAFT="true", GATE_APPLIES="true", GATE_WORK_OK="false", GATE_WORK_DETAIL="run-x=skipped")
    assert rc == 1 and "draft: mark ready for review" in out


def test_a_draft_fails_even_when_the_gate_would_not_apply():
    """D4: the draft check comes BEFORE 'not affected', so a docs-only draft is red, not green."""
    rc, out = _run(GATE_DRAFT="true", GATE_APPLIES="false")
    assert rc == 1 and "draft: mark ready for review" in out


def test_a_draft_does_not_fail_the_one_context_that_runs_on_drafts():
    """verify-precommit-config carries SPDX and symlink checks that cover every PR (#17957)."""
    rc, out = _run(GATE_CONTEXT="verify-precommit-config", GATE_DRAFT="true", GATE_DRAFT_GATED="false")
    assert rc == 0, out


def test_draft_only_matters_on_pull_request():
    """A push or merge_group has no draft; a stale `true` must not fail it."""
    for event in ("push", "merge_group"):
        rc, out = _run(GATE_EVENT=event, GATE_DRAFT="true")
        assert rc == 0, (event, out)


@pytest.mark.parametrize("detail", ["run-x=skipped", "run-x=failure", "run-x=cancelled", ""])
def test_a_skipped_or_failed_suite_that_applies_is_not_evidence(detail):
    """#18106: a draft-era replay once left python-suite `skipped` with zero shards run."""
    rc, out = _run(GATE_WORK_OK="false", GATE_WORK_DETAIL=detail)
    assert rc == 1 and "did not pass" in out


@pytest.mark.parametrize(
    "missing", ["GATE_CONTEXT", "GATE_CHANGES_RESULT", "GATE_APPLIES", "GATE_WORK_OK", "GATE_EVENT"]
)
def test_a_missing_input_is_an_error_not_a_pass(missing):
    env = {k: v for k, v in BASE.items() if k != missing}
    assert run_verdict_env(env).returncode != 0


# --- ci.yml wiring of the gates (review of #19621) ---------------------------------------------
_WORKFLOWS = repo_root() / ".github" / "workflows"
_WORKFLOW_SUFFIXES = {".yml", ".yaml"}


def _ci_job(name):
    jobs = yaml.safe_load((_WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))["jobs"]
    return jobs[name]


def _step_with(job, action):
    return next(s for s in job["steps"] if str(s.get("uses", "")).endswith(action))["with"]


def test_python_suite_gate_sees_a_cancelled_provision():
    """If only provision-packages is cancelled the shards read skipped: the gate must end cancelled, not red."""
    job = _ci_job("python-suite")
    assert "provision-packages" in job["needs"]
    results = _step_with(job, "cancel-run-on-cancelled-upstream")["results"]
    assert "needs.provision-packages.result" in results
    # control: the shard result is still there, so the assertion above is not satisfied by a rewrite
    assert "needs.python-shard.result" in results


def test_types_gate_applies_and_fails_on_either_types_job():
    """The SLM freshness job is a real part of the verdict: it applies it, and its failure fails the gate."""
    verdict = _step_with(_ci_job("verify-generated-types"), "gate-verdict")
    assert "run_types" in verdict["applies"] and "run_slm_types" in verdict["applies"]
    assert "outputs.ok" in verdict["work-ok"] and "outputs.slm_ok" in verdict["work-ok"]
    body = yaml.safe_load((_WORKFLOWS / "_gate-generated-types.yml").read_text(encoding="utf-8"))
    assert "slm_ok" in body[True]["workflow_call"]["outputs"]
    slm = body["jobs"]["verify-generated-types-slm"]
    assert slm["outputs"]["ok"] == "${{ steps.done.outputs.ok }}"
    assert slm["steps"][-1]["id"] == "done"  # last step, so it is reached only when every step passed


def _workflow_files(directory):
    return [p for p in sorted(directory.iterdir()) if p.suffix in _WORKFLOW_SUFFIXES]


def _inherits(text):
    return [m.start() for m in re.finditer(r"""^\s*secrets:\s*(?:inherit|"inherit"|'inherit')(?![\w-])""", text, re.M)]


def test_no_workflow_passes_every_secret_with_inherit():
    """Each reusable body names the secrets it reads; the caller passes those names and nothing else."""
    workflows = _workflow_files(_WORKFLOWS)
    # A listing that found nothing would report the same clean result as a compliant tree.
    assert len(workflows) >= 40, f"only {len(workflows)} workflows listed: the sweep did not look"
    offenders = [p.name for p in workflows if _inherits(p.read_text(encoding="utf-8"))]
    assert not offenders, f"`secrets: inherit` in {offenders}: pass the named secrets instead"


def test_the_inherit_detector_catches_a_planted_one():
    assert _inherits("jobs:\n  x:\n    uses: ./a.yml\n    secrets: inherit  # note\n")
    assert not _inherits("jobs:\n  x:\n    secrets:\n      A: ${{ secrets.A }}\n")


@pytest.mark.parametrize("value", ['"inherit"', "'inherit'", "inherit"])
def test_the_inherit_detector_catches_each_quoted_form(value):
    assert _inherits(f"jobs:\n  x:\n    secrets: {value}\n")


def test_the_sweep_reads_both_yaml_suffixes(tmp_path):
    for name in ("a.yml", "b.yaml", "c.txt"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert [p.name for p in _workflow_files(tmp_path)] == ["a.yml", "b.yaml"]


@pytest.mark.parametrize(
    ("body", "secret"),
    [("_gate-code-quality.yml", "CONVENTIONS_DENYLIST"), ("_gate-ai-security-review.yml", "CLAUDE_CODE_OAUTH_TOKEN")],
)
def test_a_reusable_body_declares_exactly_the_secrets_it_reads(body, secret):
    text = (_WORKFLOWS / body).read_text(encoding="utf-8")
    declared = set(yaml.safe_load(text)[True]["workflow_call"].get("secrets", {}))
    read = set(re.findall(r"secrets\.([A-Z0-9_]+)", text)) - {"GITHUB_TOKEN"}
    assert declared == read == {secret}
    caller = {
        j: v
        for j, v in yaml.safe_load((_WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))["jobs"].items()
        if v.get("uses", "").endswith(body)
    }
    assert [set(v["secrets"]) for v in caller.values()] == [{secret}]
