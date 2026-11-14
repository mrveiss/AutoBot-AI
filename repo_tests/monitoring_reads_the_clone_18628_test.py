# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The monitoring role reads repo files from the clone, never the deploy dir (#18628).

A clean install failed at "Assert Prometheus alert rules were found": the
alert-rules ``find`` searched ``{{ autobot_repo_dir }}/autobot-monitoring``
(``/opt/autobot/autobot-monitoring``), and ``install.sh`` deploys only the
service trees there. The rules sat in the clone, ``code_source_dir``, which the
role's other source reads (``health_check_cron.yml``) already use. Long-lived
hosts with an older full-tree ``/opt/autobot`` hid it.

**What this does not cover.** It checks where the tasks read from, not that the
clone holds the files on a host; a clean install is the end-to-end proof.
"""

from __future__ import annotations

import yaml
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()
_SOURCE_KEYS = ("src", "paths")


def _module_args(task: dict) -> list[dict]:
    return [v for k, v in task.items() if isinstance(v, dict) and (k.startswith("ansible.") or k in ("copy", "find"))]


def test_no_monitoring_task_reads_a_source_from_the_deploy_dir() -> None:
    files = [_ROOT / p for p in tracked_paths(_ROOT, "autobot-slm-backend/ansible/roles/monitoring/tasks/*.yml")]
    assert files, "no monitoring task files found -- this guard would check nothing"
    offenders, sources = [], 0
    for path in files:
        for task in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            for args in _module_args(task):
                for key in _SOURCE_KEYS:
                    value = str(args.get(key, ""))
                    sources += "code_source_dir" in value
                    if "autobot_repo_dir" in value:
                        offenders.append(f"{path.name}: {task.get('name')}: {key}={value}")
    assert sources >= 2, f"expected the alert-rules find and the health-check copy to read the clone, saw {sources}"
    assert not offenders, f"repo sources read from the deploy dir, which a fresh install does not fill: {offenders}"
