# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""install.sh marks the local node synced AFTER it registers it (#18663).

The mark-synced endpoint 404s on a node with no row, and the playbook tolerates that 404 for the
fleet-wide run. During ``ansible_deployment`` the local node is not registered yet, so a
mark-synced step placed there passes silently and stamps nothing. The step belongs after
``register_local_node``, and must reuse the playbook's tagged tasks.
"""

from __future__ import annotations

import os
import re
import subprocess

import yaml
from repo_tests._paths import repo_root

_SCRIPT = "scripts/deployment/mark_local_node_synced.sh"
_REGISTER = "register_local_node() {"


def _register_body(source: str) -> str:
    """install.sh's register_local_node function body."""
    return source[source.index(_REGISTER) :].split("\n}\n", 1)[0]


def _marks_after_registration(source: str) -> bool:
    """The mark-synced call sits inside register_local_node, after the node POST."""
    body = _register_body(source)
    return _SCRIPT in body and body.index(_SCRIPT) > body.index('"${api_url}/api/nodes"')


def _install() -> str:
    return (repo_root() / "install.sh").read_text(encoding="utf-8")


def test_mark_synced_runs_after_registration() -> None:
    assert _marks_after_registration(_install())


def test_control_call_before_registration_fails() -> None:
    source = _install()
    line = next(ln for ln in source.splitlines() if _SCRIPT in ln)
    moved = source.replace(line + "\n", "").replace(_REGISTER + "\n", _REGISTER + "\n" + line + "\n", 1)
    assert moved != source, "control did not change install.sh"
    assert not _marks_after_registration(moved)


def test_mark_synced_reuses_the_playbook_tasks() -> None:
    script = (repo_root() / _SCRIPT).read_text(encoding="utf-8")
    assert "playbooks/provision-fleet-roles.yml" in script and "--tags mark-synced" in script
    assert "/api/code-sync/" not in script, "a second hand-written call to the endpoint"


_ANSIBLE_DIR = "autobot-slm-backend/ansible"


def _script_value(script: str, flag: str) -> str:
    """The value the script passes for ``flag``, with a ``${NAME}`` resolved from its assignments."""
    raw = re.search(rf'{re.escape(flag)} "?([^"\s)]+)"?', script).group(1)
    name = re.fullmatch(r"\$\{(\w+)\}", raw)
    if not name:
        return raw
    return re.search(rf'\b{name.group(1)}="([^"]+)"', script).group(1)


def _inventory_hosts(group: dict) -> set[str]:
    hosts = set((group.get("hosts") or {}).keys())
    for child in (group.get("children") or {}).values():
        hosts |= _inventory_hosts(child or {})
    return hosts


def _limit_is_an_inventory_host(script: str) -> bool:
    inventory = repo_root() / _ANSIBLE_DIR / _script_value(script, "-i")
    data = yaml.safe_load(inventory.read_text(encoding="utf-8"))
    return _script_value(script, "--limit") in _inventory_hosts(data.get("all", data))


def _script() -> str:
    return (repo_root() / _SCRIPT).read_text(encoding="utf-8")


def test_limit_names_a_host_of_the_passed_inventory() -> None:
    assert _limit_is_an_inventory_host(_script())


def test_control_limit_by_node_id_matches_no_host() -> None:
    # The original defect: --limit carried the node id, a var of the install inventory, not a host.
    moved = (
        _script()
        .replace('--limit "${INVENTORY_HOST}"', '--limit "${node_id}"')
        .replace('code_source="${1', 'node_id="00-SLM-Manager"\ncode_source="${1')
    )
    assert moved != _script(), "control did not change the script"
    assert not _limit_is_an_inventory_host(moved)


def test_node_id_reaches_the_url_and_the_run_is_strict() -> None:
    script = _script()
    assert '-e "slm_node_id=${node_id}"' in script and "mark_synced_strict=true" in script
    playbook = (repo_root() / _ANSIBLE_DIR / "playbooks/provision-fleet-roles.yml").read_text(encoding="utf-8")
    assert "/code-sync/nodes/{{ slm_node_id | default(inventory_hostname) }}/mark-synced" in playbook
    assert "/code-sync/nodes/{{ inventory_hostname }}/mark-synced" not in playbook


def test_mark_synced_only_runs_once_the_code_source_is_assigned() -> None:
    body = _register_body(_install())
    arm = body[body.index('200) success "Code source assigned') :].split(";;", 1)[0]
    assert _SCRIPT in arm, "mark-synced must run only in the code-source 200 arm"


def _run_helper(tmp_path, stub_body: str) -> subprocess.CompletedProcess:
    """Run the real helper with a stub ``ansible-playbook`` first on PATH; it records its argv."""
    bin_dir, code_source = tmp_path / "bin", tmp_path / "src"
    (code_source / _ANSIBLE_DIR).mkdir(parents=True)
    bin_dir.mkdir()
    stub = bin_dir / "ansible-playbook"
    stub.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" > "{tmp_path}/argv"\n{stub_body}\n', encoding="utf-8")
    stub.chmod(0o755)
    (tmp_path / "vars.json").write_text("{}", encoding="utf-8")
    return subprocess.run(
        [
            "bash",
            str(repo_root() / _SCRIPT),
            str(code_source),
            "00-SLM-Manager",
            "https://127.0.0.1",
            str(tmp_path / "vars.json"),
            str(tmp_path / "log"),
        ],
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )


_OK_RUN = (
    'echo "TASK [Mark-synced | POST to x]"; echo "ok: [localhost]"; '
    'echo "localhost                  : ok=3    changed=0    failed=0"'
)


def test_helper_invokes_the_tagged_playbook_for_the_registered_node(tmp_path) -> None:
    result = _run_helper(tmp_path, _OK_RUN)
    argv = (tmp_path / "argv").read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert "playbooks/provision-fleet-roles.yml" in argv
    assert "--tags mark-synced" in argv
    assert "slm_node_id=00-SLM-Manager" in argv
    assert "slm_api_url=https://127.0.0.1" in argv
    assert "--limit localhost" in argv


def test_helper_fails_and_prints_a_vars_file_free_rerun_when_the_post_did_not_run(tmp_path) -> None:
    result = _run_helper(tmp_path, 'echo "localhost                  : ok=2    changed=0    failed=0"')
    assert result.returncode == 1
    assert "sudo ansible-playbook" in result.stderr
    assert "@" not in result.stderr.split("rerun:", 1)[1]
