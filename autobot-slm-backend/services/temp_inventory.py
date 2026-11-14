# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Temporary inventories that load the real group_vars (#14286, #19202).

Ansible resolves ``group_vars/`` relative to the inventory SOURCE directory. An inventory
written beside no ``group_vars`` sibling loads none of ``inventory/group_vars/*.yml``: no
``autobot.base_dir``, no ``role_*_active`` facts. Every caller that hands
``execute_playbook`` its own inventory writes it here, so one helper carries the link.
"""

import tempfile
from pathlib import Path

from services.playbook_executor import ANSIBLE_LOCAL_TMP, link_group_vars


def write_linked_inventory(content: str, prefix: str, ansible_dir: Path) -> Path:
    """Write *content* to a fresh inventory file with ``group_vars`` linked beside it.

    The file goes into the uid-scoped ansible tmp dir, never the code tree: the symlink
    placed next to it must neither dirty the checkout nor land in a world-writable
    directory shared with other users. The caller removes the file when the run ends.

    Args:
        content: the inventory YAML text.
        prefix: file-name prefix naming the caller, e.g. ``"decommission_inv_"``.
        ansible_dir: the ansible directory holding ``inventory/group_vars``.

    Returns:
        Path to the written inventory.

    Raises:
        RuntimeError: group_vars could not be linked; the inventory file is removed first.
    """
    tmp_dir = Path(ANSIBLE_LOCAL_TMP)
    tmp_dir.mkdir(mode=0o700, exist_ok=True)
    fd, name = tempfile.mkstemp(suffix=".yml", prefix=prefix, dir=str(tmp_dir))
    path = Path(name)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
        link_group_vars(path, ansible_dir)
        _require_group_vars(path, ansible_dir)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def _require_group_vars(inventory: Path, ansible_dir: Path) -> None:
    """Raise unless *inventory*'s ``group_vars`` sibling is the real directory.

    ``link_group_vars`` is best-effort and returns silently when the source is absent or the
    symlink fails; Ansible would then run without ``autobot.base_dir`` and the role facts.
    """
    expected = ansible_dir / "inventory" / "group_vars"
    linked = inventory.parent / "group_vars"
    if not (expected.is_dir() and linked.is_dir() and linked.resolve() == expected.resolve()):
        raise RuntimeError(
            f"group_vars for {inventory.name} did not resolve to {expected}; refusing to run Ansible without them"
        )
