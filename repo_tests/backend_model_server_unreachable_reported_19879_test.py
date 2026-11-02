# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19879: a model server that cannot be asked what it holds is reported, not skipped in silence."""

from __future__ import annotations

import yaml
from repo_tests._paths import repo_root

_FILE = repo_root() / "autobot-slm-backend" / "ansible" / "roles" / "backend" / "tasks" / "resolve_models.yml"


def _task(prefix: str) -> dict:
    tasks = yaml.safe_load(_FILE.read_text(encoding="utf-8"))
    return next(t for t in tasks if str(t.get("name", "")).startswith(prefix))


def test_an_unreachable_server_is_reported_with_what_came_back() -> None:
    report = _task("Backend | Report a model server that could not be asked")
    assert report["when"] == "(_backend_model_tags.status | default(0)) != 200"
    msg = report["ansible.builtin.debug"]["msg"]
    assert "_backend_model_tags.status" in msg and "_backend_model_tags.msg" in msg and "embedding model" in msg


def test_the_report_never_fails_the_play_and_runs_when_the_decision_does_not() -> None:
    decide = _task("Backend | Decide the models")
    report = _task("Backend | Report a model server that could not be asked")
    assert (
        "ansible.builtin.fail" not in report and "failed_when" not in report
    )  # a model server installed later in the play must not stop a deploy
    # contrast: the decision runs on exactly the opposite condition
    assert decide["when"] == "(_backend_model_tags.status | default(0)) == 200"
