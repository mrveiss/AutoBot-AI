# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#16299: the installer's check reads stdin, says why, and never prints the value."""

from __future__ import annotations

import subprocess
import sys

import pytest
import yaml
from repo_tests._paths import repo_root

_SCRIPT = "autobot_shared/security/password_weakness.py"
_ROLE = "autobot-slm-backend/ansible/roles/slm_manager/tasks/main.yml"


def _run(password: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(repo_root() / _SCRIPT)], input=password, capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize("weak", ["admin", "autobot123", "password"])
def test_a_guessable_password_fails_and_is_not_printed(weak: str) -> None:
    done = _run(weak)
    assert done.returncode == 1 and done.stdout.strip() and weak not in done.stdout


def test_contrast_a_strong_password_passes() -> None:
    assert _run("kV9-long-unique-value").returncode == 0  # pragma: allowlist secret


def _task() -> dict:
    tasks = yaml.safe_load((repo_root() / _ROLE).read_text(encoding="utf-8"))
    return next(t for t in tasks if "Refuse a guessable admin password" in str(t.get("name")))


def test_the_role_checks_only_a_fresh_install_and_hides_the_value() -> None:
    task = _task()
    assert task["no_log"] is True and "not slm_secrets_stat.stat.exists" in task["when"]
    assert task["ansible.builtin.command"]["stdin"] == "{{ slm_admin_password }}"
    assert _SCRIPT in task["ansible.builtin.command"]["cmd"]


def test_the_check_runs_before_any_password_is_generated_or_stored() -> None:
    text = (repo_root() / _ROLE).read_text(encoding="utf-8")
    assert text.index("Refuse a guessable admin password") < text.index('"SLM | Generate security secrets"')
