#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the Ansible repo-path reference guard (#13744).

The bug this guards against — a play installing from
``/opt/autobot/src/docker/npu-worker/requirements.txt``, which never existed —
survived because a wrong path in a play only fails on a host. A guard for it is
worth nothing unless it can actually fail, so these tests assert both directions
and the discovery step, which is where the first draft silently checked nothing.
"""

import pathlib
import subprocess
import sys

import pytest

_SCRIPT = pathlib.Path(__file__).parent / "check_ansible_file_references.py"
sys.path.insert(0, str(_SCRIPT.parent))

import check_ansible_file_references as guard  # noqa: E402


def _play(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    """Write a play at a realistic ansible/ location under *tmp_path*."""
    play_dir = tmp_path / "component" / "ansible" / "playbooks"
    play_dir.mkdir(parents=True)
    path = play_dir / "deploy.yml"
    path.write_text(body, encoding="utf-8")
    return path


# ----------------------------------------------------------------- discovery


def test_a_checkout_inside_an_excluded_directory_is_still_scanned(tmp_path):
    """The repo may live at .worktrees/<branch>/ — exclusions are relative.

    Matching ``_EXCLUDE_DIRS`` against the absolute path excluded the whole
    repository and made the guard report "0 references" while passing.
    """
    root = tmp_path / ".worktrees" / "issue-1"
    _play(root, "- hosts: all\n")

    assert guard._ansible_files(root), "the guard scanned nothing from inside a worktree"


def test_vendored_trees_are_still_skipped(tmp_path):
    _play(tmp_path / "node_modules" / "pkg", "- hosts: all\n")

    assert guard._ansible_files(tmp_path) == []


def test_only_ansible_paths_are_scanned(tmp_path):
    other = tmp_path / "compose"
    other.mkdir()
    (other / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    assert guard._ansible_files(tmp_path) == []


# ---------------------------------------------------------------- extraction


def test_a_deployed_src_reference_is_extracted():
    text = "    - pip:\n        requirements: /opt/autobot/src/autobot-npu-worker/requirements.txt\n"

    assert guard._referenced_repo_paths(text) == [(2, "requirements", "autobot-npu-worker/requirements.txt")]


@pytest.mark.parametrize(
    "line",
    [
        "        requirements: /etc/somewhere/else/requirements.txt",
        "        src: {{ project_root }}/requirements.txt",
        "        src: ${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/",
    ],
)
def test_paths_that_cannot_be_resolved_statically_are_skipped(line):
    """A guard that reports false positives gets switched off."""
    assert guard._referenced_repo_paths(line + "\n") == []


# ------------------------------------------------------------- end-to-end


def _run(cwd: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_missing_referenced_file_fails(tmp_path):
    _play(
        tmp_path,
        "- hosts: all\n  tasks:\n    - pip:\n        requirements: /opt/autobot/src/docker/npu-worker/requirements.txt\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "docker/npu-worker/requirements.txt" in result.stdout


def test_a_present_referenced_file_passes(tmp_path):
    (tmp_path / "autobot-npu-worker").mkdir()
    (tmp_path / "autobot-npu-worker" / "requirements.txt").write_text("numpy\n", encoding="utf-8")
    _play(
        tmp_path,
        "- hosts: all\n  tasks:\n    - pip:\n        requirements: /opt/autobot/src/autobot-npu-worker/requirements.txt\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 0, result.stdout
    assert "1 deployed-src reference(s) resolve" in result.stdout


def test_the_real_repository_passes():
    """The guard must be green on the tree it ships with."""
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    result = _run(repo_root)

    assert result.returncode == 0, result.stdout
    # And it must be checking something — "0 references" would be a guard that cannot fail.
    assert "0 deployed-src reference(s)" not in result.stdout


# ------------------------------------------------- host patterns (#13745)


def _inventory(tmp_path: pathlib.Path, body: str, name: str = "hosts.yml") -> None:
    inv = tmp_path / "component" / "ansible" / "inventory"
    inv.mkdir(parents=True, exist_ok=True)
    (inv / name).write_text(body, encoding="utf-8")


def test_a_group_no_inventory_defines_is_reported(tmp_path):
    """A play targeting nothing is skipped silently — ok=0, exit 0, reads as success."""
    _inventory(tmp_path, "all:\n  children:\n    frontend:\n      hosts:\n        web-1: {}\n")
    _play(tmp_path, "- name: Deploy\n  hosts: browser\n  tasks: []\n")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "hosts: browser" in result.stdout


def test_a_group_defined_by_any_inventory_resolves(tmp_path):
    """Several inventories ship, describing different topologies.

    A play with no target in one of them is not a defect, so the rule is
    "at least one", not "every".
    """
    _inventory(tmp_path, "all:\n  children:\n    frontend:\n      hosts:\n        web-1: {}\n")
    _inventory(tmp_path, "all:\n  children:\n    browser:\n      hosts:\n        br-1: {}\n", name="production.yml")
    _play(tmp_path, "- name: Deploy\n  hosts: browser\n  tasks: []\n")

    assert _run(tmp_path).returncode == 0


def test_an_alias_group_resolves(tmp_path):
    """#2515 aliases exist so production.yml's names resolve in hosts.yml.

    #13745 read only the `children:` block and reported these as undefined.
    """
    _inventory(
        tmp_path,
        "all:\n  children:\n    npu_workers:\n      hosts:\n        npu-1: {}\n\nnpu:\n  children:\n    npu_workers:\n",
    )
    _play(tmp_path, "- name: Deploy\n  hosts: npu\n  tasks: []\n")

    assert _run(tmp_path).returncode == 0


def test_a_host_name_is_a_valid_target(tmp_path):
    """`hosts:` accepts a host as readily as a group.

    Collecting only groups reported 13 host-targeted plays as broken — a guard
    that cries wolf gets switched off.
    """
    _inventory(tmp_path, "all:\n  children:\n    backend:\n      hosts:\n        autobot-backend: {}\n")
    _play(tmp_path, "- name: Diagnose\n  hosts: autobot-backend\n  tasks: []\n")

    assert _run(tmp_path).returncode == 0


def test_a_sibling_inventory_file_is_read(tmp_path):
    """Both `ansible/inventory/hosts.yml` and `ansible/inventory.yml` are in use."""
    ansible_dir = tmp_path / "component" / "ansible"
    ansible_dir.mkdir(parents=True)
    (ansible_dir / "inventory.yml").write_text(
        "all:\n  children:\n    autobot:\n      hosts:\n        node-1: {}\n", encoding="utf-8"
    )
    _play(tmp_path, "- name: Logging\n  hosts: autobot\n  tasks: []\n")

    assert _run(tmp_path).returncode == 0


@pytest.mark.parametrize("pattern", ["all", "localhost", "{{ target_group }}", "$SOME_VAR"])
def test_patterns_needing_no_inventory_group_are_skipped(pattern, tmp_path):
    _inventory(tmp_path, "all:\n  children:\n    frontend:\n      hosts:\n        web-1: {}\n")
    _play(tmp_path, f"- name: Play\n  hosts: {pattern}\n  tasks: []\n")

    assert _run(tmp_path).returncode == 0


def test_the_allowlist_is_documented_with_a_tracking_issue():
    """An unexplained allowlist entry is indistinguishable from the bug it hides."""
    source = _SCRIPT.read_text(encoding="utf-8")
    block = source.split("_RUNTIME_SUPPLIED_PATTERNS")[0]
    assert "#13786" in block, "each allowlisted pattern needs a tracking issue beside it"


def test_deploy_native_services_resolves_everywhere_it_needs_to():
    """#13745's own example: `npu` and `aiml` do resolve, via the #2515 aliases."""
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    play = repo_root / "autobot-slm-backend/ansible/playbooks/deploy-native-services.yml"
    if not play.exists():  # pragma: no cover - repo layout guard
        pytest.skip("playbook not present")

    all_groups = set().union(*guard.inventory_groups(repo_root).values())
    unresolved = guard._unresolvable_hosts(play.read_text(encoding="utf-8"), all_groups)

    assert unresolved == [], f"deploy-native-services targets undefined groups: {unresolved}"


