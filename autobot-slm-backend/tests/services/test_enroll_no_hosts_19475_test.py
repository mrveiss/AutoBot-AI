# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A run that matched no hosts is a failure, and never deletes the SSH password (#19475)."""

from __future__ import annotations

import asyncio
import configparser
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_HOST = "192.0.2.10"

_NO_HOSTS_OUTPUT = f"""[WARNING]: Unable to parse {_HOST}, as an inventory source
[WARNING]: No inventory was parsed, only implicit localhost is available
PLAY [Enroll Node - Deploy SLM Agent] ****
skipping: no hosts matched
PLAY RECAP ****
"""
_PATTERN_OUTPUT = "[WARNING]: Could not match supplied host pattern, ignoring: x\nPLAY RECAP ****\n"
_GOOD_OUTPUT = f"PLAY RECAP ****\n{_HOST}   : ok=9  changed=3  unreachable=0  failed=0  skipped=1\n"
_FAILED_OUTPUT = f"PLAY RECAP ****\n{_HOST}   : ok=2  changed=0  unreachable=0  failed=1  skipped=0\n"
_UNREACHABLE_OUTPUT = f"PLAY RECAP ****\n{_HOST}   : ok=0  changed=0  unreachable=1  failed=0  skipped=0\n"


@pytest.fixture()
def deployment():
    """conftest stubs `services.deployment`; load the real file and restore sys.modules after."""
    before = dict(sys.modules)
    spec = importlib.util.spec_from_file_location("_real_deployment_19475", _BACKEND / "services" / "deployment.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        for key in set(sys.modules) - set(before):
            del sys.modules[key]
        sys.modules.update(before)


def _inventory_section() -> configparser.SectionProxy:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(_BACKEND / "ansible" / "ansible.cfg", encoding="utf-8")
    return parser["inventory"]


def test_ansible_cfg_enables_host_list_and_fails_on_unparsed_inventory() -> None:
    """`-i "<ip>,"` needs host_list; without it every single-host run silently matches nothing."""
    section = _inventory_section()
    plugins = [p.strip() for p in section["enable_plugins"].split(",")]
    assert "host_list" in plugins
    assert {"yaml", "ini", "auto"} <= set(plugins)
    assert section.getboolean("unparsed_is_failed") is True


def _runner(deployment, monkeypatch, tmp_path, output: str, returncode: int = 0):
    class _Proc:
        def __init__(self) -> None:
            self.returncode = returncode

        async def communicate(self):
            return output.encode("utf-8"), None

    async def fake_exec(*_argv, **_kw):
        return _Proc()

    svc = deployment.DeploymentService()
    svc.ansible_dir = tmp_path
    monkeypatch.setattr(deployment.asyncio, "create_subprocess_exec", fake_exec)
    return svc


@pytest.mark.parametrize(
    "output", [_NO_HOSTS_OUTPUT, _PATTERN_OUTPUT, _FAILED_OUTPUT, _UNREACHABLE_OUTPUT], ids=lambda o: o[:30]
)
def test_a_run_that_did_not_succeed_on_the_target_fails_though_it_exits_zero(
    deployment, monkeypatch, tmp_path, output
) -> None:
    svc = _runner(deployment, monkeypatch, tmp_path, output)
    with pytest.raises(RuntimeError):
        asyncio.run(svc._run_ansible_command(["ansible-playbook"], "Enrollment playbook failed", _HOST))


def test_a_recap_listing_the_target_host_succeeds(deployment, monkeypatch, tmp_path) -> None:
    svc = _runner(deployment, monkeypatch, tmp_path, _GOOD_OUTPUT)
    assert asyncio.run(svc._run_ansible_command(["ansible-playbook"], "x", _HOST)) == _GOOD_OUTPUT


def test_a_recap_for_a_different_host_does_not_prove_the_target_ran(deployment, monkeypatch, tmp_path) -> None:
    svc = _runner(deployment, monkeypatch, tmp_path, _GOOD_OUTPUT.replace(_HOST, "192.0.2.99"))
    with pytest.raises(RuntimeError):
        asyncio.run(svc._run_ansible_command(["ansible-playbook"], "x", _HOST))


def _enroll(deployment, monkeypatch, tmp_path, output: str):
    node = SimpleNamespace(
        node_id="n1",
        ip_address=_HOST,
        status=deployment.NodeStatus.PENDING.value,
        ssh_user="pi",
        ssh_port=22,
        auth_method="password",
        extra_data={"ssh_password": "stored-secret"},  # pragma: allowlist secret
    )
    db = MagicMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: node))
    svc = _runner(deployment, monkeypatch, tmp_path, output)
    (tmp_path / "playbooks").mkdir()
    (tmp_path / deployment._ENROLLMENT_PLAYBOOK).write_text("---\n", encoding="utf-8")
    monkeypatch.setattr(svc, "_get_slm_public_key", AsyncMock(return_value="ssh-rsa AAAA k"))
    monkeypatch.setattr(svc, "_find_ansible_playbook", lambda: "ansible-playbook")
    monkeypatch.setattr(svc, "_get_effective_password", lambda _n, _p: None)
    ok, _msg = asyncio.run(svc.enroll_node(db, "n1"))
    return ok, node


def test_failed_enrollment_keeps_the_password_and_original_identity(deployment, monkeypatch, tmp_path) -> None:
    ok, node = _enroll(deployment, monkeypatch, tmp_path, _NO_HOSTS_OUTPUT)
    assert ok is False
    assert node.extra_data == {"ssh_password": "stored-secret"}  # pragma: allowlist secret
    assert node.ssh_user == "pi"
    assert node.auth_method == "password"
    assert node.status == deployment.NodeStatus.ERROR.value


def test_proven_enrollment_keeps_the_password_and_switches_to_key(deployment, monkeypatch, tmp_path) -> None:
    ok, node = _enroll(deployment, monkeypatch, tmp_path, _GOOD_OUTPUT)
    assert ok is True
    assert node.extra_data == {"ssh_password": "stored-secret"}  # pragma: allowlist secret
    assert node.auth_method == "key"
