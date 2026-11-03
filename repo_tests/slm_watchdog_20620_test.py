# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20620: the SLM must always be running. The watchdog script runs here, with stub commands."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import jinja2
import pytest
import yaml
from repo_tests._paths import repo_root

_ROOT = repo_root()
_ROLE = _ROOT / "autobot-slm-backend" / "ansible" / "roles" / "slm_manager"
_VARS = {
    "ansible_managed": "test",
    "slm_backend_service": "autobot-slm-backend",
    "slm_backend_host": "127.0.0.1",
    "slm_backend_port": 8000,
    "slm_watchdog_max_health_failures": 3,
    "slm_watchdog_health_timeout": 1,
    "slm_self_update_unit_prefix": "autobot-selfupdate",
    "slm_watchdog_max_update_ticks": 2,
}


def _run(tmp_path: Path, state: str, healthy: bool, updating: bool = False, pid: int = 100) -> list[str]:
    """One tick; returns the systemctl actions it took (is-active itself is not an action)."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is needed to run the watchdog")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "actions"
    log.write_text("", encoding="utf-8")
    (bin_dir / "systemctl").write_text(
        f'#!/bin/sh\nif [ "$1" = is-active ]; then echo {state}; exit 0; fi\n'
        f'if [ "$1" = show ]; then echo {pid}; exit 0; fi\n'
        f'if [ "$1" = list-units ]; then {"echo autobot-selfupdate-1.service" if updating else ":"}; exit 0; fi\n'
        f'echo "$*" >> {log}\n',
        encoding="utf-8",
    )
    (bin_dir / "curl").write_text(f"#!/bin/sh\nexit {0 if healthy else 22}\n", encoding="utf-8")
    (bin_dir / "logger").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for tool in ("systemctl", "curl", "logger"):
        (bin_dir / tool).chmod(0o755)
    source = (_ROLE / "templates" / "autobot-slm-watchdog.sh.j2").read_text(encoding="utf-8")
    script = tmp_path / "watchdog.sh"
    script.write_text(jinja2.Template(source).render(**_VARS), encoding="utf-8")
    env = {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin", "SLM_WATCHDOG_STATE": str(tmp_path / "count")}
    done = subprocess.run([bash, str(script)], env=env, capture_output=True, text=True, timeout=20)
    assert done.returncode == 0, done.stderr
    return log.read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("state", ["failed", "inactive"])
def test_a_down_slm_has_its_failure_cleared_and_is_started(tmp_path, state) -> None:
    assert _run(tmp_path, state, healthy=False) == [
        "reset-failed autobot-slm-backend",
        "start --no-block autobot-slm-backend",
    ]


def test_a_healthy_slm_is_left_alone(tmp_path) -> None:
    assert _run(tmp_path, "active", healthy=True) == []


@pytest.mark.parametrize("state", ["activating", "deactivating"])
def test_a_slm_systemd_is_working_on_is_left_alone(tmp_path, state) -> None:
    assert _run(tmp_path, state, healthy=False) == []


def test_a_hung_slm_is_restarted_only_after_the_limit(tmp_path) -> None:
    assert _run(tmp_path, "active", healthy=False) == []
    assert _run(tmp_path, "active", healthy=False) == []
    assert _run(tmp_path, "active", healthy=False) == ["restart --no-block autobot-slm-backend"]


def test_a_replacement_process_gets_its_full_allowance(tmp_path) -> None:
    _run(tmp_path, "active", healthy=False, pid=100)
    _run(tmp_path, "active", healthy=False, pid=100)
    assert _run(tmp_path, "active", healthy=False, pid=200) == []
    assert _run(tmp_path, "active", healthy=False, pid=200) == []
    assert _run(tmp_path, "active", healthy=False, pid=200) == ["restart --no-block autobot-slm-backend"]


def test_recovering_resets_the_count(tmp_path) -> None:
    _run(tmp_path, "active", healthy=False)
    _run(tmp_path, "active", healthy=False)
    _run(tmp_path, "active", healthy=True)
    assert _run(tmp_path, "active", healthy=False) == []


def test_the_watchdog_is_installed_where_the_update_path_also_reaches_it() -> None:
    """update-all-nodes.yml runs service_units.yml and never main.yml (#14624)."""
    update = (_ROOT / "autobot-slm-backend" / "ansible" / "playbooks" / "update-all-nodes.yml").read_text(
        encoding="utf-8"
    )
    assert "tasks_from: service_units.yml" in update
    tasks = yaml.safe_load((_ROLE / "tasks" / "service_units.yml").read_text(encoding="utf-8"))
    timer = [t for t in tasks if t.get("ansible.builtin.systemd", {}).get("name") == "autobot-slm-watchdog.timer"]
    assert timer and timer[0]["ansible.builtin.systemd"]["enabled"] is True
    assert timer[0]["ansible.builtin.systemd"]["state"] == "started"


def test_systemds_start_limit_stays_so_a_broken_unit_still_shows_failed() -> None:
    """#4090: the watchdog retries; it must not hide the failure."""
    unit = (_ROLE / "templates" / "autobot-slm-backend.service.j2").read_text(encoding="utf-8")
    assert "StartLimitBurst=5" in unit and "Restart=always" in unit


def test_decommissioning_stops_the_watchdog_before_the_services() -> None:
    playbook = (_ROOT / "autobot-slm-backend" / "ansible" / "playbooks" / "decommission-node.yml").read_text(
        encoding="utf-8"
    )
    assert playbook.index("autobot-slm-watchdog.timer") < playbook.index("Stop and disable all services")


def test_the_bootstrap_unit_restarts_always_too() -> None:
    unit = _ROOT / "autobot-infrastructure" / "autobot-slm-backend" / "templates" / "autobot-slm-backend.service"
    assert "Restart=always" in unit.read_text(encoding="utf-8")


def test_a_running_update_holds_the_watchdog_off(tmp_path) -> None:
    assert _run(tmp_path, "failed", healthy=False, updating=True) == []


def test_a_stuck_update_holds_it_off_only_up_to_the_limit(tmp_path) -> None:
    assert _run(tmp_path, "failed", healthy=False, updating=True) == []
    assert _run(tmp_path, "failed", healthy=False, updating=True) == []
    assert _run(tmp_path, "failed", healthy=False, updating=True) == [
        "reset-failed autobot-slm-backend",
        "start --no-block autobot-slm-backend",
    ]


def test_health_failures_during_an_update_dont_count(tmp_path) -> None:
    _run(tmp_path, "active", healthy=False)
    _run(tmp_path, "active", healthy=False, updating=True)
    assert _run(tmp_path, "active", healthy=False) == []


def test_the_update_prefix_matches_the_code_that_starts_the_update() -> None:
    executor = (_ROOT / "autobot-slm-backend" / "services" / "playbook_executor.py").read_text(encoding="utf-8")
    assert '"SLM_SELF_UPDATE_UNIT_PREFIX", "autobot-selfupdate"' in executor
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert defaults["slm_self_update_unit_prefix"] == "autobot-selfupdate"


def test_bootstrap_installs_the_watchdog_with_nothing_left_unrendered(tmp_path) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is needed")
    helper = _ROOT / "autobot-infrastructure" / "autobot-slm-backend" / "scripts" / "install-slm-watchdog.sh"
    for name in ("autobot-slm-watchdog.sh", "autobot-slm-watchdog.service", "autobot-slm-watchdog.timer"):
        command = f'PROJECT_ROOT="{_ROOT}"; source "{helper}"; render_slm_watchdog_file {name}'
        done = subprocess.run([bash, "-c", command], capture_output=True, text=True, timeout=20)
        assert done.returncode == 0, done.stderr
        assert done.stdout and "{{" not in done.stdout, name
    bootstrap = helper.with_name("bootstrap-slm.sh").read_text(encoding="utf-8")
    assert "install_slm_watchdog" in bootstrap
