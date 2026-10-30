# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Neither the installer nor code-sync leaves the root-run code tree world-writable (#19503).

rsync -a and Ansible synchronize copy source modes, so one loose source mode reaches every node.
Also pins the install-text fixes that share install.sh and INSTALL.md (#19410, #19867, #19870,
#19181): each is text a reader acts on when something has already gone wrong.
"""

from __future__ import annotations

import ast
import re

import yaml
from repo_tests._paths import repo_root

_ROOT = repo_root()
_INSTALL = (_ROOT / "install.sh").read_text(encoding="utf-8")
_DOC = (_ROOT / "INSTALL.md").read_text(encoding="utf-8")
_SLM = _ROOT / "autobot-slm-backend"
_FLAG = "--chmod=o-w"
_CONSTANT = "RSYNC_NEVER_WORLD_WRITABLE"
_CONSTANTS = {_CONSTANT, "RSYNC_ARCHIVE_ARGS"}
_RSYNC_MODULES = (
    "services/sync_orchestrator.py",
    "api/code_sync.py",
    "api/code_sync_paths.py",
    "api/_rsync_paths.py",
)
_SHELL_SYNCS = (
    "autobot-infrastructure/autobot-slm-backend/scripts/bootstrap-slm.sh",
    "autobot-infrastructure/shared/scripts/install-slm.sh",
    "autobot-infrastructure/shared/scripts/utilities/sync-frontend.sh",
    "autobot-infrastructure/shared/scripts/utilities/sync-to-slm.sh",
    "autobot-infrastructure/shared/scripts/utilities/sync-to-vm.sh",
    "autobot-slm-frontend/scripts/sync-to-admin.sh",
    "sync-frontend.sh",
)
# Carries data, certificates and logs rather than the code tree.
_NOT_CODE = {"data-migration.yml"}


def _rsync_lists(source: str) -> list[list[ast.expr]]:
    """Argument lists of every rsync command, as list literals or subprocess calls."""
    found = []
    for node in ast.walk(ast.parse(source)):
        args = node.elts if isinstance(node, ast.List) else node.args if isinstance(node, ast.Call) else []
        if args and isinstance(args[0], ast.Constant) and args[0].value == "rsync":
            found.append(args)
    return found


def _sets_mode(args: list[ast.expr]) -> bool:
    """The flag directly, or the shared args that carry it, unpacked."""
    unpacked = [a.value for a in args if isinstance(a, ast.Starred)]
    return any(isinstance(a, ast.Name) and a.id in _CONSTANTS for a in [*args, *unpacked])


def _synchronize_tasks(node) -> list[dict]:
    """Every synchronize module body under a parsed YAML document."""
    found = []
    if isinstance(node, list):
        for item in node:
            found += _synchronize_tasks(item)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key in ("synchronize", "ansible.posix.synchronize"):
                found.append(value)
            else:
                found += _synchronize_tasks(value)
    return found


def test_installer_sets_its_umask_before_anything_runs() -> None:
    assert re.search(r"^set -euo pipefail; umask 022\b", _INSTALL, re.M)


def test_installer_strips_an_inherited_default_acl_only_from_a_tree_it_created() -> None:
    """A default ACL on the parent overrides the umask (measured on the clean-install runner)."""
    assert 'setfacl -R -b -k "${AUTOBOT_BASE}"' in _INSTALL
    guard = _INSTALL.index('[[ -d "${AUTOBOT_BASE}" ]] || fresh_base=true')
    assert guard < _INSTALL.index('run_ok "Creating directory structure"') < _INSTALL.index("setfacl -R -b -k")


def test_installer_copy_never_carries_a_world_writable_mode() -> None:
    copies = [line for line in _INSTALL.splitlines() if re.search(r"\brsync -a\b", line)]
    assert copies, "the service-directory copy moved; this test reads nothing"
    assert all(_FLAG in line for line in copies), copies


def test_flag_constant_is_the_value_the_ansible_tasks_use() -> None:
    source = (_SLM / "services" / "deploy_artifacts.py").read_text(encoding="utf-8")
    assert f'{_CONSTANT} = "{_FLAG}"' in source
    assert f'RSYNC_ARCHIVE_ARGS = ("-avz", {_CONSTANT})' in source


def test_every_python_rsync_sets_the_mode() -> None:
    total = 0
    for rel in _RSYNC_MODULES:
        lists = _rsync_lists((_SLM / rel).read_text(encoding="utf-8"))
        total += len(lists)
        assert lists, f"{rel}: no rsync command found"
        assert all(_sets_mode(args) for args in lists), f"{rel}: an rsync copies source modes as they are"
    assert total >= 8, f"expected the 8 known rsync commands, read {total}"


def test_every_code_synchronize_task_sets_the_mode() -> None:
    checked = 0
    for path in sorted((_SLM / "ansible").rglob("*.yml")):
        if path.name in _NOT_CODE or "synchronize:" not in path.read_text(encoding="utf-8"):
            continue
        for task in _synchronize_tasks(list(yaml.safe_load_all(path.read_text(encoding="utf-8")))):
            checked += 1
            assert _FLAG in (task.get("rsync_opts") or []), f"{path.name}: {task.get('dest')}"
    assert checked >= 22, f"expected the 22 known code-tree tasks, read {checked}"


def test_every_code_shell_sync_sets_the_mode() -> None:
    """Backups and logs carry data, and the Windows NPU sync's target has no POSIX modes."""
    for rel in _SHELL_SYNCS:
        copies = [line for line in (_ROOT / rel).read_text(encoding="utf-8").splitlines() if "rsync -avz" in line]
        assert copies, f"{rel}: no rsync found; this test reads nothing"
        assert all(_FLAG in line for line in copies), f"{rel}: {copies}"


def test_contrast_a_bare_rsync_is_caught() -> None:
    assert not all(_sets_mode(args) for args in _rsync_lists('cmd = ["rsync", "-a", src, dst]\n'))
    assert _synchronize_tasks([{"tasks": [{"ansible.posix.synchronize": {"dest": "x"}}]}]) == [{"dest": "x"}]


def test_existing_tree_is_only_reported() -> None:
    body = _INSTALL[_INSTALL.index("report_world_writable_code() {") :]
    body = body[: body.index("\n}\n")]
    assert "-perm -0002" in body and "warn " in body
    assert "chmod" not in body, "changing a live host's modes needs approval (#17038)"
    assert re.search(r"validate_distributions; report_world_writable_code", _INSTALL)


def test_no_terminal_advice_survives_sudo() -> None:
    """#19410: a variable set before sudo never reaches the script."""
    message = next(line for line in _INSTALL.splitlines() if "No terminal to choose an interface" in line)
    assert "sudo AUTOBOT_INSTALL_INTERFACE=<name> bash" in message and "sudo bash -s -- --ip=" in message
    assert "sudo AUTOBOT_INSTALL_INTERFACE=eth0 bash" in _DOC and "sudo bash -s -- --ip=<address>" in _DOC


def test_rerun_hint_uses_the_run_skip_set() -> None:
    """#19867: the hint once skipped `provision`, which the run keeps for the backend role (#6600)."""
    assert re.search(r'local skip_tags="seed"', _INSTALL)
    assert '--skip-tags "${skip_tags}"' in _INSTALL and 'deploy-slm-manager.yml --skip-tags ${skip_tags}"' in _INSTALL
    assert "seed,provision" not in _INSTALL


def test_admin_pass_error_names_the_current_variable() -> None:
    """#19870: AUTOBOT_SLM_ADMIN_PASSWORD is deprecated (#19318)."""
    line = next(line for line in _INSTALL.splitlines() if line.lstrip().startswith("--admin-pass=*)"))
    assert "SLM_ADMIN_PASSWORD" in line and "AUTOBOT_SLM_ADMIN_PASSWORD" not in line


def test_wizard_table_lists_every_step() -> None:
    """#19181: the table had 8 rows for 9 steps; configure_secrets renders as API Keys."""
    wizard = (_SLM / "api" / "setup_wizard.py").read_text(encoding="utf-8")
    steps = re.findall(r'^    "(\w+)",$', wizard[wizard.index("WIZARD_STEPS = [") :].split("]")[0], re.M)
    section = _DOC[_DOC.index("| Welcome |") :].split("\n\n")[0]
    assert len(steps) == 9 and len(section.splitlines()) == len(steps), (steps, section)
    assert "| API Keys |" in section
