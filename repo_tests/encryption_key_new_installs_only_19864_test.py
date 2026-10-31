# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""New installs generate AUTOBOT_ENCRYPTION_KEY once; updates keep it and never create one (#19864)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

_ANS = "autobot-slm-backend/ansible"
_LINE = re.compile(r"^AUTOBOT_ENCRYPTION_KEY=(.+)$", re.M)


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


def _run_generator(directory: Path) -> str:
    script = directory / "generate-secrets.sh"
    if not script.exists():
        shutil.copy(repo_root() / "docker/generate-secrets.sh", script)
    # A fake docker answering "no volumes": the script refuses a new DB password unless it can check.
    bin_dir = directory / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "docker"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "AUTOBOT_DOCKER_MGMT_PREFIX": "10.77.3"}
    subprocess.run(["bash", str(script)], check=True, capture_output=True, text=True, env=env)
    return (directory / ".env.secrets").read_text(encoding="utf-8")


def test_a_new_docker_install_gets_a_key_and_a_rerun_keeps_it(tmp_path: Path) -> None:
    first = _LINE.findall(_run_generator(tmp_path))
    assert len(first) == 1 and len(first[0]) == 64
    assert _LINE.findall(_run_generator(tmp_path)) == first


def test_an_existing_docker_install_is_not_given_a_key(tmp_path: Path) -> None:
    (tmp_path / ".env.secrets").write_text("SECRET_KEY=kept\n", encoding="utf-8")
    assert not _LINE.search(_run_generator(tmp_path))


def test_an_empty_file_from_a_refused_run_is_still_a_new_install(tmp_path: Path) -> None:
    (tmp_path / ".env.secrets").touch()
    assert len(_LINE.findall(_run_generator(tmp_path))) == 1


def test_the_slm_role_generates_only_when_the_secrets_file_is_absent() -> None:
    tasks = yaml.safe_load(_read(f"{_ANS}/roles/slm_manager/tasks/main.yml"))
    generating = [
        t for t in tasks if "autobot_encryption_key" in (t.get("ansible.builtin.set_fact") or t.get("set_fact") or {})
    ]
    assert len(generating) == 1
    assert generating[0]["when"] == "not slm_secrets_stat.stat.exists"
    assert "AUTOBOT_ENCRYPTION_KEY" not in _read(f"{_ANS}/roles/slm_manager/tasks/secrets_root_key.yml")
    assert "AUTOBOT_ENCRYPTION_KEY={{ autobot_encryption_key }}" in _read(
        f"{_ANS}/roles/slm_manager/templates/slm-secrets.env.j2"
    )


@pytest.mark.parametrize(
    "site",
    [
        f"{_ANS}/roles/backend/tasks/main.yml",
        f"{_ANS}/roles/backend/tasks/env_only.yml",
        f"{_ANS}/playbooks/deploy-backend-env.yml",
        f"{_ANS}/roles/backend_services/tasks/main.yml",
    ],
)
def test_every_render_of_the_backend_env_reads_the_key(site: str) -> None:
    text = _read(site)
    assert "backend.env.j2" in text
    assert "read_encryption_key.yml" in text


def test_every_backend_env_render_is_one_of_those_sites() -> None:
    found = subprocess.run(
        ["git", "grep", "-lE", "src: .*backend\\.env\\.j2", "--", _ANS],
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert sorted(found) == sorted(
        [
            f"{_ANS}/roles/backend/tasks/main.yml",
            f"{_ANS}/roles/backend/tasks/env_only.yml",
            f"{_ANS}/playbooks/deploy-backend-env.yml",
            f"{_ANS}/roles/backend_services/tasks/main.yml",
        ]
    )


def test_install_sh_generates_only_without_a_secrets_file() -> None:
    text = _read("install.sh")
    line = next(ln for ln in text.splitlines() if ln.strip().startswith("autobot_encryption_key=$("))
    assert line.index('if [[ -f "${SECRETS_FILE}" ]]') < line.index("grep -oP") < line.index("openssl rand -hex 32")
    assert "AUTOBOT_ENCRYPTION_KEY=${autobot_encryption_key}" in text
