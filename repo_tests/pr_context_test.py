# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ``pr-context`` action's script, driven against a fake ``gh`` (#20825).

Every fact a dispatched run reads about its pull request comes from this one lookup, so each refusal is pinned:
a stale head ends the run CANCELLED (never failed); a closed pull request, a base equal to the head, a base that
is not an ancestor of the head and a base that is not on the base branch all fail; ``admitted`` follows the label
read live; the body goes to a file and never to an output line.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
from repo_tests._paths import repo_root

SCRIPT = repo_root() / ".github" / "actions" / "pr-context" / "pr_context.sh"
HEAD, BASE, NEW = "a" * 40, "b" * 40, "c" * 40
pytestmark = pytest.mark.skipif(shutil.which("jq") is None or shutil.which("bash") is None, reason="the script needs bash and jq")

FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
cfg = json.load(open(os.environ["FAKE_GH_CONFIG"]))
args = sys.argv[1:]
path = next(a for a in args if a.startswith("repos/"))
if "-X" in args:
    open(cfg["log"], "a").write(path + "\\n")
    sys.exit(0)
if "/compare/" in path:
    key = path.split("/compare/", 1)[1]
    status = cfg["compare"].get(key)
    if status is None:
        sys.exit(1)
    print(status)
    sys.exit(0)
print(json.dumps(cfg["pull"]))
"""


def _pull(**over: Any) -> Dict[str, Any]:
    pull = {
        "state": "open", "draft": False, "title": "feat: x (#1)", "body": "Closes #1\nadmitted=false\n", "commits": 3,
        "head": {"sha": HEAD, "ref": "issue-1-x", "repo": {"full_name": "o/r"}},
        "base": {"ref": "main"}, "user": {"login": "someone", "type": "User"}, "labels": [{"name": "land-next"}],
    }
    pull.update(over)
    return pull


def run(tmp_path: Path, *, pull: Optional[Dict[str, Any]] = None, compare: Optional[Dict[str, str]] = None, **env: str):
    """Run the script; returns (returncode, outputs dict, raw outputs text, cancelled paths)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH, encoding="utf-8")
    gh.chmod(0o755)
    log, out, temp = tmp_path / "gh.log", tmp_path / "out.txt", tmp_path / "tmp"
    temp.mkdir(exist_ok=True)
    out.write_text("", encoding="utf-8")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({
        "pull": pull or _pull(), "log": str(log),
        "compare": compare if compare is not None else {f"{BASE}...{HEAD}": "ahead", f"{BASE}...main": "ahead"},
    }), encoding="utf-8")
    environ = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_GH_CONFIG": str(cfg), "REPO": "o/r", "RUN_ID": "9",
               "RUN_SHA": HEAD, "RUNNER_TEMP": str(temp), "GITHUB_OUTPUT": str(out), "CANCEL_WAIT_SECONDS": "0",
               "PR_NUMBER": "1", "HEAD_SHA": HEAD, "BASE_SHA": BASE, **env}
    proc = subprocess.run(["bash", str(SCRIPT)], env=environ, capture_output=True, text=True, check=False)
    raw = out.read_text(encoding="utf-8")
    outputs = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
    return proc.returncode, outputs, raw, (log.read_text(encoding="utf-8").split() if log.exists() else [])


def test_a_valid_dispatch_yields_the_live_facts(tmp_path: Path) -> None:
    rc, o, _, cancelled = run(tmp_path)
    assert rc == 0 and cancelled == []
    assert (o["is-pr"], o["number"], o["head-sha"], o["base-sha"]) == ("true", "1", HEAD, BASE)
    assert (o["base-ref"], o["head-ref"], o["same-repo"], o["author"], o["author-type"]) == ("main", "issue-1-x", "true", "someone", "User")
    assert (o["draft"], o["admitted"], o["commits"], o["labels"]) == ("false", "true", "3", '["land-next"]')


def test_no_pull_request_number_is_not_a_pull_request_run(tmp_path: Path) -> None:
    rc, o, _, _ = run(tmp_path, PR_NUMBER="", HEAD_SHA="", BASE_SHA="")
    assert rc == 0 and o["is-pr"] == "false" and o["number"] == "" and o["admitted"] == "" and o["labels"] == ""


def test_a_pull_request_without_land_next_is_not_admitted_and_a_draft_is_a_draft(tmp_path: Path) -> None:
    rc, o, _, _ = run(tmp_path, pull=_pull(labels=[{"name": "ci:full"}], draft=True))
    assert rc == 0 and o["admitted"] == "false" and o["draft"] == "true"