# ------------------------------------------------ the job that runs the guard


def test_the_workflow_installs_every_third_party_import_the_guard_needs():
    """CI must not be the thing that discovers a missing dependency.

    This job went red twice for exactly that: once for `pytest-asyncio`
    (pytest.ini sets --asyncio-mode=auto) and once for `pyyaml` (the guard parses
    inventories). Both were a full CI round-trip to learn something checkable here.
    """
    import ast  # noqa: PLC0415

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    workflow = repo_root / ".github/workflows/ansible-file-references.yml"
    if not workflow.exists():  # pragma: no cover - repo layout guard
        pytest.skip("workflow not present")

    declared = set()
    for line in workflow.read_text(encoding="utf-8").splitlines():
        if "extra-packages:" in line:
            declared.update(line.split("extra-packages:", 1)[1].split())

    stdlib = set(sys.stdlib_module_names)
    imported = set()
    for source in (_SCRIPT, pathlib.Path(__file__)):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])

    # Distribution names differ from import names for some packages.
    dist_for = {"yaml": "pyyaml", "pytest": "pytest"}
    local = {_SCRIPT.stem}
    third_party = {m for m in imported - stdlib - local if not m.startswith("_")}

    missing = {m for m in third_party if dist_for.get(m, m) not in declared}
    assert not missing, f"the workflow does not install: {sorted(missing)}"
