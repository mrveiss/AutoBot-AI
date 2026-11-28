# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The native installer accepts only the OS it is built for: Ubuntu 22.04+ (#19235).

INSTALL.md said "Debian 11+ / Ubuntu 22.04+", and the gate checked only /etc/debian_version, but
install.sh gets Python 3.14 and Ansible from Ubuntu Launchpad PPAs, which Debian has no source
for, so a Debian install passed the gate and failed halfway. The owner chose to narrow
(2026-10-22). These tests run install.sh's own gate lines against an os-release file the test
writes, so a gate that drifts from the documented OS fails here.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_ROOT = repo_root()
_INSTALL = _ROOT / "install.sh"


def _gate(os_release: Path) -> str:
    text = _INSTALL.read_text(encoding="utf-8")
    m = re.search(r"    local os_id=\"\" os_version=\"\" os_name\n.*?\|\| fatal \"[^\"]*\"\n", text, re.S)
    assert m, "install.sh no longer has the Ubuntu gate"
    return m.group(0).replace("/etc/os-release", str(os_release))


@pytest.mark.parametrize(
    ("id_", "version", "accepted"),
    [
        ("ubuntu", "22.04", True),
        ("ubuntu", "24.04", True),
        ("ubuntu", "20.04", False),
        ("debian", "12", False),
        ("", "", False),
    ],
)
def test_only_ubuntu_22_04_or_newer_passes(tmp_path: Path, id_: str, version: str, accepted: bool) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash unavailable")
    os_release = tmp_path / "os-release"
    os_release.write_text(f'ID={id_}\nVERSION_ID="{version}"\nNAME="test"\n', encoding="utf-8")
    script = (
        'set -euo pipefail\nfatal() { echo "FATAL: $*"; exit 1; }\n'
        + "gate() {\n"
        + _gate(os_release)
        + "}\ngate\necho PASSED\n"
    )
    out = subprocess.run([bash, "-c", script], capture_output=True, text=True, timeout=30)
    assert ("PASSED" in out.stdout) is accepted, out.stdout + out.stderr
    if not accepted:
        assert "Ubuntu 22.04 or newer" in out.stdout and "Docker path in INSTALL.md" in out.stdout


def test_the_docs_name_only_the_os_the_installer_accepts() -> None:
    install_md = (_ROOT / "INSTALL.md").read_text(encoding="utf-8")
    assert "| OS | Ubuntu 22.04+" in install_md
    assert "Debian 11+" not in install_md, "INSTALL.md still promises Debian"
