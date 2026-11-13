# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20509: a role never reaches repo files through playbook_dir, whose depth depends on the playbook."""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._comment_syntax import strip_trailing_comment
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
    growth=40,
    what="Ansible YAML files",
    roots=(_ROLES,),
)


def _offenders(text: str) -> bool:
    return any(_BAD.search(strip_trailing_comment(line, ("#",))) for line in text.splitlines())


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


_SHARED = f"{_ROLES}/_shared/tasks"
#: A `role_path` that quietly falls back to playbook_dir hides the missing anchor it should report.
_FALLBACK = re.compile(r"role_path\s*\|\s*default\(")
#: The one shared task with no role_path (statically imported by playbooks); it proves its tree instead.
_PLAYBOOK_ANCHORED = "install_agent_autobot_shared.yml"


def _code(text: str) -> str:
    return "\n".join(strip_trailing_comment(line, ("#",)) for line in text.splitlines())


def _reads_playbook_dir(text: str) -> bool:
    """True if a task reads ``playbook_dir``; a task ``name:`` that says it does not is a mention."""
    return any("playbook_dir" in line for line in _code(text).splitlines() if not re.match(r"\s*-?\s*name:", line))


def test_contrast_a_task_name_mentioning_playbook_dir_is_not_a_read() -> None:
    assert not _reads_playbook_dir('- name: "Resolve the repo root without playbook_dir (#20509)"\n  debug: {}')
    assert _reads_playbook_dir('  root: "{{ playbook_dir | dirname }}"')


def test_no_shared_task_hides_a_missing_role_path_behind_playbook_dir() -> None:
    bad = [
        p.name
        for p in REACH.examined(repo_root())
        if str(p.relative_to(repo_root())).startswith(_SHARED)
        and _FALLBACK.search(_code(p.read_text(encoding="utf-8")))
    ]
    assert not bad, f"fail loudly on a missing role_path instead of defaulting it: {bad}"


def test_contrast_the_silent_fallback_is_caught() -> None:
    assert _FALLBACK.search("src: \"{{ role_path | default(playbook_dir ~ '/x') }}/../x\"")
    assert not _FALLBACK.search(
        "repo_source_root | default(role_path ~ '/../../../..' if role_path is defined else '', true)"
    )


def test_only_the_playbook_imported_task_reads_playbook_dir_and_it_proves_the_tree() -> None:
    root = repo_root()
    users = sorted(
        p.name
        for p in REACH.examined(root)
        if str(p.relative_to(root)).startswith(_SHARED) and _reads_playbook_dir(p.read_text(encoding="utf-8"))
    )
    assert users == [_PLAYBOOK_ANCHORED]
    text = (root / _SHARED / _PLAYBOOK_ANCHORED).read_text(encoding="utf-8")
    assert "autobot-slm-backend/ansible/roles/_shared/tasks/install_agent_autobot_shared.yml" in text
    assert text.index("shared_anchor.stat.exists") < text.index("shared_src.stat.exists")


def test_the_role_less_callers_name_their_anchor_and_the_tasks_assert_it() -> None:
    root = repo_root()
    for name, var in (
        ("clear_venv_husks.yml", "husk_repo_root"),
        ("stage_shared_manifests.yml", "shared_manifests_repo_root"),
    ):
        text = (root / _SHARED / name).read_text(encoding="utf-8")
        assert f"{var} | length > 0" in text, name
    play = (root / "autobot-slm-backend/ansible/playbooks/update-all-nodes.yml").read_text(encoding="utf-8")
    assert play.count("repo_source_root:") >= play.count("_shared/tasks/clear_venv_husks.yml") >= 2
