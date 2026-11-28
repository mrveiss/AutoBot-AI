# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every ansible caller that targets `-i "<host>,"` treats a no-hosts run as a failure (#19475)."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_HOST = "192.0.2.10"
_NO_HOSTS = "[WARNING]: No inventory was parsed, only implicit localhost is available\nskipping: no hosts matched\nPLAY RECAP ****\n"
_GOOD = f"PLAY RECAP ****\n{_HOST}   : ok=3  changed=1  unreachable=0  failed=0  skipped=0\n"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_real_{name}_19475", _BACKEND / "services" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def modules():
    """conftest stubs services; load the real files and restore sys.modules after."""
    before = dict(sys.modules)
    try:
        yield {name: _load(name) for name in ("blue_green", "replication")}
    finally:
        for key in set(sys.modules) - set(before):
            del sys.modules[key]
        sys.modules.update(before)


def _fake_exec(monkeypatch, module, output: str) -> None:
    class _Proc:
        returncode = 0

        async def communicate(self):
            return output.encode("utf-8"), None

    async def fake_exec(*_argv, **_kw):
        return _Proc()

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_exec)


def _calls(modules, tmp_path):
    bg = modules["blue_green"].BlueGreenService()
    bg.ansible_dir = tmp_path
    rep = modules["replication"].ReplicationService()
    rep.ansible_dir = tmp_path
    node = SimpleNamespace(ip_address=_HOST, ssh_user="autobot", ssh_port=22, node_id="n1")
    return {
        "blue_green_deploy": (bg, modules["blue_green"], lambda: bg._deploy_roles_to_node(node, ["redis"])),
        "blue_green_purge": (
            bg,
            modules["blue_green"],
            lambda: bg._execute_purge_playbook(_HOST, "autobot", 22, ["redis"]),
        ),
        "replication": (
            rep,
            modules["replication"],
            lambda: rep._run_ansible_replication(_HOST, "autobot", 22, "192.0.2.11", "pw"),
        ),
        "promotion": (rep, modules["replication"], lambda: rep._run_ansible_promotion(_HOST, "autobot", 22)),
    }


@pytest.mark.parametrize("site", ["blue_green_deploy", "blue_green_purge", "replication", "promotion"])
def test_a_no_hosts_run_is_reported_as_failure_by_each_caller(modules, monkeypatch, tmp_path, site) -> None:
    (tmp_path / "deploy.yml").write_text("---\n", encoding="utf-8")
    (tmp_path / "purge.yml").write_text("---\n", encoding="utf-8")
    _svc, module, call = _calls(modules, tmp_path)[site]
    _fake_exec(monkeypatch, module, _NO_HOSTS)
    assert asyncio.run(call()) is False


@pytest.mark.parametrize("site", ["blue_green_deploy", "blue_green_purge", "replication", "promotion"])
def test_a_run_whose_recap_lists_the_target_succeeds_in_each_caller(modules, monkeypatch, tmp_path, site) -> None:
    (tmp_path / "deploy.yml").write_text("---\n", encoding="utf-8")
    (tmp_path / "purge.yml").write_text("---\n", encoding="utf-8")
    _svc, module, call = _calls(modules, tmp_path)[site]
    _fake_exec(monkeypatch, module, _GOOD)
    assert asyncio.run(call()) is True
