# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A PR into ``release`` is judged only on commits not already on main (#19466).

Owner ruling 2026-10-24: "Gates judge only new commits." The rule has one home,
``.github/actions/release-promotion-base``; its script runs here against a ``gh`` stub
that answers through the REAL ``jq`` with the script's own ``--jq`` expression, so the
parsing is exercised, not restated. The pairs matter: a script that always yields a base
would pass the release case and break every PR into main, and one that yields empty on
a failed compare would turn "could not read the base" into "nothing new to judge".
"""

from __future__ import annotations

import json
import os
import shutil

# Fixed argv, no user input.
import subprocess  # nosec B404
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

ACTION_DIR = repo_root() / ".github" / "actions" / "release-promotion-base"
SCRIPT = ACTION_DIR / "release_promotion_base.sh"
WORKFLOWS = repo_root() / ".github" / "workflows"
MERGE_BASE = "c255b9974d" + "0" * 30

_GH_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$STATE/gh_calls"
if [ "${GH_FAIL:-0}" = "1" ]; then echo "gh: HTTP 502" >&2; exit 1; fi
jq_expr=""; prev=""
for arg in "$@"; do
  if [ "$prev" = "--jq" ]; then jq_expr="$arg"; fi
  prev="$arg"
done
exec "__JQ__" -r "$jq_expr" < "$GH_FIXTURE_JSON"
"""


def _run(tmp_path: Path, *, event: str, base_ref: str, response: dict | None = None, fail: bool = False):
    if shutil.which("jq") is None:
        pytest.skip("jq is not installed; the stub answers through the real jq")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "gh"
    stub.write_text(_GH_STUB.replace("__JQ__", shutil.which("jq")), encoding="utf-8")
    stub.chmod(0o755)
    fixture = tmp_path / "compare.json"
    fixture.write_text(json.dumps(response or {}), encoding="utf-8")
    out = tmp_path / "github_output"
    out.write_text("", encoding="utf-8")
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "STATE": str(tmp_path),
        "GH_FIXTURE_JSON": str(fixture),
        "GH_FAIL": "1" if fail else "0",
        "GITHUB_OUTPUT": str(out),
        "EVENT_NAME": event,
        "BASE_REF": base_ref,
        "HEAD_SHA": "f" * 40,
        "REPO": "owner/repo",
        "RELEASE_BRANCH": "release",
        "INTEGRATION_BRANCH": "main",
        "FETCH": "false",
    }
    proc = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30)  # nosec B603
    calls_file = tmp_path / "gh_calls"
    calls = calls_file.read_text(encoding="utf-8").splitlines() if calls_file.exists() else []
    outputs = dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines() if line)
    return proc, outputs, calls


@pytest.mark.parametrize(("event", "base_ref"), [("pull_request", "main"), ("push", ""), ("merge_group", "")])
def test_anything_but_a_pr_into_release_yields_nothing_and_asks_nothing(tmp_path, event, base_ref) -> None:
    proc, outputs, calls = _run(tmp_path, event=event, base_ref=base_ref)
    assert proc.returncode == 0, proc.stderr
    assert outputs == {"base-sha": "", "new-commits": ""}, "callers must keep today's base"
    assert calls == [], "the compare API is only consulted for a PR into release"


@pytest.mark.parametrize("ahead", [0, 3])
def test_a_pr_into_release_yields_the_merge_base_with_main_and_the_new_count(tmp_path, ahead) -> None:
    response = {"merge_base_commit": {"sha": MERGE_BASE}, "ahead_by": ahead, "behind_by": 7}
    proc, outputs, calls = _run(tmp_path, event="pull_request", base_ref="release", response=response)
    assert proc.returncode == 0, proc.stderr
    assert outputs == {"base-sha": MERGE_BASE, "new-commits": str(ahead)}
    assert len(calls) == 1 and calls[0].startswith(f"api repos/owner/repo/compare/main...{'f' * 40} ")


def test_a_failed_compare_fails_closed(tmp_path) -> None:
    proc, outputs, _ = _run(tmp_path, event="pull_request", base_ref="release", fail=True)
    assert proc.returncode != 0
    assert outputs == {}, "a failed compare must never read as 'nothing new to judge'"


@pytest.mark.parametrize(
    "response",
    [{}, {"merge_base_commit": None, "ahead_by": 0}, {"merge_base_commit": {"sha": MERGE_BASE}, "ahead_by": None}],
)
def test_a_compare_without_a_base_or_count_fails_closed(tmp_path, response) -> None:
    proc, outputs, _ = _run(tmp_path, event="pull_request", base_ref="release", response=response)
    assert proc.returncode != 0
    assert outputs == {}


def _steps(workflow: str, job: str) -> list[dict]:
    doc = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    return doc["jobs"][job]["steps"]


def _uses_index(steps: list[dict]) -> int:
    hits = [i for i, s in enumerate(steps) if s.get("uses") == "./.github/actions/release-promotion-base"]
    assert len(hits) == 1, "the gate must call the one home of the rule exactly once"
    assert any(
        "actions/checkout" in s.get("uses", "") for s in steps[: hits[0]]
    ), "a local action needs a checkout first"
    return hits[0]


def test_the_trailer_gate_scans_from_the_release_base_and_counts_against_it() -> None:
    steps = _steps("no-commit-trailers.yml", "check-trailers")
    idx = _uses_index(steps)
    action_id = steps[idx]["id"]
    scan = next(s for s in steps[idx:] if s.get("name") == "Scan PR commits for banned trailers")
    assert f"steps.{action_id}.outputs.base-sha" in scan["env"]["RELEASE_BASE_SHA"]
    assert f"steps.{action_id}.outputs.new-commits" in scan["env"]["RELEASE_NEW_COMMITS"]
    run = scan["run"]
    assert 'BASE_SHA="${RELEASE_BASE_SHA}"' in run and 'EXPECTED_COMMITS="${RELEASE_NEW_COMMITS}"' in run
    # The override must precede the scan it narrows, or the count guard checks the old range.
    assert run.index('BASE_SHA="${RELEASE_BASE_SHA}"') < run.index('rev-list --count "${BASE_SHA}..${HEAD_SHA}"')


def test_the_ratchet_base_prefers_the_release_base() -> None:
    steps = _steps("ci.yml", "python-shard")
    idx = _uses_index(steps)
    action_id = steps[idx]["id"]
    ratchet = next(s for s in steps[idx:] if s.get("name") == "Ratchet base (#19283)")
    event_base = ratchet["env"]["EVENT_BASE"]
    assert event_base.replace("${{", "").strip().startswith(f"steps.{action_id}.outputs.base-sha ||")
