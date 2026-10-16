# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""auto-fix-generated-types can be dispatched on a branch (#18500).

A merge train learned that its combined tree needs an ``api.ts`` patch only by
running the full CI suite, because the workflow triggered on ``pull_request``
alone and read ``github.head_ref`` / the PR's head repo everywhere. These pin
the three acceptance criteria against the parsed workflow.

**What these do not cover.** No run is dispatched; that the job produces the
patch on a real train branch is shown by the first dispatch.
"""

from __future__ import annotations

import yaml
from repo_tests._paths import repo_root

_WORKFLOW = repo_root() / ".github" / "workflows" / "auto-fix-generated-types.yml"


def _doc() -> dict:
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    doc["on"] = doc.pop(True, doc.get("on"))  # PyYAML reads the bare key `on` as True
    return doc


def test_dispatch_runs_the_job_on_the_dispatched_ref() -> None:
    doc = _doc()
    assert "workflow_dispatch" in doc["on"]
    job = doc["jobs"]["autofix-types"]
    assert "github.event_name == 'workflow_dispatch'" in job["if"]
    checkout = next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "${{ github.head_ref || github.ref }}"
    assert (
        "github.head_ref || github.ref" in doc["concurrency"]["group"]
    ), "dispatches on different branches would cancel each other"


def test_the_parked_run_approval_stays_pull_request_only() -> None:
    gate = _doc()["jobs"]["approve-parked-runs"]["if"]
    assert "github.event.pull_request.head.repo.full_name == github.repository" in gate
    assert "workflow_dispatch" not in gate


def test_the_patch_artifact_is_uploaded_whatever_the_event() -> None:
    steps = _doc()["jobs"]["autofix-types"]["steps"]
    upload = next(s for s in steps if s.get("with", {}).get("name") == "generated-types-patch")
    assert str(upload.get("if", "")).strip() == "failure()", "the upload must not depend on the triggering event"
