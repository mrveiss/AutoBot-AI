# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20509: a role never reaches repo files through playbook_dir, whose depth depends on the playbook."""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROLES = "autobot-slm-backend/ansible/roles"
#: Any climb out of playbook_dir, in either spelling: its depth depends on which playbook ran.
_BAD = re.compile(r"""playbook_dir\s*(?:\}\}|~\s*['"])/\.\.""")


def _role_yaml(root: Path) -> list[Path]:
    try:
        return [root / rel for rel in tracked_paths(root, _ROLES) if rel.endswith((".yml", ".yaml"))]
    except EmptyEnumeration:
        return []


REACH = declare(
    "role-source-paths-depth-proof-20509",
    discover=_role_yaml,
    floor=189,  # mid-window: population 209, window (169, 209)
    growth=40,
    what="Ansible YAML files",
    roots=(_ROLES,),
)


def _offenders(text: str) -> bool:
    return any(_BAD.search(line) for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_no_role_reaches_the_repo_through_playbook_dir() -> None:
    bad = [str(p) for p in REACH.examined(repo_root()) if _offenders(p.read_text(encoding="utf-8"))]
    assert not bad, f"use role_path, whose depth is fixed: {bad}"


def test_contrast_the_old_form_is_caught() -> None:
    assert _offenders('src: "{{ playbook_dir }}/../../../constraints/shared.txt"')
    assert _offenders("""lookup('file', playbook_dir ~ '/../../../x/requirements.txt')""")
    assert _offenders('chdir: "{{ playbook_dir }}/../../.."')
    assert _offenders('src: "{{ playbook_dir }}/../"')
    assert not _offenders('src: "{{ role_path }}/../../../../constraints/shared.txt"')
    assert not _offenders("# the comment may say {{ playbook_dir }}/../")


def test_the_ai_stack_copies_from_its_own_tree() -> None:
    text = (repo_root() / _ROLES / "ai-stack/tasks/main.yml").read_text(encoding="utf-8")
    assert "{{ role_path }}/../../../../autobot-infrastructure/shared/docker/ai-stack/ai_api_server.py" in text
