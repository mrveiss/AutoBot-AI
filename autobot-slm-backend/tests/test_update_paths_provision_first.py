# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every path that runs update-all-nodes.yml provisions pending roles before the play (#22211, #22262).

Source guards, split out of ``test_updater_provisions_pending_roles.py`` (which covers the behaviour) when the
#22262 tests took that file to its size ceiling. The play's vnc gate requires the ``autobot-vnc`` account, and
only provisioning creates it, so a path that runs the playbook without the step first deadlocks a node.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


#: The literal and the names that carry it (services/rollback_target.py holds the one definition).
_PLAYBOOK = "update-all-nodes.yml"
_CONSTANTS = frozenset({"FLEET_UPDATE_PLAYBOOK", "ROLLBACK_PLAYBOOK"})


def _is_playbook(node: ast.AST) -> bool:
    """The playbook name as a literal, a bare constant, or a module attribute (``rollback_target.X``)."""
    if isinstance(node, ast.Constant):
        return node.value == _PLAYBOOK
    return getattr(node, "id", None) in _CONSTANTS or getattr(node, "attr", None) in _CONSTANTS


def _calls_to_update_all(path: Path) -> list[int]:
    """Line numbers of execute_playbook calls naming the fleet update playbook, positionally or by keyword."""
    hits = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "execute_playbook":
            if any(_is_playbook(v) for v in [*node.args, *(k.value for k in node.keywords)]):
                hits.append(node.lineno)
    return hits


def _names_update_all(path: Path) -> bool:
    """Whether a module spells the playbook literal, imports its constant, or reads it off a module."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and any(a.name in _CONSTANTS for a in node.names):
            return True
        if isinstance(node, (ast.Constant, ast.Attribute)) and _is_playbook(node):
            return True
    return False


def test_the_guard_sees_every_call_and_naming_form(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from services.rollback_target import FLEET_UPDATE_PLAYBOOK\n"
        "async def f(e, rollback_target):\n"
        "    await e.execute_playbook('update-all-nodes.yml', limit=[])\n"
        "    await e.execute_playbook(playbook_name='update-all-nodes.yml', limit=[])\n"
        "    await e.execute_playbook(FLEET_UPDATE_PLAYBOOK, limit=[])\n"
        "    await e.execute_playbook(playbook_name=rollback_target.ROLLBACK_PLAYBOOK)\n"
        "    await e.execute_playbook('other.yml')\n",
        encoding="utf-8",
    )
    assert _calls_to_update_all(sample) == [3, 4, 5, 6]
    assert _names_update_all(sample)
    importer = tmp_path / "importer.py"
    importer.write_text("from services.rollback_target import ROLLBACK_PLAYBOOK as P\n", encoding="utf-8")
    assert _names_update_all(importer), "an import of the constant names the playbook"
    other = tmp_path / "other.py"
    other.write_text("PLAYBOOK = 'other.yml'\n", encoding="utf-8")
    assert not _names_update_all(other), "a different playbook is not the fleet update"


def _naming_update_all() -> set[str]:
    """Every non-test SLM module that names the fleet update playbook (docstrings excluded)."""
    from autobot_shared.testfile_names import is_test_filename

    found = set()
    for path in _ROOT.rglob("*.py"):
        skipped = {"tests", "ansible", "venv", ".venv", "node_modules"} & set(path.relative_to(_ROOT).parts)
        if not skipped and not is_test_filename(path.name) and _names_update_all(path):
            found.add(path.relative_to(_ROOT).as_posix())
    return found


def test_every_update_path_provisions_before_the_play() -> None:
    """#22262: every module that names update-all-nodes.yml either runs it through the helper or names it only.

    code_sync's four paths call run_update_all_nodes; the infrastructure route runs the playbook itself, so it
    calls provision_before_raw_update first; rollback_target defines the name. A new module naming it (literal,
    constant import or attribute) fails here, and only the helper may pass it to execute_playbook.
    """
    assert _naming_update_all() == {
        "services/pending_role_provisioning.py",
        "services/rollback_target.py",
        "api/infrastructure.py",
    }
    for rel in _naming_update_all() | {"api/code_sync.py"}:
        hits = _calls_to_update_all(_ROOT / rel)
        assert hits == [] or rel == "services/pending_role_provisioning.py", f"{rel} runs it bypassing the helper"
    code_sync = (_ROOT / "api" / "code_sync.py").read_text(encoding="utf-8")
    assert code_sync.count("run_update_all_nodes(") == 4 and "await provision_pending_roles(node_id)" in code_sync
    infra = (_ROOT / "api" / "infrastructure.py").read_text(encoding="utf-8")
    run = infra[infra.index("async def _run_playbook(") :]
    early = run.index("await provision_before_raw_update(playbook.playbook_file, limit_hosts)")
    assert early < run.index("create_subprocess_exec("), "the raw route provisions before it spawns the play"
