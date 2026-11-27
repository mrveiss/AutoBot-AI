# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every path that runs update-all-nodes.yml provisions pending roles before the play (#22211, #22262).

Source guards, split out of ``test_updater_provisions_pending_roles.py`` (which covers the behaviour) when the
#22262 tests took that file to its size ceiling. The play's vnc gate requires the ``autobot-vnc`` account, and
only provisioning creates it, so a path that runs the playbook without the step first deadlocks a node.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _calls_to_update_all(path: Path) -> list[int]:
    """Line numbers of execute_playbook calls naming update-all-nodes.yml, positionally or by keyword."""
    import ast

    hits = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "execute_playbook":
            values = [*node.args, *(k.value for k in node.keywords)]
            if any(isinstance(v, ast.Constant) and v.value == "update-all-nodes.yml" for v in values):
                hits.append(node.lineno)
    return hits


def test_the_guard_sees_both_call_forms(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "async def f(e):\n"
        "    await e.execute_playbook('update-all-nodes.yml', limit=[])\n"
        "    await e.execute_playbook(playbook_name='update-all-nodes.yml', limit=[])\n"
        "    await e.execute_playbook('other.yml')\n",
        encoding="utf-8",
    )
    assert _calls_to_update_all(sample) == [2, 3]


def _naming_update_all() -> set[str]:
    """Every non-test SLM module holding the literal name ``update-all-nodes.yml`` (docstrings excluded)."""
    import ast

    from autobot_shared.testfile_names import is_test_filename

    found = set()
    for path in _ROOT.rglob("*.py"):
        rel = path.relative_to(_ROOT).as_posix()
        skipped = {"tests", "ansible", "venv", ".venv", "node_modules"} & set(path.relative_to(_ROOT).parts)
        if skipped or is_test_filename(path.name):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(isinstance(n, ast.Constant) and n.value == "update-all-nodes.yml" for n in ast.walk(tree)):
            found.add(rel)
    return found


def test_every_update_path_provisions_before_the_play() -> None:
    """#22262: every module that names update-all-nodes.yml either runs it through the helper or names it only.

    code_sync's four paths call run_update_all_nodes; the infrastructure route runs the playbook itself, so it
    calls provision_before_raw_update first; rollback_target only names it. A new module naming it fails here.
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
