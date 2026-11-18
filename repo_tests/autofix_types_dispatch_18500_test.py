# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The generated-types autofix can be dispatched on a branch (#18500).

A merge train learned that its combined tree needs an ``api.ts`` patch only by
running the full CI suite. The steps now live once in a composite action. The
``pull_request`` workflow checks out the PR head and runs it; a dispatch-only
workflow does a plain checkout of the dispatched branch and runs the same action.

Why this shape: CodeQL's ``actions/cache-poisoning/poisonable-step`` read a
checkout of ``github.head_ref`` -- and, in a reusable workflow, of
``inputs.ref`` -- in any dispatch-triggerable workflow as untrusted code with
default-branch cache access, and its control-check model never reads
``github.event_name`` or a step ``if:``. Three such shapes were ejected (train
23). These tests pin that no dispatch path checks out any computed ref.

**What these do not cover.** No run is dispatched and CodeQL is not run here;
the PR's own CodeQL check and the first train dispatch are the end-to-end proof.
"""

from __future__ import annotations

import yaml
from repo_tests._paths import repo_root

_ROOT = repo_root()
_ACTION_PATH = ".github/actions/generated-types-autofix/action.yml"
_ACTION_USE = "./.github/actions/generated-types-autofix"  # how a workflow names the local action


def _doc(rel: str) -> dict:
    doc = yaml.safe_load((_ROOT / rel).read_text(encoding="utf-8"))
    if True in doc:
        doc["on"] = doc.pop(True)  # PyYAML reads the bare key `on` as True
    return doc


def _steps(rel: str) -> list[dict]:
    return _doc(rel)["jobs"]["autofix-types"]["steps"]


def test_dispatch_checks_out_the_dispatched_branch_with_no_ref_and_runs_the_action() -> None:
    doc = _doc(".github/workflows/dispatch-generated-types.yml")
    assert set(doc["on"]) == {"workflow_dispatch"}
    checkout, action = _steps(".github/workflows/dispatch-generated-types.yml")
    assert (
        checkout["uses"].startswith("actions/checkout@") and "with" not in checkout
    ), "a dispatch checkout takes no ref"
    assert action["uses"] == _ACTION_USE
    assert (
        doc["concurrency"]["group"] == "${{ github.workflow }}-${{ github.ref }}"
    ), "dispatches on different branches must not cancel each other"


def test_the_pull_request_caller_cannot_be_dispatched() -> None:
    doc = _doc(".github/workflows/auto-fix-generated-types.yml")
    assert "workflow_dispatch" not in doc["on"], "a PR-head checkout must never sit in a dispatch-triggerable workflow"
    checkout, action = _steps(".github/workflows/auto-fix-generated-types.yml")
    assert checkout["with"]["ref"] == "${{ github.head_ref }}" and action["uses"] == _ACTION_USE


def test_the_action_checks_out_nothing() -> None:
    steps = _doc(_ACTION_PATH)["runs"]["steps"]
    assert steps, "the composite action has no steps"
    assert not [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")]


def test_the_parked_run_approval_stays_pull_request_only() -> None:
    gate = _doc(".github/workflows/auto-fix-generated-types.yml")["jobs"]["approve-parked-runs"]["if"]
    assert "github.event.pull_request.head.repo.full_name == github.repository" in gate


def test_the_patch_artifact_is_uploaded_whatever_the_caller() -> None:
    steps = _doc(_ACTION_PATH)["runs"]["steps"]
    upload = next(s for s in steps if s.get("with", {}).get("name") == "generated-types-patch")
    assert str(upload.get("if", "")).strip() == "failure()"
