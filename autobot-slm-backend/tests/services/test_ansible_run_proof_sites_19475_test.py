# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An exit-0 ansible run is not proof it ran: the shared check, its edge cases, and every site (#19475)."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_HOST = "192.0.2.10"
_NO_HOSTS = "[WARNING]: No inventory was parsed, only implicit localhost is available\nskipping: no hosts matched\nPLAY RECAP ****\n"
_GOOD = f"PLAY RECAP ****\n{_HOST}   : ok=3  changed=1  unreachable=0  failed=0  skipped=0\n"


def _recap(host: str, ok: int = 3, unreachable: int = 0, failed: int = 0) -> str:
    return f"PLAY RECAP ****\n{host}  : ok={ok}  changed=0  unreachable={unreachable}  failed={failed}  skipped=0\n"


@pytest.fixture()
def load():
    """Load real files from disk (conftest stubs `services`); restore sys.modules afterwards."""
    before = dict(sys.modules)

    def _load(rel: str):
        spec = importlib.util.spec_from_file_location("_real_19475_" + rel.replace("/", "_"), _BACKEND / rel)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    try:
        yield _load
    finally:
        for key in set(sys.modules) - set(before):
            del sys.modules[key]
        sys.modules.update(before)


@pytest.fixture()
def utils(load):
    return load("services/ansible_utils.py")


# --- the shared check ---------------------------------------------------------------------


def test_only_the_last_play_recap_counts(utils) -> None:
    """(a) An earlier recap listing the host must not vouch for a final recap that lacks it."""
    output = _recap(_HOST) + "\nsome later playbook\n" + _recap("192.0.2.99")
    assert utils.ansible_run_failure(output, _HOST, 0) is not None
    flipped = _recap(_HOST, failed=1) + "\nmore\n" + _recap(_HOST)
    assert utils.ansible_run_failure(flipped, _HOST, 0) is None


def test_the_target_must_have_run_at_least_one_task(utils) -> None:
    """(b) A recap line with ok=0 is not an enrollment that did anything."""
    assert utils.ansible_run_failure(_recap(_HOST, ok=0), _HOST, 0) is not None
    assert utils.ansible_run_failure(_recap(_HOST, ok=1), _HOST, 0) is None


def test_multi_host_check_fails_on_any_bad_recap_line_or_marker_but_needs_no_target(utils) -> None:
    both = _recap("a") + "b  : ok=1  changed=0  unreachable=0  failed=0  skipped=0\n"
    assert utils.ansible_run_failure(both, None, 0) is None
    assert utils.ansible_run_failure(both + "c : ok=0 changed=0 unreachable=1 failed=0 skipped=0\n", None, 0)
    assert utils.ansible_run_failure(both + "d : ok=2 changed=0 unreachable=0 failed=1 skipped=0\n", None, 0)
    assert utils.ansible_run_failure(_NO_HOSTS, None, 0)
    assert utils.ansible_run_failure("anything", None, 2) == "anything"


def test_ansible_config_env_names_the_repo_cfg(utils, tmp_path) -> None:
    assert utils.ansible_config_env(tmp_path) == {"ANSIBLE_CONFIG": str(tmp_path / "ansible.cfg")}
    assert utils.ansible_subprocess_env(tmp_path, X="1")["ANSIBLE_CONFIG"] == str(tmp_path / "ansible.cfg")


# --- (c) ANSIBLE_CONFIG in every runner environment ---------------------------------------


def test_deployment_environment_names_the_ansible_cfg(load, tmp_path) -> None:
    svc = load("services/deployment.py").DeploymentService()
    svc.ansible_dir = tmp_path
    assert svc._get_ansible_environment()["ANSIBLE_CONFIG"] == str(tmp_path / "ansible.cfg")


def test_playbook_executor_environment_names_the_ansible_cfg_and_forwards_it(load, tmp_path, monkeypatch) -> None:
    module = load("services/playbook_executor.py")
    svc = module.PlaybookExecutor.__new__(module.PlaybookExecutor)
    svc.ansible_dir = tmp_path
    monkeypatch.setattr(module.PlaybookExecutor, "_ensure_ansible_temp_dirs", staticmethod(lambda: None))
    assert svc._build_ansible_env()["ANSIBLE_CONFIG"] == str(tmp_path / "ansible.cfg")
    assert "ANSIBLE_CONFIG" in module.ANSIBLE_ENV_ALLOWLIST_EXACT


