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


def _install() -> str:
    return (repo_root() / "install.sh").read_text(encoding="utf-8")


def test_the_one_liner_checks_before_it_writes_secrets_or_runs_ansible() -> None:
    text = _install()
    main = text[text.index("main() {") :]
    assert main.index("code_deployment") < main.index("ansible_deployment")
    deploy = text[text.index("code_deployment() {") : text.index("ansible_deployment() {")]
    assert "refuse_guessable_admin_password" in deploy


def test_the_installer_function_really_refuses_and_passes(tmp_path) -> None:
    """The function itself, run in bash against the real script."""
    text = _install()
    start = text.index("refuse_guessable_admin_password() {")
    body = text[start : text.index("generate_admin_password() {", start)]
    assert "|| fatal " in body  # error() only logs here and the install would carry on
    tree = tmp_path / "autobot_shared/security"
    tree.mkdir(parents=True)
    tree.joinpath("password_weakness.py").write_text(
        (repo_root() / _SCRIPT).read_text(encoding="utf-8"), encoding="utf-8"
    )

    def run(password: str, generated: str = "false", preserved: str = "false") -> subprocess.CompletedProcess:
        script = (
            'fatal() { echo "FATAL $*"; exit 1; }\n'
            f"CODE_SOURCE={tmp_path}\nADMIN_PASSWORD='{password}'\n"
            f"ADMIN_PASSWORD_GENERATED={generated}\nADMIN_PASSWORD_PRESERVED={preserved}\n"
            f"{body}\nrefuse_guessable_admin_password\necho PASSED\n"
        )
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)

    refused = run("autobot123")
    assert refused.returncode == 1 and "was refused" in refused.stdout and "autobot123" not in refused.stdout
    assert "PASSED" in run("kV9-long-unique-value").stdout  # pragma: allowlist secret
    assert "PASSED" in run("autobot123", preserved="true").stdout
    assert "PASSED" in run("autobot123", generated="true").stdout
