# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the hardcoded-value detector's shell-script blind spot (#14316).

``detect-hardcoded-values.sh`` used to scan only ``*.py``/``*.ts``/``*.vue``,
so no shell script was ever scanned and ``autobot-infrastructure`` was not
even in its ``SCAN_DIRS``. That is how ``User=kali``, ``chown kali:kali`` and
bare ``kali ALL=(ALL) NOPASSWD:`` sudoers lines sat in
``autobot-infrastructure/shared/scripts/utilities/fix-vnc-desktop.sh``,
``fix-vnc-wsl.sh`` and ``setup/system/setup_passwordless_sudo.sh`` while the
detector reported clean.

Every test below builds a throwaway tree under ``tmp_path`` and runs a COPY
of the real script against it -- ``REPO_ROOT`` inside the script is derived
from its own location (``dirname BASH_SOURCE/..``), so copying it to
``<tmp>/pipeline-scripts/`` makes ``<tmp>`` the resolved repo root, fully
isolated from the real checkout's own violation backlog.

Fixture strings are assembled from fragments rather than written as literal
text, so this file cannot itself be mistaken for a hardcoded credential or
fleet IP by an unrelated scanner walking test sources.
"""

from __future__ import annotations

import json
import shutil
import stat
import subprocess  # nosec B404 - fixed argv, no shell
from pathlib import Path

_SCRIPT = Path(__file__).with_name("detect-hardcoded-values.sh")

_BAD_ACCOUNT = "ka" + "li"
_FLEET_IP = ".".join(("172", "16", "168", "77"))


def _hermetic_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    scripts_dir = root / "pipeline-scripts"
    scripts_dir.mkdir(parents=True)
    target = scripts_dir / "detect-hardcoded-values.sh"
    shutil.copy(_SCRIPT, target)
    target.chmod(target.stat().st_mode | stat.S_IEXEC)
    return root


def _run(root: Path) -> dict:
    result = subprocess.run(  # nosec B603 - fixed argv, no shell
        ["bash", str(root / "pipeline-scripts" / "detect-hardcoded-values.sh"), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_a_sudoers_line_in_a_shell_script_is_now_flagged(tmp_path):
    """The exact shape from #14316: a bare ``kali ALL=(ALL) NOPASSWD: ...`` line."""
    root = _hermetic_repo(tmp_path)
    infra = root / "autobot-infrastructure" / "shared" / "scripts" / "setup"
    infra.mkdir(parents=True)
    (infra / "setup_passwordless_sudo.sh").write_text(
        f"#!/bin/bash\n{_BAD_ACCOUNT} ALL=(ALL) NOPASSWD: /usr/bin/lsof\n",
        encoding="utf-8",
    )

    report = _run(root)

    assert report["other_violations"] >= 1
    assert report["status"] == "pass", "an account violation alone must not block the SSOT gate"


def test_a_systemd_user_directive_in_a_shell_script_is_now_flagged(tmp_path):
    """The ``fix-vnc-desktop.sh`` shape: ``User=kali`` inside a heredoc unit file."""
    root = _hermetic_repo(tmp_path)
    infra = root / "autobot-infrastructure" / "shared" / "scripts" / "utilities"
    infra.mkdir(parents=True)
    (infra / "fix-vnc-desktop.sh").write_text(
        "#!/bin/bash\n"
        "cat > /etc/systemd/system/tigervnc.service << EOF\n"
        f"User={_BAD_ACCOUNT}\n"
        f"Group={_BAD_ACCOUNT}\n"
        "EOF\n",
        encoding="utf-8",
    )

    report = _run(root)

    assert report["other_violations"] >= 2  # one for User=, one for Group=


def test_the_fixed_variable_form_stays_clean(tmp_path):
    """The real post-#14036 fix: ``User=${VNC_USER}`` is indirection, not a
    literal, and must not become a new false positive."""
    root = _hermetic_repo(tmp_path)
    infra = root / "autobot-infrastructure" / "shared" / "scripts" / "utilities"
    infra.mkdir(parents=True)
    (infra / "fix-vnc-desktop.sh").write_text(
        "#!/bin/bash\n"
        'VNC_USER="${AUTOBOT_VNC_USER:-autobot}"\n'
        "cat > /etc/systemd/system/tigervnc.service << EOF\n"
        "User=${VNC_USER}\n"
        "Group=${VNC_USER}\n"
        "EOF\n",
        encoding="utf-8",
    )

    report = _run(root)

    assert report["total_violations"] == 0


def test_a_hardcoded_fleet_ip_in_a_shell_script_is_now_flagged(tmp_path):
    """The IP scan has the same blind spot -- shell/ansible were never included."""
    root = _hermetic_repo(tmp_path)
    shared = root / "autobot_shared"
    shared.mkdir(parents=True)
    (shared / "deploy.sh").write_text(f"HOST={_FLEET_IP}\n", encoding="utf-8")

    report = _run(root)

    assert report["ssot_violations"] >= 1
    assert report["status"] == "fail", "a hardcoded fleet IP must still block the gate"


def test_a_hardcoded_fleet_ip_in_an_ansible_yaml_file_is_now_flagged(tmp_path):
    root = _hermetic_repo(tmp_path)
    ansible_dir = root / "autobot-slm-backend" / "ansible"
    ansible_dir.mkdir(parents=True)
    (ansible_dir / "inventory.yml").write_text(f"host: {_FLEET_IP}\n", encoding="utf-8")

    report = _run(root)

    assert report["ssot_violations"] >= 1


def test_an_unrelated_extension_is_still_ignored(tmp_path):
    """Scope check: the fix targets sh/yml/yaml, not every file in the tree."""
    root = _hermetic_repo(tmp_path)
    shared = root / "autobot_shared"
    shared.mkdir(parents=True)
    (shared / "notes.txt").write_text(f"{_BAD_ACCOUNT} ALL=(ALL) NOPASSWD: x\n{_FLEET_IP}\n", encoding="utf-8")

    report = _run(root)

    assert report["total_violations"] == 0


def test_the_real_repository_has_no_new_blocking_ssot_violations():
    """End-to-end against the real tree.

    Enabling ``*.sh``/``*.yml``/``*.yaml`` scanning must surface an
    ``other_violations`` backlog (expected, per #14316) without turning up a
    NEW ``ssot_violations`` hit -- that category blocks the CI gate
    (ssot-coverage.yml's job-status step), so a real fleet IP reachable only
    once shell/yaml scanning was enabled would silently redden every future
    PR touching an unrelated file that happens to share this workflow.
    """
    result = subprocess.run(  # nosec B603 B607 - fixed argv, no shell
        ["bash", str(_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)

    assert report["ssot_violations"] == 0, (
        "a real fleet IP is now reachable through *.sh/*.yml/*.yaml scanning and must be "
        f"fixed at the source (or noqa'd if a documented example), not allow-listed: {report}"
    )
