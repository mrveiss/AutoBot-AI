# Copyright 2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: inter-node SSH key resolution stays unified on ONE canonical location (#12429).

Every consumer that SSHes to fleet nodes (SLM -> node, deploy, code-sync,
service orchestration) MUST resolve the private key from the single canonical
source — ``ssot_config.path.ssh_key_path`` in Python and the
``autobot_ssh_key_path`` Ansible var (both default
``/etc/autobot/ssh/autobot_key``).

This test fails if a regression reintroduces a scattered literal: a
home-dir fleet-key copy (``~/.ssh/autobot_key``), the divergent RSA identity
(``~/.ssh/id_rsa``), the ``autobot_fleet`` key name, or a hardcoded
``ansible_ssh_private_key_file`` in an inventory. See the issue for why the
split caused real ``Permission denied (publickey)`` failures.
"""

from __future__ import annotations

import re
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Python runtime that builds inter-node ssh/rsync commands.
_PY_SCOPE = (_BACKEND_ROOT / "services", _BACKEND_ROOT / "api")

# Literals that must never reappear in runtime Python — each is a scattered
# inter-node key path the canonical accessor replaced.
_FORBIDDEN_PY = (
    re.compile(r"""["']/home/autobot/\.ssh/autobot_key["']"""),  # home-dir fleet copy
    re.compile(r"""\.ssh["'/\s]+id_rsa\b"""),  # divergent RSA identity for node comms
    re.compile(r"autobot_fleet"),  # third key name
    re.compile(r"""os\.environ\.get\(\s*["']SLM_SSH_KEY["']"""),  # per-module env default
)


def _runtime_py_files() -> list[Path]:
    files: list[Path] = []
    for root in _PY_SCOPE:
        for p in root.rglob("*.py"):
            name = p.name
            if name.endswith("_test.py") or name.startswith("test_"):
                continue
            files.append(p)
    return files


def test_no_scattered_inter_node_key_literals_in_python():
    """No runtime Python hardcodes a non-canonical inter-node key path (#12429)."""
    offenders: list[str] = []
    for path in _runtime_py_files():
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pat in _FORBIDDEN_PY:
                if pat.search(line):
                    rel = path.relative_to(_BACKEND_ROOT)
                    offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Inter-node SSH key must resolve via config.path.ssh_key_path (#12429). "
        "Scattered literals found:\n" + "\n".join(offenders)
    )


def test_inventories_use_canonical_ssh_key_var():
    """Every inventory ansible_ssh_private_key_file resolves the canonical var (#12429)."""
    inv_dir = _BACKEND_ROOT / "ansible" / "inventory"
    key_line = re.compile(r"ansible_ssh_private_key_file:\s*(.+?)\s*$")
    offenders: list[str] = []
    for path in inv_dir.rglob("*.yml"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            m = key_line.search(line)
            if not m:
                continue
            value = m.group(1).strip().strip('"').strip("'")
            if "autobot_ssh_key_path" not in value:
                rel = path.relative_to(_BACKEND_ROOT)
                offenders.append(f"{rel}:{lineno}: {value}")
    assert not offenders, (
        "Inventories must set ansible_ssh_private_key_file to "
        '"{{ autobot_ssh_key_path }}" (#12429). Hardcoded values:\n' + "\n".join(offenders)
    )


def test_canonical_ssh_key_var_defined_once():
    """The single canonical Ansible var exists with the /etc default (#12429)."""
    all_yml = _BACKEND_ROOT / "ansible" / "inventory" / "group_vars" / "all.yml"
    text = all_yml.read_text(encoding="utf-8")
    assert re.search(
        r'^autobot_ssh_key_path:\s*["\']?/etc/autobot/ssh/autobot_key["\']?\s*$',
        text,
        re.MULTILINE,
    ), "group_vars/all.yml must define autobot_ssh_key_path: /etc/autobot/ssh/autobot_key (#12429)"
