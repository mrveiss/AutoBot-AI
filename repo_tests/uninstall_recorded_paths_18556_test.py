# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Alertmanager's paths go on uninstall only when the install record says AutoBot made them (#18556).

A host may run its own Alertmanager on the same paths (the upstream tarball's layout). The
monitoring role records ``created_path=<path>`` for each path that was absent before it ran;
``scripts/uninstall.sh`` removes a RECORDED_PATHS entry only when the record lists it, and names
every other one as kept. Nothing here runs an uninstall: the real functions run against temp paths.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import yaml
from repo_tests._paths import repo_root

_ROOT = repo_root()
_UNINSTALL = _ROOT / "scripts" / "uninstall.sh"
_ROLE = _ROOT / "autobot-slm-backend" / "ansible" / "roles" / "monitoring"


def _uninstall_array(name: str) -> list[str]:
    body = re.search(rf"^readonly {name}=\((.*?)\)", _UNINSTALL.read_text(encoding="utf-8"), re.S | re.M).group(1)
    return [tok.strip("\"'") for tok in body.split()]


def _recorded_paths(tmp: Path, record: str | None, which: str) -> list[str]:
    text = _UNINSTALL.read_text(encoding="utf-8")
    funcs = "\n".join(
        re.search(rf"^{n}\(\) \{{.*?^\}}", text, re.S | re.M).group(0)
        for n in ("record_values", "existing", "recorded_paths")
    )
    mine, theirs = tmp / "mine", tmp / "theirs"
    mine.mkdir(parents=True), theirs.mkdir()
    rec = tmp / "install-record"
    if record is not None:
        rec.write_text(record.format(mine=mine), encoding="utf-8")
    script = f"set -euo pipefail\nINSTALL_RECORD={rec}\nRECORDED_PATHS=({mine} {theirs} {tmp}/absent)\n{funcs}\nrecorded_paths {which}\n"
    out = subprocess.run([shutil.which("bash") or "bash", "-c", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return [Path(p).name for p in out.stdout.split()]


def test_only_a_recorded_path_is_removed_and_every_other_one_is_named_kept(tmp_path: Path) -> None:
    record = "package=nodejs\ncreated_path={mine}\n"
    assert _recorded_paths(tmp_path / "a", record, "yes") == ["mine"]
    assert _recorded_paths(tmp_path / "b", record, "no") == ["theirs"]


def test_contrast_without_a_record_nothing_is_removed(tmp_path: Path) -> None:
    assert _recorded_paths(tmp_path / "a", None, "yes") == []
    assert _recorded_paths(tmp_path / "b", None, "no") == ["mine", "theirs"]


def test_the_ungated_lists_no_longer_carry_alertmanager() -> None:
    ungated = _uninstall_array("PATHS") + _uninstall_array("UNITS")
    assert not [p for p in ungated if "alertmanager" in p.lower()], ungated
    assert "/etc/alertmanager" in _uninstall_array("RECORDED_PATHS")


def test_the_role_records_exactly_the_paths_the_uninstaller_gates() -> None:
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    as_named = {
        "{{ alertmanager_install_dir }}": "${ALERTMANAGER_DIR}",
        "{{ alertmanager_config_dir }}": defaults["alertmanager_config_dir"],
        "{{ alertmanager_data_dir }}": defaults["alertmanager_data_dir"],
    }
    role = [as_named.get(p, p) for p in defaults["alertmanager_owned_paths"]]
    assert sorted(role) == sorted(_uninstall_array("RECORDED_PATHS"))
    tasks = (_ROLE / "tasks" / "alertmanager.yml").read_text(encoding="utf-8")
    assert 'line: "created_path={{ item.item }}"' in tasks and "when: not item.stat.exists" in tasks
    assert "record_values created_path" in _UNINSTALL.read_text(encoding="utf-8")


def test_the_role_writes_the_record_the_installer_and_uninstaller_read() -> None:
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    for script in (_UNINSTALL, _ROOT / "install.sh"):
        assert f'readonly INSTALL_RECORD="{defaults["autobot_install_record"]}"' in script.read_text(encoding="utf-8")
