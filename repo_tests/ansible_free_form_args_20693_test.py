# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20693: a stray quote in a shell comment refused a whole include, and every update stopped before migrating."""

from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[1]
_BACKUP = _ROOT / "autobot-slm-backend/ansible/_shared/tasks/pre_migration_backup.yml"


def _shell_blocks() -> list:
    tasks = yaml.safe_load(_BACKUP.read_text(encoding="utf-8"))
    return [t["ansible.builtin.shell"] for t in tasks if "ansible.builtin.shell" in t]


def test_no_shell_block_in_the_backup_include_has_an_odd_apostrophe() -> None:
    """Runs without ansible-core; the full check runs Ansible's own splitter in its workflow."""
    blocks = _shell_blocks()
    assert len(blocks) >= 2, "this would be judging almost nothing"
    assert not any("libpq's" in block for block in blocks)


def test_the_check_refuses_a_stray_quote_and_passes_the_tree(tmp_path) -> None:
    pytest.importorskip("ansible")
    import sys

    sys.path.insert(0, str(_ROOT / "tools/lint"))
    from check_ansible_free_form_args import check_tree

    bad = tmp_path / "bad.yml"
    bad.write_text("- name: t\n  ansible.builtin.shell: |\n    # libpq's own\n    echo hi\n", encoding="utf-8")
    assert check_tree(tmp_path)[1], "the known-bad control must be refused"
    examined, refused = check_tree(_ROOT / "autobot-slm-backend/ansible")
    assert examined > 100 and refused == []