@pytest.mark.parametrize("site", ["blue_green_deploy", "blue_green_purge", "replication", "promotion"])
def test_blue_green_and_replication_runners_name_the_ansible_cfg(load, monkeypatch, tmp_path, site) -> None:
    bg = load("services/blue_green.py")
    rep = load("services/replication.py")
    seen: dict = {}

    class _Proc:
        returncode = 0

        async def communicate(self):
            return _recap(_HOST).encode(), None

    async def fake_exec(*_argv, **kw):
        seen["env"] = kw.get("env")
        return _Proc()

    (tmp_path / "deploy.yml").write_text("---\n", encoding="utf-8")
    (tmp_path / "purge.yml").write_text("---\n", encoding="utf-8")
    bsvc, rsvc = bg.BlueGreenService(), rep.ReplicationService()
    bsvc.ansible_dir = rsvc.ansible_dir = tmp_path
    node = SimpleNamespace(ip_address=_HOST, ssh_user="autobot", ssh_port=22, node_id="n1")
    calls = {
        "blue_green_deploy": (bg, lambda: bsvc._deploy_roles_to_node(node, ["redis"])),
        "blue_green_purge": (bg, lambda: bsvc._execute_purge_playbook(_HOST, "autobot", 22, ["redis"])),
        "replication": (rep, lambda: rsvc._run_ansible_replication(_HOST, "autobot", 22, "192.0.2.11", "pw")),
        "promotion": (rep, lambda: rsvc._run_ansible_promotion(_HOST, "autobot", 22)),
    }
    module, call = calls[site]
    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_exec)
    assert asyncio.run(call()) is True
    assert seen["env"]["ANSIBLE_CONFIG"] == str(tmp_path / "ansible.cfg")


# --- the three sites -----------------------------------------------------------------------


def test_playbook_executor_run_result_reports_a_no_hosts_run_as_failed(load) -> None:
    executor = load("services/playbook_executor.py").PlaybookExecutor
    bad = executor._run_result(_NO_HOSTS.splitlines(), 0, detached=False)
    assert bad["returncode"] != 0
    good = executor._run_result(_recap(_HOST).splitlines(), 0, detached=False)
    assert good["returncode"] == 0


def _infra_run(load, monkeypatch, tmp_path, output: str):
    infra = load("api/infrastructure.py")
    (tmp_path / "p.yml").write_text("---\n", encoding="utf-8")
    monkeypatch.setattr(infra, "_ansible_dir", lambda: tmp_path)
    monkeypatch.setitem(
        sys.modules,
        "api.setup_wizard",
        types.SimpleNamespace(_generate_dynamic_inventory=_async_value(tmp_path / "inv.ini")),
    )
    monkeypatch.setitem(
        sys.modules, "services.ansible_secrets", types.SimpleNamespace(fetch_deploy_secrets=_async_value({}))
    )

    class _Proc:
        returncode = 0

        async def wait(self):
            return 0

    async def fake_exec(*_a, **_k):
        return _Proc()

    async def fake_stream(_process, execution):
        execution.output.extend(output.splitlines())

    monkeypatch.setattr(infra.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(infra, "_stream_process_output", fake_stream)
    execution = infra.PlaybookExecution(
        execution_id="e1", playbook_id="p", status=infra.PlaybookStatus.PENDING, triggered_by="t"
    )
    infra._executions["e1"] = execution
    playbook = SimpleNamespace(playbook_file="p.yml", tags=[], variables={})
    asyncio.run(infra._run_playbook("e1", playbook, {}, None))
    return infra, execution


def _async_value(value):
    async def _f(*_a, **_k):
        return value

    return _f


def test_infrastructure_run_playbook_fails_a_no_hosts_run_that_exits_zero(load, monkeypatch, tmp_path) -> None:
    infra, execution = _infra_run(load, monkeypatch, tmp_path, _NO_HOSTS)
    assert execution.status == infra.PlaybookStatus.FAILED
    assert execution.error


def test_infrastructure_run_playbook_completes_a_run_whose_recap_is_clean(load, monkeypatch, tmp_path) -> None:
    infra, execution = _infra_run(load, monkeypatch, tmp_path, _recap(_HOST))
    assert execution.status == infra.PlaybookStatus.COMPLETED


def test_multi_host_mode_treats_an_empty_recap_as_failure(utils) -> None:
    """HIGH: rc=0, no marker and no PLAY RECAP at all proves nothing ran."""
    assert utils.ansible_run_failure("TASK [x] ok\nno recap at all", None, 0)
    assert utils.ansible_run_failure("PLAY RECAP ****\n", None, 0)


def test_multi_host_mode_requires_a_host_that_ran_a_task(utils) -> None:
    """MED: every recap host at ok=0 is not a play that did anything."""
    zeros = _recap("a", ok=0) + "b  : ok=0  changed=0  unreachable=0  failed=0  skipped=2\n"
    assert utils.ansible_run_failure(zeros, None, 0)
    assert utils.ansible_run_failure(zeros + "c : ok=1 changed=0 unreachable=0 failed=0 skipped=0\n", None, 0) is None


def test_a_per_play_skip_does_not_fail_a_run_whose_target_ran(utils) -> None:
    """#19762: a multi-play run prints this for every play whose group the limit leaves out."""
    output = "skipping: no hosts matched\n" + _recap(_HOST)
    assert utils.ansible_run_failure(output, None, 0) is None
    assert utils.ansible_run_failure(output, _HOST, 0) is None


def test_an_inventory_level_marker_in_an_early_play_still_fails_a_multi_play_run(utils) -> None:
    """The run as a whole targeting nothing is matched over the whole output, not just the last recap."""
    output = "[WARNING]: No inventory was parsed\n" + _recap(_HOST)
    assert utils.ansible_run_failure(output, None, 0)
    assert utils.ansible_run_failure(output, _HOST, 0)
