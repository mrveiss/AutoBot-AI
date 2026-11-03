# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20743: a sync without restarts deploys, and restarts nothing.

`--tags !restart` was a tag named "!restart", so the run executed only the `always` tasks: 4 of
the updater's 88. And Ansible ignores tags on handlers, so even a correct `--skip-tags restart`
would still restart services a config change notified.
"""

import importlib.util
import json
import shutil
import subprocess  # nosec B404 -- runs ansible-playbook on a generated local playbook
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[1]
_ANSIBLE = _ROOT / "ansible"
_UPDATER_ROLES = ("backend", "ai-stack", "npu-worker", "frontend", "browser", "tts-worker", "postgresql", "redis")
_UPDATER_ROLES += ("monitoring",)


def _load(name: str, rel: str, stubs: tuple = ()):
    """Load a module by path, past the conftest's session stubs of `services` (#11248)."""
    saved = {n: sys.modules.get(n) for n in stubs}
    try:
        for n in stubs:
            sys.modules[n] = MagicMock()
        spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for n, orig in saved.items():
            sys.modules.pop(n, None) if orig is None else sys.modules.__setitem__(n, orig)


_sr = _load("_sync_restart_20743", "services/sync_restart.py")


def test_a_no_restart_sync_skips_restarts_and_never_negates_a_tag() -> None:
    assert _sr.no_restart_args(True) == {}
    args = _sr.no_restart_args(False)
    assert args == {"skip_tags": ["restart"], "extra_vars": {"autobot_restart_services": "false"}}
    assert "tags" not in args


def test_the_command_skips_with_skip_tags_and_refuses_a_negated_tag() -> None:
    # The real `services` package; only the modules that reach the network or the DB are stubbed.
    stubs = ("services.ansible_secrets", "services.inventory_builder", "services.provision_progress")
    pe = _load("_pe_20743", "services/playbook_executor.py", stubs)
    pe.reject_negated_tags = _sr.reject_negated_tags  # the conftest's session stubs can shadow it
    executor = pe.PlaybookExecutor.__new__(pe.PlaybookExecutor)
    executor.inventory_path = Path("inv.yml")
    executor._find_ansible_playbook = lambda: "ansible-playbook"
    cmd = executor._build_ansible_command(Path("p.yml"), ["n1"], None, None, False, skip_tags=["restart"])
    assert cmd[cmd.index("--skip-tags") + 1] == "restart" and "--tags" not in cmd
    with pytest.raises(ValueError, match="cannot negate"):
        executor._build_ansible_command(Path("p.yml"), ["n1"], ["!restart"], None, False)


def test_both_code_sync_paths_use_the_one_helper() -> None:
    source = (_ROOT / "api" / "code_sync.py").read_text(encoding="utf-8")
    assert "!restart" not in source
    assert source.count("no_restart_args(") == 2


def _handlers(role: str) -> list:
    return yaml.safe_load((_ANSIBLE / "roles" / role / "handlers" / "main.yml").read_text(encoding="utf-8")) or []


def test_every_restart_handler_the_updater_can_notify_checks_the_variable() -> None:
    restarting = [(role, h["name"]) for role in _UPDATER_ROLES for h in _handlers(role) if "restarted" in json.dumps(h)]
    assert len(restarting) >= 18, "control: the finder sees the restart handlers"
    unguarded = [
        (role, name)
        for role, name in restarting
        if _sr.RESTART_VAR not in str(next(h for h in _handlers(role) if h["name"] == name).get("when", ""))
    ]
    assert not unguarded, f"these would still restart on a no-restart sync: {unguarded}"


def _updater_tasks() -> list:
    """(name, tags) for every task in update-all-nodes.yml, with block tags inherited."""
    out: list = []

    def walk(node, inherited=()):
        if isinstance(node, list):
            for item in node:
                walk(item, inherited)
        elif isinstance(node, dict):
            tags = node.get("tags") or []
            tags = tuple(inherited) + tuple([tags] if isinstance(tags, str) else tags)
            if "name" in node and "block" not in node and "hosts" not in node:
                out.append((node["name"], tags))
            for key in ("tasks", "block", "rescue", "always", "pre_tasks", "post_tasks"):
                walk(node.get(key), tags)

    walk(yaml.safe_load((_ANSIBLE / "playbooks" / "update-all-nodes.yml").read_text(encoding="utf-8")))
    return out


def test_a_no_restart_sync_still_runs_the_deploy_tasks() -> None:
    tasks = _updater_tasks()
    runs = [n for n, t in tasks if "restart" not in t]
    always_only = [n for n, t in tasks if "always" in t]
    assert len(runs) > len(always_only) * 5, "skipping restarts leaves the deploy, not just the always tasks"


_PROBE = """
- hosts: localhost
  gather_facts: false
  tasks:
    - name: deploy config
      ansible.builtin.debug: {msg: DEPLOYED}
      changed_when: true
      notify: restart svc
    - name: restart task
      ansible.builtin.debug: {msg: RESTART-TASK}
      tags: [restart]
  handlers:
    - name: restart svc
      ansible.builtin.debug: {msg: HANDLER-RESTART}
      when: %s
""" % next(
    h["when"] for h in _handlers("ai-stack") if h["name"] == "restart ai-stack"
)  # the guard exactly as the roles carry it


@pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible not installed")
@pytest.mark.parametrize("restart", [False, True], ids=["no-restart", "restart"])
def test_real_ansible_deploys_and_restarts_only_when_asked(tmp_path: Path, restart: bool) -> None:
    """The real semantics, with the exact arguments a sync passes: the handler guard is the one in the roles."""
    (tmp_path / "p.yml").write_text(_PROBE, encoding="utf-8")
    args = _sr.no_restart_args(restart)
    cmd = ["ansible-playbook", "-i", "localhost,", "-c", "local", str(tmp_path / "p.yml")]
    if args:
        cmd += ["--skip-tags", ",".join(args["skip_tags"])]
        cmd += ["-e", json.dumps(args["extra_vars"])]
    env = {"ANSIBLE_LOG_PATH": str(tmp_path / "a.log"), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    out = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120, check=False).stdout  # nosec B603
    assert "DEPLOYED" in out
    assert ("RESTART-TASK" in out) is restart and ("HANDLER-RESTART" in out) is restart