@pytest.mark.parametrize("env", [{"RUN_SHA": NEW}, {"HEAD_SHA": NEW}])
def test_a_stale_dispatch_cancels_the_run_and_never_reports_success(tmp_path: Path, env: Dict[str, str]) -> None:
    pull = _pull(head={"sha": HEAD, "ref": "x", "repo": {"full_name": "o/r"}})
    rc, o, _, cancelled = run(tmp_path, pull=pull, compare={f"{BASE}...{NEW}": "ahead", f"{BASE}...main": "ahead"}, **env)
    assert cancelled == ["repos/o/r/actions/runs/9/force-cancel"], "the stale run must be force-cancelled"
    assert rc != 0 and "is-pr" not in o, "if the cancel does not take effect the step still fails closed"


def test_the_live_head_moving_after_the_dispatch_cancels_it(tmp_path: Path) -> None:
    moved = _pull(head={"sha": NEW, "ref": "x", "repo": {"full_name": "o/r"}})
    rc, o, _, cancelled = run(tmp_path, pull=moved)
    assert cancelled and rc != 0 and "is-pr" not in o


@pytest.mark.parametrize(
    ("label", "kwargs"),
    [
        ("closed", {"pull": _pull(state="closed")}),
        ("base equals head", {"BASE_SHA": HEAD}),
        ("base not an ancestor of the head", {"compare": {f"{BASE}...{HEAD}": "diverged", f"{BASE}...main": "ahead"}}),
        ("base behind the head's history", {"compare": {f"{BASE}...{HEAD}": "behind", f"{BASE}...main": "ahead"}}),
        ("base not on the base branch", {"compare": {f"{BASE}...{HEAD}": "ahead", f"{BASE}...main": "diverged"}}),
        ("compare unreadable", {"compare": {}}),
        ("short head pin", {"HEAD_SHA": "abc"}),
        ("non-numeric number", {"PR_NUMBER": "1; rm -rf /"}),
    ],
)
def test_each_refusal_fails_and_publishes_no_pull_request_facts(tmp_path: Path, label: str, kwargs: Dict[str, Any]) -> None:
    rc, o, _, cancelled = run(tmp_path, **kwargs)
    assert rc != 0, label
    assert "is-pr" not in o and "admitted" not in o, f"{label}: a refused run must publish nothing"
    assert cancelled == [] or label == "short head pin", label


def test_the_body_goes_to_a_file_and_never_to_an_output_line(tmp_path: Path) -> None:
    body = "Closes #1\nadmitted=false\ntitle=owned\n"
    rc, o, raw, _ = run(tmp_path, pull=_pull(body=body, title="a\nadmitted=false"))
    assert rc == 0 and o["admitted"] == "true", "an injected line in the body must not rewrite an output"
    assert "owned" not in raw and "Closes #1" not in raw, "the body must never reach an output"
    assert Path(o["body-file"]).read_text(encoding="utf-8").strip().splitlines()[1] == "admitted=false"
    assert "\n" not in o["title"] and o["title"] == "aadmitted=false", "a title is one line"
    assert json.loads(Path(o["pull-file"]).read_text(encoding="utf-8"))["state"] == "open"


def test_control_the_fake_gh_is_not_passing_everything(tmp_path: Path) -> None:
    rc, _, _, _ = run(tmp_path, compare={f"{BASE}...{HEAD}": "ahead"})
    assert rc != 0, "with the branch comparison missing the lookup must fail, so the fake can fail"


def _fork_pull() -> Dict[str, Any]:
    pull = _pull()
    pull["head"] = {"sha": HEAD, "ref": "patch-1", "repo": {"full_name": "someone/r"}}
    return pull


def test_a_fork_head_runs_only_from_the_coordinators_mirror_ref(tmp_path: Path) -> None:
    rc, out, _, _ = run(tmp_path, pull=_fork_pull(), RUN_REF="refs/heads/ci/pr-1")
    assert rc == 0 and out["same-repo"] == "false" and out["is-pr"] == "true"


@pytest.mark.parametrize("ref", ["", "refs/heads/patch-1", "refs/heads/ci/pr-2", "refs/heads/ci/pr-1x", "refs/pull/1/merge"])
def test_a_fork_head_on_any_other_ref_is_refused(tmp_path: Path, ref: str) -> None:
    """Known-bad controls: unset, the fork's own branch name, another PR's mirror, a near-miss, a merge ref."""
    rc, out, _, _ = run(tmp_path, pull=_fork_pull(), RUN_REF=ref)
    assert rc == 1 and "is-pr" not in out


def test_a_same_repository_head_needs_no_mirror_ref(tmp_path: Path) -> None:
    rc, out, _, _ = run(tmp_path, RUN_REF="refs/heads/issue-1-x")
    assert rc == 0 and out["same-repo"] == "true"
