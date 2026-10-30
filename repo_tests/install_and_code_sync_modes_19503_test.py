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
import subprocess

import yaml
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()
_INSTALL = (_ROOT / "install.sh").read_text(encoding="utf-8")
_DOC = (_ROOT / "INSTALL.md").read_text(encoding="utf-8")
_SLM = _ROOT / "autobot-slm-backend"
_FLAG = "--chmod=o-w"
_CONSTANT = "RSYNC_NEVER_WORLD_WRITABLE"
_CONSTANTS = {_CONSTANT, "RSYNC_ARCHIVE_ARGS"}
# Copying without the flag on purpose: data rather than code, or a target with no POSIX modes.
_SHELL_EXEMPT = {
    "autobot-infrastructure/shared/scripts/logging/collect-application-logs.sh": "pulls logs",
    "autobot-infrastructure/shared/scripts/utilities/sync-npu-worker-to-windows.sh": "Windows target",
    "autobot-slm-backend/ansible/utils/backup.sh": "pulls backups",
}
_ARCHIVE_RSYNC = re.compile(r"\brsync\s+-[a-zA-Z]*a")
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
    assert _ARCHIVE_RSYNC.search(_INSTALL), "the service-directory copy moved; this test reads nothing"
    assert not _loose_copies(_INSTALL)


def test_flag_constant_is_the_value_the_ansible_tasks_use() -> None:
    source = (_SLM / "services" / "deploy_artifacts.py").read_text(encoding="utf-8")
    assert f'{_CONSTANT} = "{_FLAG}"' in source
    assert f'RSYNC_ARCHIVE_ARGS = ("-avz", {_CONSTANT})' in source


def test_every_python_rsync_sets_the_mode() -> None:
    total = 0
    for path in sorted(_SLM.rglob("*.py")):
        rel = path.relative_to(_SLM).as_posix()
        if rel.startswith(("tests/", "venv/", ".venv/")) or path.name.endswith("_test.py"):
            continue
        lists = _rsync_lists(path.read_text(encoding="utf-8"))
        total += len(lists)
        assert all(_sets_mode(args) for args in lists), f"{rel}: an rsync copies source modes as they are"
    assert total >= 8, f"expected at least the 8 known rsync commands, read {total}"


def test_every_code_synchronize_task_sets_the_mode() -> None:
    checked = 0
    for path in sorted((_SLM / "ansible").rglob("*.yml")):
        if path.name in _NOT_CODE or "synchronize:" not in path.read_text(encoding="utf-8"):
            continue
        for task in _synchronize_tasks(list(yaml.safe_load_all(path.read_text(encoding="utf-8")))):
            checked += 1
            assert _FLAG in (task.get("rsync_opts") or []), f"{path.name}: {task.get('dest')}"
    assert checked >= 22, f"expected the 22 known code-tree tasks, read {checked}"


def _loose_copies(text: str) -> list[str]:
    """Archive-mode rsync lines that keep source modes."""
    return [
        line
        for line in text.splitlines()
        if _ARCHIVE_RSYNC.search(line) and _FLAG not in line and not line.lstrip().startswith(("#", "echo"))
    ]


def test_every_shell_rsync_sets_the_mode_or_is_exempt() -> None:
    listed = tracked_paths(_ROOT, "*.sh")
    assert len(listed) > 50, f"git listed {len(listed)} shell files; this test reads nothing"
    loose = {rel for rel in listed if _loose_copies((_ROOT / rel).read_text(encoding="utf-8", errors="replace"))}
    assert loose == set(_SHELL_EXEMPT), loose ^ set(_SHELL_EXEMPT)


def test_contrast_a_bare_rsync_is_caught() -> None:
    assert not all(_sets_mode(args) for args in _rsync_lists('cmd = ["rsync", "-a", src, dst]\n'))
    assert _synchronize_tasks([{"tasks": [{"ansible.posix.synchronize": {"dest": "x"}}]}]) == [{"dest": "x"}]
    assert _loose_copies('    rsync -avz --delete "$a" "$b"\n') and _loose_copies('local cmd="rsync -a"\n')
    assert not _loose_copies(f'rsync -avz {_FLAG} "$a" "$b"\n# rsync -a\nrsync --version\n')


def _report(tmp_path) -> str:
    """install.sh's own report function, over a tree where one critical dir is missing."""
    body = _INSTALL[_INSTALL.index("report_world_writable_code() {") :]
    body = body[: body.index("\n}\n") + 3]
    script = f"""set -euo pipefail
warn() {{ echo "WARN $*"; }}
CODE_SOURCE={tmp_path}/code_source; AUTOBOT_BASE={tmp_path}; CRITICAL_DIRS=(present absent)
{body}
report_world_writable_code
echo FINISHED
"""
    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
    assert done.returncode == 0 and "FINISHED" in done.stdout, done.stdout + done.stderr
    return done.stdout


def test_existing_tree_is_reported_and_never_changed(tmp_path) -> None:
    (tmp_path / "code_source").mkdir()
    loose = tmp_path / "present"
    loose.mkdir()
    loose.chmod(0o755)
    assert "WARN" not in _report(tmp_path), "a clean tree was reported"
    loose.chmod(0o777)
    assert "WARN 1 world-writable" in _report(tmp_path)
    assert loose.stat().st_mode & 0o777 == 0o777, "the report changed a live tree's modes (#17038)"


def test_validate_reports_before_a_missing_directory_can_end_it() -> None:
    assert "report_world_writable_code; validate_distributions; exit 0" in _INSTALL


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


def _wizard_rows() -> list[str]:
    section = _DOC[_DOC.index("| Welcome |") :].split("\n\n")[0]
    return [row.split("|")[1].strip() for row in section.splitlines()]


def _ui_labels() -> list[str]:
    """The labels the wizard renders, in WIZARD_STEPS order."""
    wizard = (_SLM / "api" / "setup_wizard.py").read_text(encoding="utf-8")
    steps = re.findall(r'^    "(\w+)",$', wizard[wizard.index("WIZARD_STEPS = [") :].split("]")[0], re.M)
    view = (_ROOT / "autobot-slm-frontend" / "src" / "views" / "SetupWizardView.vue").read_text(encoding="utf-8")
    block = view[view.index("const stepLabels") :].split("}")[0]
    labels = dict(re.findall(r"^\s+(\w+): '([^']+)',$", block, re.M))
    return [labels[step] for step in steps]


def test_wizard_table_uses_the_real_ui_labels() -> None:
    """#19181: 8 rows for 9 steps, and row names the UI does not show."""
    assert len(_ui_labels()) == 9, _ui_labels()
    assert _wizard_rows() == _ui_labels()
